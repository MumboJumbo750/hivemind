/**
 * Hivemind Auto-Execute — TASK-IDE-006
 *
 * Empfängt Conductor-Dispatches und delegiert sie automatisch an Copilot Agent Mode.
 *
 * Governance-Stufen (konfigurierbar in Extension Settings):
 *   manual     — Notification + User-Bestätigung vor jeder Ausführung
 *   semi-auto  — Auto-Execute für Worker + Kartograph, Manual für Stratege + Architekt
 *   full-auto  — Alle Dispatches werden automatisch ausgeführt
 *
 * Limitierung (Stand 2026): VS Code hat kein offizielles API um programmatisch
 * Prompts an Copilot Agent Mode zu senden. Workaround: workbench.action.chat.open
 * mit query-Parameter (experimentell).
 */

import * as vscode from 'vscode';
import * as path from 'node:path';
import {
  acknowledgeDispatch,
  completeDispatch,
  fetchAuditEntries,
  fetchGovernanceConfig,
  HivemindDispatch,
  markDispatchRunning,
  reportDispatchProgress,
  type AuditEntry,
} from './api';
import { AgentActivityProvider } from './sidebarProvider';

type GovernanceLevel = 'manual' | 'semi-auto' | 'full-auto';
type GovernanceSource = 'extension' | 'backend' | 'merged';
type ExecutionTarget = 'chat' | 'cli';

// Roles that auto-execute in semi-auto mode
const SEMI_AUTO_ROLES = new Set(['worker', 'kartograph', 'gaertner']);
const STRATEGY_ROLES = new Set(['stratege', 'architekt', 'triage']);
const COMPLETION_UPDATE_TARGETS = new Set(['in_review', 'done', 'cancelled']);

interface DispatchRunState {
  dispatch: HivemindDispatch;
  startedAtIso: string;
  startedAtMs: number;
  seenAuditIds: Set<string>;
  finished: boolean;
  cancelRequested: boolean;
}

export class AutoExecuteManager {
  private readonly activeRuns = new Map<string, DispatchRunState>();
  private readonly finishedDispatches = new Set<string>();

  constructor(private readonly activityProvider: AgentActivityProvider) {}

  private getGovernanceLevelSetting(): GovernanceLevel {
    return vscode.workspace
      .getConfiguration('hivemind')
      .get<GovernanceLevel>('governanceLevel', 'manual');
  }

  private getGovernanceSource(): GovernanceSource {
    return vscode.workspace
      .getConfiguration('hivemind')
      .get<GovernanceSource>('governanceSource', 'merged');
  }

  private getExecutionTarget(): ExecutionTarget {
    return vscode.workspace
      .getConfiguration('hivemind')
      .get<ExecutionTarget>('executionTarget', 'chat');
  }

  private getTimeoutSeconds(): number {
    return Math.max(
      30,
      vscode.workspace.getConfiguration('hivemind').get<number>('dispatchTimeoutSeconds', 900)
    );
  }

  private getPollIntervalMs(): number {
    return Math.max(
      1000,
      vscode.workspace.getConfiguration('hivemind').get<number>('progressPollIntervalMs', 4000)
    );
  }

  private shouldAutoExecute(level: GovernanceLevel, dispatch: HivemindDispatch): boolean {
    if (level === 'full-auto') return true;
    if (level === 'semi-auto') return SEMI_AUTO_ROLES.has(dispatch.agent_role);
    return false; // manual
  }

  private governanceRank(level: GovernanceLevel): number {
    if (level === 'manual') return 0;
    if (level === 'semi-auto') return 1;
    return 2;
  }

  private mergeGovernance(local: GovernanceLevel, backend: GovernanceLevel): GovernanceLevel {
    return this.governanceRank(local) <= this.governanceRank(backend) ? local : backend;
  }

  private normalizeBackendLevel(level: string): GovernanceLevel {
    if (level === 'auto') return 'full-auto';
    if (level === 'assisted') return 'semi-auto';
    return 'manual';
  }

