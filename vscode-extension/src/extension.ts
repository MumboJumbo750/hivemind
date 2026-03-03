/**
 * Hivemind VS Code Extension — Entry Point (TASK-IDE-003)
 */

import * as vscode from 'vscode';
import {
  checkHealth,
  fetchActiveTasks,
  fetchGuards,
  fetchPendingDispatches,
  fetchTask,
  HivemindDispatch,
  HivemindTaskGuard,
  reportGuardResult,
  submitTaskResult,
} from './api';
import { AutoExecuteManager } from './autoExecute';
import { registerChatParticipant } from './chatParticipant';
import { registerChatContextTools } from './chatContextTools';
import {
  ActiveTasksProvider,
  AgentActivityProvider,
  GuardStatusProvider,
  NextPromptsProvider,
} from './sidebarProvider';
import { SseListener } from './sseListener';
import { HivemindStatusBar } from './statusBar';

let sseListener: SseListener | null = null;
let statusBar: HivemindStatusBar | null = null;
let refreshTimer: ReturnType<typeof setInterval> | null = null;
let autoExecuteManager: AutoExecuteManager | null = null;

let activeTaskKey: string | undefined;
let activeRole = 'worker';
let taskDetailsPanel: vscode.WebviewPanel | undefined;

interface JsonObject {
  [key: string]: unknown;
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  if (!(await workspaceHasHivemindServer())) {
    return;
  }

  const config = vscode.workspace.getConfiguration('hivemind');
  const autoConnect = config.get<boolean>('autoConnect', true);
  const baseUrl = config.get<string>('url', 'http://localhost:8000');

  const activeTasksProvider = new ActiveTasksProvider();
  const nextPromptsProvider = new NextPromptsProvider();
  const guardStatusProvider = new GuardStatusProvider();
  const agentActivityProvider = new AgentActivityProvider();

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('hivemind.activeTasks', activeTasksProvider),
    vscode.window.registerTreeDataProvider('hivemind.nextPrompts', nextPromptsProvider),
    vscode.window.registerTreeDataProvider('hivemind.guardStatus', guardStatusProvider),
    vscode.window.registerTreeDataProvider('hivemind.agentActivity', agentActivityProvider)
  );

  autoExecuteManager = new AutoExecuteManager(agentActivityProvider);
  statusBar = new HivemindStatusBar();
  context.subscriptions.push(statusBar);

  context.subscriptions.push(
    vscode.commands.registerCommand('hivemind.refresh', async () => {
      await refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar!);
    }),

    vscode.commands.registerCommand('hivemind.nextPrompt', async () => {
      try {
        await vscode.commands.executeCommand('workbench.action.chat.open', {
          query: '/hivemind.next',
        });
      } catch {
        vscode.window.showInformationMessage('Copilot Chat öffnen und /hivemind.next eingeben.');
      }
    }),

    vscode.commands.registerCommand('hivemind.runGuard', async () => {
      await runGuardsForCurrentTask(activeTasksProvider, guardStatusProvider);
    }),

    vscode.commands.registerCommand('hivemind.submitResult', async () => {
      await submitResultDialog(activeTasksProvider, guardStatusProvider);
    }),

    vscode.commands.registerCommand('hivemind.openTask', async (taskKey: string) => {
      setActiveTask(taskKey, 'worker', guardStatusProvider);
      await openTaskDetails(taskKey);
    }),

    vscode.commands.registerCommand('hivemind.executeDispatch', async (dispatch: unknown) => {
      const parsed = dispatch as HivemindDispatch;
      if (!parsed?.dispatch_id || !autoExecuteManager) {
        return;
      }

      if (isTaskKey(parsed.trigger_id)) {
        setActiveTask(parsed.trigger_id, parsed.agent_role ?? 'worker', guardStatusProvider);
      }
      statusBar?.setActiveTask(parsed.trigger_id ?? '?', parsed.agent_role ?? '?');
      await autoExecuteManager.handleDispatch(parsed, true);
    })
  );

  registerChatParticipant(context);
  registerChatContextTools(context);

  if (!autoConnect) {
    return;
  }

  await refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar);

  sseListener = new SseListener(baseUrl, agentActivityProvider, (eventType, data) => {
    const payload = asObject(data);
    const eventTaskKey = getString(payload?.task_key);

    if (eventTaskKey) {
      setActiveTask(eventTaskKey, activeRole, guardStatusProvider);
    }
    if (eventType === 'conductor:dispatch') {
      const dispatch = payload as Partial<HivemindDispatch> | undefined;
      if (dispatch?.execution_mode === 'ide' && dispatch.dispatch_id) {
        if (isTaskKey(dispatch.trigger_id)) {
          setActiveTask(dispatch.trigger_id!, dispatch.agent_role ?? 'worker', guardStatusProvider);
        }
        void autoExecuteManager?.handleDispatch(
          {
            dispatch_id: dispatch.dispatch_id,
            agent_role: dispatch.agent_role ?? 'worker',
            prompt_type: dispatch.prompt_type ?? '',
            trigger_id: dispatch.trigger_id ?? '',
            prompt: dispatch.prompt,
            execution_mode: 'ide',
            status: dispatch.status ?? 'dispatched',
          },
          false
        );
      }
    }

    if (shouldRefreshForEvent(eventType)) {
      void refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar!);
    }
  });
  sseListener.start();

  refreshTimer = setInterval(() => {
    void refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar!);
  }, 30_000);
}

export function deactivate(): void {
  sseListener?.stop();
  sseListener = null;
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  autoExecuteManager = null;
  taskDetailsPanel?.dispose();
  taskDetailsPanel = undefined;
}

async function workspaceHasHivemindServer(): Promise<boolean> {
  const files = await vscode.workspace.findFiles('.vscode/mcp.json', '**/{node_modules,.git}/**', 1);
  if (files.length === 0) {
    return false;
  }

  try {
    const raw = await vscode.workspace.fs.readFile(files[0]);
    const json = JSON.parse(Buffer.from(raw).toString('utf8')) as JsonObject;

    const serverMap = (json.servers ?? json.mcpServers) as JsonObject | undefined;
    if (!serverMap) {
      return false;
    }
    if (Object.prototype.hasOwnProperty.call(serverMap, 'hivemind')) {
      return true;
    }

    for (const value of Object.values(serverMap)) {
      const entry = asObject(value);
      const url = getString(entry?.url);
      if (url?.includes('/api/mcp/sse')) {
        return true;
      }
    }
  } catch {
    return false;
  }
  return false;
}

function setActiveTask(taskKey: string, role: string, guardStatusProvider: GuardStatusProvider): void {
  activeTaskKey = taskKey;
  activeRole = role || 'worker';
  guardStatusProvider.setTask(taskKey);
  statusBar?.setActiveTask(taskKey, activeRole);
}

function shouldRefreshForEvent(eventType: string): boolean {
  if (eventType === 'conductor:dispatch' || eventType === 'notification_created') {
    return true;
  }
  return eventType.startsWith('task_') || eventType === 'task_assigned';
}

async function refreshAll(
  activeTasksProvider: ActiveTasksProvider,
  nextPromptsProvider: NextPromptsProvider,
  guardStatusProvider: GuardStatusProvider,
  status: HivemindStatusBar
): Promise<void> {
  const healthy = await checkHealth();
  if (!healthy) {
    status.setDisconnected();
    return;
  }

  const [tasks, dispatches] = await Promise.all([fetchActiveTasks(), fetchPendingDispatches()]);
  activeTasksProvider.setTasks(tasks);
  nextPromptsProvider.setDispatches(dispatches);

  if (!activeTaskKey || !tasks.some(task => task.task_key === activeTaskKey)) {
    activeTaskKey = tasks[0]?.task_key;
    activeRole = 'worker';
  }

  if (guardStatusProvider.getCurrentTaskKey() !== activeTaskKey) {
    guardStatusProvider.setTask(activeTaskKey);
  } else {
    void guardStatusProvider.loadData();
  }

  status.setConnected(tasks.length, activeTaskKey, activeRole);
}