  private async resolveBackendGovernance(dispatch: HivemindDispatch): Promise<GovernanceLevel | undefined> {
    const cfg = await fetchGovernanceConfig();
    if (!cfg) {
      return undefined;
    }

    if (dispatch.agent_role === 'reviewer') {
      return this.normalizeBackendLevel(cfg.review);
    }
    if (dispatch.agent_role === 'gaertner') {
      return this.normalizeBackendLevel(cfg.skill_merge);
    }
    if (STRATEGY_ROLES.has(dispatch.agent_role)) {
      const levels = [
        this.normalizeBackendLevel(cfg.epic_scoping),
        this.normalizeBackendLevel(cfg.epic_proposal),
        this.normalizeBackendLevel(cfg.decision_request),
      ];
      const min = Math.min(...levels.map(level => this.governanceRank(level)));
      if (min === 0) return 'manual';
      if (min === 1) return 'semi-auto';
      return 'full-auto';
    }

    // Worker + Kartograph are extension-driven; backend governance currently has no direct role key.
    return 'full-auto';
  }

  private async resolveGovernanceLevel(dispatch: HivemindDispatch): Promise<GovernanceLevel> {
    const local = this.getGovernanceLevelSetting();
    const source = this.getGovernanceSource();

    if (source === 'extension') return local;

    const backend = await this.resolveBackendGovernance(dispatch);
    if (!backend) {
      return source === 'backend' ? 'manual' : local;
    }
    if (source === 'backend') return backend;

    return this.mergeGovernance(local, backend);
  }

  private dispatchLabel(dispatch: HivemindDispatch): string {
    const role = dispatch.agent_role ? dispatch.agent_role[0].toUpperCase() + dispatch.agent_role.slice(1) : 'Worker';
    return `${role}-Task ${dispatch.trigger_id}`;
  }

  private async safeProgress(
    dispatch: HivemindDispatch,
    stage: string,
    message?: string,
    details?: Record<string, unknown>
  ): Promise<void> {
    try {
      await reportDispatchProgress(dispatch.dispatch_id, { stage, message, details });
    } catch {
      // Non-fatal: progress telemetry must not block execution.
    }
  }

  private async finalizeDispatch(
    run: DispatchRunState,
    status: 'completed' | 'failed' | 'cancelled' | 'timed_out',
    summary: string
  ): Promise<void> {
    if (run.finished) {
      return;
    }
    run.finished = true;
    this.activeRuns.delete(run.dispatch.dispatch_id);
    this.finishedDispatches.add(run.dispatch.dispatch_id);

    await this.safeProgress(run.dispatch, `dispatch_${status}`, summary);
    try {
      await completeDispatch(run.dispatch.dispatch_id, summary, status);
    } catch {
      // Completion delivery is best-effort from extension side.
    }
    this.activityProvider.addEvent(
      `${status.toUpperCase()}: [${run.dispatch.agent_role}] ${run.dispatch.trigger_id}`
    );
  }

  private dispatchPrompt(dispatch: HivemindDispatch): string {
    if (dispatch.trigger_id.toUpperCase().startsWith('TASK-')) {
      return `@hivemind task ${dispatch.trigger_id}`;
    }
    if (dispatch.agent_role === 'kartograph') {
      return '@hivemind kartograph';
    }
    return `@hivemind status\n#hivemind:task=${dispatch.trigger_id}`;
  }

  private async openCopilotChat(dispatch: HivemindDispatch): Promise<void> {
    const query = this.dispatchPrompt(dispatch);
    await vscode.commands.executeCommand('workbench.action.chat.open', { query });
  }