async function runGuardsForCurrentTask(
  activeTasksProvider: ActiveTasksProvider,
  guardStatusProvider: GuardStatusProvider
): Promise<void> {
  const taskKey = guardStatusProvider.getCurrentTaskKey() ?? activeTaskKey ?? activeTasksProvider.getTasks()[0]?.task_key;
  if (!taskKey) {
    vscode.window.showInformationMessage('Kein aktiver Task für Guard-Ausführung vorhanden.');
    return;
  }

  const guardsResponse = await fetchGuards(taskKey);
  if (guardsResponse.error) {
    vscode.window.showErrorMessage(`Guards konnten nicht geladen werden: ${guardsResponse.error.message}`);
    return;
  }

  const guards = (guardsResponse.data?.guards ?? [])
    .filter(guard => guard.scope === 'task')
    .filter(guard => !['passed', 'skipped'].includes(guard.status));

  if (guards.length === 0) {
    vscode.window.showInformationMessage(`Keine offenen task-spezifischen Guards für ${taskKey}.`);
    return;
  }

  let reported = 0;
  for (const guard of guards) {
    const status = await askGuardStatus(taskKey, guard);
    if (!status) {
      break;
    }

    const defaultText = `Guard ${guard.title} via VS Code (${status})`;
    const resultText = await vscode.window.showInputBox({
      title: `${taskKey}: Guard-Result`,
      prompt: `Result-Text für Guard "${guard.title}"`,
      value: defaultText,
      ignoreFocusOut: true,
    });
    if (resultText === undefined) {
      break;
    }

    const report = await reportGuardResult(taskKey, guard.guard_id, status, resultText);
    if (report.error) {
      vscode.window.showErrorMessage(`Guard "${guard.title}" konnte nicht gemeldet werden: ${report.error.message}`);
      continue;
    }
    reported += 1;
  }

  guardStatusProvider.setTask(taskKey);
  if (reported > 0) {
    vscode.window.showInformationMessage(`${reported} Guard-Result(s) für ${taskKey} gemeldet.`);
  }
}

async function askGuardStatus(
  taskKey: string,
  guard: HivemindTaskGuard
): Promise<'passed' | 'failed' | 'skipped' | undefined> {
  const options: Array<{ label: string; value: 'passed' | 'failed' | 'skipped'; description: string }> = [
    { label: 'Passed', value: 'passed', description: 'Guard erfolgreich' },
    { label: 'Failed', value: 'failed', description: 'Guard fehlgeschlagen' },
  ];
  if (guard.skippable) {
    options.push({ label: 'Skipped', value: 'skipped', description: 'Guard überspringen' });
  }

  const picked = await vscode.window.showQuickPick(options, {
    title: `${taskKey}: ${guard.title}`,
    placeHolder: `Guard-Status wählen (aktuell: ${guard.status})`,
    ignoreFocusOut: true,
  });
  return picked?.value;
}

async function submitResultDialog(
  activeTasksProvider: ActiveTasksProvider,
  guardStatusProvider: GuardStatusProvider
): Promise<void> {
  const suggestedTask = activeTaskKey ?? activeTasksProvider.getTasks()[0]?.task_key ?? '';
  const taskKey = await vscode.window.showInputBox({
    title: 'Hivemind Submit Result',
    prompt: 'Task-Key',
    value: suggestedTask,
    placeHolder: 'TASK-IDE-003',
    ignoreFocusOut: true,
  });
  if (!taskKey) {
    return;
  }

  const resultText = await vscode.window.showInputBox({
    title: 'Hivemind Submit Result',
    prompt: `Ergebnistext für ${taskKey}`,
    placeHolder: 'Kurzfassung der Umsetzung...',
    ignoreFocusOut: true,
  });
  if (!resultText) {
    return;
  }

  const response = await submitTaskResult(taskKey, resultText);
  if (response.error) {
    vscode.window.showErrorMessage(`submit_result fehlgeschlagen: ${response.error.message}`);
    return;
  }

  setActiveTask(taskKey, activeRole, guardStatusProvider);
  vscode.window.showInformationMessage(`Result für ${taskKey} gespeichert. Danach Task-State auf in_review setzen.`);
}

async function openTaskDetails(taskKey: string): Promise<void> {
  const [taskResponse, guardsResponse] = await Promise.all([fetchTask(taskKey), fetchGuards(taskKey)]);

  if (!taskDetailsPanel) {
    taskDetailsPanel = vscode.window.createWebviewPanel(
      'hivemind.taskDetails',
      `Hivemind ${taskKey}`,
      vscode.ViewColumn.Beside,
      { enableCommandUris: true }
    );
    taskDetailsPanel.onDidDispose(() => {
      taskDetailsPanel = undefined;
    });
  } else {
    taskDetailsPanel.title = `Hivemind ${taskKey}`;
    taskDetailsPanel.reveal(vscode.ViewColumn.Beside, true);
  }

  const task = taskResponse.data;
  const guards = guardsResponse.data?.guards ?? [];
  taskDetailsPanel.webview.html = renderTaskDetailsHtml(taskKey, task, guards, taskResponse.error?.message);
}

function renderTaskDetailsHtml(
  taskKey: string,
  task: unknown,
  guards: HivemindTaskGuard[],
  errorMessage?: string
): string {
  const taskObj = asObject(task);
  const title = escapeHtml(getString(taskObj?.title) ?? taskKey);
  const state = escapeHtml(getString(taskObj?.state) ?? 'unknown');
  const description = escapeHtml(getString(taskObj?.description) ?? 'Keine Beschreibung');
  const dodCriteria = parseDodCriteria(taskObj?.definition_of_done);
  const dodHtml = dodCriteria.length > 0
    ? dodCriteria.map(item => `<li>${escapeHtml(item)}</li>`).join('')
    : '<li>Keine DoD-Kriterien hinterlegt.</li>';
  const guardRows = guards.length > 0
    ? guards.map(guard => `<tr><td>${escapeHtml(guard.title)}</td><td>${escapeHtml(guard.status)}</td><td>${escapeHtml(guard.scope ?? 'n/a')}</td></tr>`).join('')
    : '<tr><td colspan="3">Keine Guards</td></tr>';

  const chatQuery = encodeURIComponent(JSON.stringify([{ query: `@hivemind task ${taskKey}` }]));
  const chatCommandUri = `command:workbench.action.chat.open?${chatQuery}`;

  const errorSection = errorMessage
    ? `<p style="color:#c62828;"><strong>Fehler:</strong> ${escapeHtml(errorMessage)}</p>`
    : '';

  return `<!doctype html>
<html lang="de">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(taskKey)}</title>
  <style>
    body { font-family: "Segoe UI", sans-serif; padding: 16px; color: var(--vscode-foreground); background: var(--vscode-editor-background); }
    h1 { margin: 0 0 8px 0; font-size: 20px; }
    .meta { color: var(--vscode-descriptionForeground); margin-bottom: 12px; }
    .block { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--vscode-panel-border); font-size: 12px; }
    a.button { display: inline-block; padding: 6px 10px; border-radius: 6px; text-decoration: none; color: var(--vscode-button-foreground); background: var(--vscode-button-background); }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <p class="meta"><strong>${escapeHtml(taskKey)}</strong> • State: <strong>${state}</strong></p>
  ${errorSection}
  <p><a class="button" href="${chatCommandUri}">Im Copilot Chat öffnen</a></p>

  <section class="block">
    <h2>Beschreibung</h2>
    <p>${description}</p>
  </section>

  <section class="block">
    <h2>Definition of Done</h2>
    <ul>${dodHtml}</ul>
  </section>

  <section class="block">
    <h2>Guard Status</h2>
    <table>
      <thead><tr><th>Guard</th><th>Status</th><th>Scope</th></tr></thead>
      <tbody>${guardRows}</tbody>
    </table>
  </section>
</body>
</html>`;
}

function parseDodCriteria(raw: unknown): string[] {
  const parsed = asObject(raw);
  const criteria = parsed?.criteria;
  if (!Array.isArray(criteria)) {
    return [];
  }
  return criteria.map(item => String(item));
}

function asObject(value: unknown): JsonObject | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }
  return value as JsonObject;
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function isTaskKey(value: unknown): value is string {
  return typeof value === 'string' && /^TASK-/i.test(value);
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}