  private async writeCliTaskfile(dispatch: HivemindDispatch): Promise<vscode.Uri> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      throw new Error('Kein Workspace geöffnet; Copilot CLI benötigt ein Workspace-Verzeichnis.');
    }
    const dir = vscode.Uri.joinPath(folder.uri, '.hivemind', 'dispatches');
    await vscode.workspace.fs.createDirectory(dir);
    const file = vscode.Uri.joinPath(dir, `${dispatch.dispatch_id}.md`);
    const content = [
      `# Hivemind Dispatch ${dispatch.dispatch_id}`,
      '',
      `- Agent Role: ${dispatch.agent_role}`,
      `- Trigger: ${dispatch.trigger_id}`,
      `- Prompt Type: ${dispatch.prompt_type}`,
      '',
      '## Prompt',
      '',
      dispatch.prompt ?? this.dispatchPrompt(dispatch),
      '',
      '## Completion Rule',
      '',
      "Run `hivemind/submit_result` for this task, then `hivemind/update_task_state` to `in_review`.",
      '',
    ].join('\n');
    await vscode.workspace.fs.writeFile(file, new TextEncoder().encode(content));
    return file;
  }

  private async runCopilotCli(dispatch: HivemindDispatch): Promise<{ command: string; taskfile: string }> {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      throw new Error('Kein Workspace geöffnet; Copilot CLI kann nicht gestartet werden.');
    }
    const taskfile = await this.writeCliTaskfile(dispatch);
    const defaultTemplate = 'gh copilot run --input-file "{taskfile}"';
    const template = vscode.workspace
      .getConfiguration('hivemind')
      .get<string>('copilotCliCommandTemplate', defaultTemplate);
    const command = template
      .replaceAll('{taskfile}', taskfile.fsPath)
      .replaceAll('{task_key}', dispatch.trigger_id)
      .replaceAll('{agent_role}', dispatch.agent_role);

    const terminal = vscode.window.createTerminal({
      name: `Hivemind ${dispatch.trigger_id}`,
      cwd: folder.uri.fsPath,
    });
    terminal.show(true);
    terminal.sendText(command, true);
    return { command, taskfile: taskfile.fsPath };
  }

  private extractTaskKey(entry: AuditEntry): string | undefined {
    const raw = entry.input_snapshot?.task_key ?? entry.input_snapshot?.task_id;
    return typeof raw === 'string' ? raw.toUpperCase() : undefined;
  }

  private isSubmitResultForDispatch(dispatch: HivemindDispatch, entry: AuditEntry): boolean {
    if (entry.tool_name !== 'hivemind/submit_result') {
      return false;
    }
    const trigger = dispatch.trigger_id.toUpperCase();
    const taskKey = this.extractTaskKey(entry);
    if (trigger.startsWith('TASK-') && taskKey) {
      return taskKey === trigger;
    }
    return JSON.stringify(entry.input_snapshot ?? {}).toUpperCase().includes(trigger);
  }

  private isUpdateStateCompletionForDispatch(dispatch: HivemindDispatch, entry: AuditEntry): boolean {
    if (entry.tool_name !== 'hivemind/update_task_state') {
      return false;
    }
    const trigger = dispatch.trigger_id.toUpperCase();
    const taskKey = this.extractTaskKey(entry);
    const targetStateRaw = entry.input_snapshot?.target_state;
    const targetState = typeof targetStateRaw === 'string' ? targetStateRaw.toLowerCase() : '';
    if (!COMPLETION_UPDATE_TARGETS.has(targetState)) {
      return false;
    }
    if (trigger.startsWith('TASK-') && taskKey) {
      return taskKey === trigger;
    }
    return JSON.stringify(entry.input_snapshot ?? {}).toUpperCase().includes(trigger);
  }

  private async monitorExecution(run: DispatchRunState): Promise<void> {
    const timeoutAt = run.startedAtMs + this.getTimeoutSeconds() * 1000;
    const pollIntervalMs = this.getPollIntervalMs();

    while (!run.finished) {
      if (run.cancelRequested) {
        await this.finalizeDispatch(run, 'cancelled', 'Dispatch vom User abgebrochen');
        return;
      }

      if (Date.now() >= timeoutAt) {
        await this.safeProgress(run.dispatch, 'dispatch_timeout', 'Dispatch-Timeout erreicht');
        await this.finalizeDispatch(
          run,
          'timed_out',
          `Kein Completion-Signal innerhalb von ${this.getTimeoutSeconds()}s erkannt`
        );
        void vscode.window.showWarningMessage(
          `Hivemind: Dispatch ${run.dispatch.trigger_id} ist in Timeout gelaufen. Fallback prüfen.`
        );
        return;
      }

      const entries = await fetchAuditEntries(run.startedAtIso, 100);
      const sorted = [...entries].sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));

      for (const entry of sorted) {
        if (run.seenAuditIds.has(entry.id)) {
          continue;
        }
        run.seenAuditIds.add(entry.id);

        if (entry.tool_name.startsWith('hivemind/')) {
          await this.safeProgress(run.dispatch, 'mcp_call', entry.tool_name, {
            audit_id: entry.id,
            created_at: entry.created_at,
          });
          this.activityProvider.addEvent(`MCP: ${entry.tool_name} (${run.dispatch.trigger_id})`);
        }

        if (this.isSubmitResultForDispatch(run.dispatch, entry)) {
          await this.safeProgress(run.dispatch, 'submit_result_detected', 'submit_result erkannt', {
            audit_id: entry.id,
          });
          await this.finalizeDispatch(run, 'completed', 'Completion via MCP submit_result erkannt');
          return;
        }

        if (this.isUpdateStateCompletionForDispatch(run.dispatch, entry)) {
          await this.safeProgress(run.dispatch, 'task_state_transition_detected', 'update_task_state erkannt', {
            audit_id: entry.id,
          });
          await this.finalizeDispatch(run, 'completed', 'Completion via MCP update_task_state erkannt');
          return;
        }
      }

      await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    }
  }

  private async executeDispatch(dispatch: HivemindDispatch): Promise<void> {
    const run: DispatchRunState = {
      dispatch,
      startedAtIso: new Date().toISOString(),
      startedAtMs: Date.now(),
      seenAuditIds: new Set<string>(),
      finished: false,
      cancelRequested: false,
    };
    this.activeRuns.set(dispatch.dispatch_id, run);

    try {
      await acknowledgeDispatch(dispatch.dispatch_id);
      await this.safeProgress(dispatch, 'acknowledged', 'Dispatch acknowledged');

      await markDispatchRunning(dispatch.dispatch_id);
      await this.safeProgress(dispatch, 'running', 'Dispatch running');
    } catch {
      await this.finalizeDispatch(run, 'failed', 'Dispatch konnte nicht als running markiert werden');
      return;
    }

    this.activityProvider.addEvent(`Executing: [${dispatch.agent_role}] ${dispatch.trigger_id}`);

    const executionTarget = this.getExecutionTarget();
    try {
      if (executionTarget === 'cli') {
        const cli = await this.runCopilotCli(dispatch);
        await this.safeProgress(dispatch, 'cli_started', 'Copilot CLI gestartet', cli);
        this.activityProvider.addEvent(`CLI gestartet: ${path.basename(cli.taskfile)}`);
      } else {
        await this.openCopilotChat(dispatch);
        await this.safeProgress(dispatch, 'chat_opened', 'Copilot Chat geöffnet', {
          query: this.dispatchPrompt(dispatch),
        });
      }
    } catch (err) {
      const message = `Copilot-Ausführung fehlgeschlagen: ${err}`;
      await this.safeProgress(dispatch, 'copilot_error', message);
      await this.finalizeDispatch(run, 'failed', message);
      return;
    }

    void vscode.window.showInformationMessage(
      `Hivemind: Dispatch ${dispatch.trigger_id} läuft`,
      'Abbrechen'
    ).then(async action => {
      if (action === 'Abbrechen' && !run.finished) {
        run.cancelRequested = true;
      }
    });

    await this.monitorExecution(run);
  }

  async handleDispatch(dispatch: HivemindDispatch, forceExecute = false): Promise<void> {
    if (this.finishedDispatches.has(dispatch.dispatch_id)) {
      return;
    }
    if (this.activeRuns.has(dispatch.dispatch_id)) {
      return;
    }

    await this.safeProgress(dispatch, 'dispatch_received', 'Dispatch über SSE empfangen', {
      agent_role: dispatch.agent_role,
      trigger_id: dispatch.trigger_id,
    });

    const level = await this.resolveGovernanceLevel(dispatch);

    if (forceExecute || this.shouldAutoExecute(level, dispatch)) {
      await this.executeDispatch(dispatch);
    } else {
      const action = await vscode.window.showInformationMessage(
        `Hivemind: ${this.dispatchLabel(dispatch)} bereit — Ausführen?`,
        'Ausführen',
        'Abbrechen'
      );
      if (action === 'Ausführen') {
        await this.executeDispatch(dispatch);
      } else {
        const run: DispatchRunState = {
          dispatch,
          startedAtIso: new Date().toISOString(),
          startedAtMs: Date.now(),
          seenAuditIds: new Set<string>(),
          finished: false,
          cancelRequested: false,
        };
        await this.finalizeDispatch(run, 'cancelled', 'User hat die Ausführung abgebrochen');
      }
    }

    this.activityProvider.addEvent(
      `Governance: ${level} — [${dispatch.agent_role}] ${dispatch.trigger_id}`
    );
  }
}
