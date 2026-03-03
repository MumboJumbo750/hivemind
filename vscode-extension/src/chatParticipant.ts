/**
 * Hivemind Chat Participant — @hivemind (TASK-IDE-004)
 *
 * Registers @hivemind in Copilot Chat with subcommands:
 *   @hivemind next        — naechsten Dispatch-Prompt anzeigen
 *   @hivemind task KEY    — Task-Details + Worker-Prompt
 *   @hivemind guard       — Guards ausfuehren
 *   @hivemind health      — Health-Status
 *   @hivemind kartograph  — Kartograph-Session
 *
 * Important: @hivemind is an entry point that routes the user to the correct
 * Agent Mode prompt. The actual execution remains in Copilot Agent Mode + MCP-Tools.
 */

import * as vscode from 'vscode';
import { exec as execCb } from 'node:child_process';
import { promisify } from 'node:util';
import {
  checkHealth,
  fetchActiveTasks,
  fetchGuards,
  fetchNextPrompt,
  fetchPromptForTask,
  fetchTask,
  reportGuardResult,
  type HivemindTask,
  type HivemindTaskGuard,
} from './api';

const PARTICIPANT_ID = 'hivemind';
const execAsync = promisify(execCb);

type ChatHandler = vscode.ChatRequestHandler;
type ChatProgress = vscode.Progress<{ message?: string }>;

function md(text: string): vscode.MarkdownString {
  const s = new vscode.MarkdownString(text);
  s.isTrusted = {
    enabledCommands: [
      'hivemind.nextPrompt',
      'hivemind.openTask',
      'hivemind.runGuard',
      'hivemind.submitResult',
      'hivemind.executeDispatch',
      'hivemind.refresh',
    ],
  };
  return s;
}

function createProgressReporter(stream: vscode.ChatResponseStream): ChatProgress {
  return {
    report: value => {
      if (value.message) {
        stream.progress(value.message);
      }
    },
  };
}

function truncate(text: string, maxLength = 3_000): string {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}\n\n... (truncated)`;
}

function escapeCodeBlock(text: string): string {
  return text.replace(/```/g, '` ` `');
}

function parseKey(text: string, prefix: 'TASK' | 'EPIC'): string | undefined {
  const pattern = new RegExp(`\\b${prefix}-[A-Z0-9-]+\\b`, 'i');
  const match = text.match(pattern);
  return match?.[0]?.toUpperCase();
}

function parseHashVariable(text: string, name: 'task' | 'epic'): string | undefined {
  const pattern = new RegExp(`#hivemind:${name}\\s*=\\s*([A-Za-z0-9-]+)`, 'i');
  const match = text.match(pattern);
  return match?.[1]?.toUpperCase();
}

function referenceValueToText(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value instanceof vscode.Uri) {
    return value.toString();
  }
  if (value instanceof vscode.Location) {
    return value.uri.toString();
  }
  return String(value ?? '');
}

function resolveTaskKeyFromRequest(
  request: vscode.ChatRequest,
  activeTasks: HivemindTask[]
): string | undefined {
  const promptTask = parseKey(request.prompt, 'TASK') ?? parseHashVariable(request.prompt, 'task');
  if (promptTask) {
    return promptTask;
  }

  const refTask = request.references
    .map(ref => referenceValueToText(ref.value))
    .map(value => parseKey(value, 'TASK'))
    .find(Boolean);
  if (refTask) {
    return refTask;
  }

  return activeTasks.find(t => t.state === 'in_progress')?.task_key ?? activeTasks[0]?.task_key;
}

function resolveEpicKeyFromRequest(request: vscode.ChatRequest): string | undefined {
  const promptEpic = parseKey(request.prompt, 'EPIC') ?? parseHashVariable(request.prompt, 'epic');
  if (promptEpic) {
    return promptEpic;
  }

  return request.references
    .map(ref => referenceValueToText(ref.value))
    .map(value => parseKey(value, 'EPIC'))
    .find(Boolean);
}

async function runShellCommand(command: string, cwd: string, timeoutMs = 180_000): Promise<{
  exitCode: number;
  stdout: string;
  stderr: string;
}> {
  try {
    const { stdout, stderr } = await execAsync(command, {
      cwd,
      timeout: timeoutMs,
      windowsHide: true,
      maxBuffer: 4 * 1024 * 1024,
    });
    return { exitCode: 0, stdout: String(stdout), stderr: String(stderr) };
  } catch (err) {
    const e = err as { code?: number | string; stdout?: string; stderr?: string; message?: string };
    return {
      exitCode: typeof e.code === 'number' ? e.code : 1,
      stdout: String(e.stdout ?? ''),
      stderr: String(e.stderr ?? e.message ?? 'Command failed'),
    };
  }
}

async function summarizeWithModel(
  model: vscode.LanguageModelChat,
  prompt: string,
  token: vscode.CancellationToken
): Promise<string | undefined> {
  try {
    const response = await model.sendRequest([vscode.LanguageModelChatMessage.User(prompt)], {}, token);
    let out = '';
    for await (const chunk of response.text) {
      out += chunk;
    }
    const trimmed = out.trim();
    return trimmed || undefined;
  } catch {
    return undefined;
  }
}

function renderTaskHeader(taskKey: string, state?: string, title?: string): string {
  const label = title ? ` — ${title}` : '';
  const stateSuffix = state ? ` *(${state})*` : '';
  return `## Task \`${taskKey}\`${label}${stateSuffix}`;
}

async function handleNext(
  progress: ChatProgress,
  stream: vscode.ChatResponseStream
): Promise<void> {
  progress.report({ message: 'Naechsten Dispatch ermitteln...' });

  try {
    const result = await fetchNextPrompt();
    if (result.error) {
      stream.markdown(md(`**Fehler:** ${result.error.message}`));
      return;
    }
    if (!result.data) {
      stream.markdown(md('Kein anstehender Dispatch gefunden.'));
      return;
    }

    const { prompt_type, prompt, token_count } = result.data;
    stream.markdown(md(`## Hivemind Dispatch: \`${prompt_type}\``));
    stream.markdown(md(`*Token-Count: ${token_count}*`));
    stream.markdown(md('---'));
    stream.markdown(md(`\`\`\`\n${escapeCodeBlock(prompt)}\n\`\`\``));
    stream.button({
      command: 'hivemind.nextPrompt',
      title: '$(debug-start) In Agent Mode ausfuehren',
    });
  } catch (err) {
    stream.markdown(md(`**Fehler beim Abrufen:** ${err}`));
  }
}

async function handleTask(
  request: vscode.ChatRequest,
  progress: ChatProgress,
  stream: vscode.ChatResponseStream,
  taskKeyArg?: string
): Promise<string | undefined> {
  const activeTasks = await fetchActiveTasks();
  const taskKey = taskKeyArg ?? resolveTaskKeyFromRequest(request, activeTasks);

  if (!taskKey) {
    stream.markdown(md('**Usage:** `@hivemind task TASK-42`'));
    return undefined;
  }

  progress.report({ message: `Task ${taskKey} laden...` });

  try {
    const [taskResult, promptResult] = await Promise.all([
      fetchTask(taskKey),
      fetchPromptForTask('worker', taskKey),
    ]);

    if (taskResult.error) {
      stream.markdown(md(`**Fehler (Task):** ${taskResult.error.message}`));
      return undefined;
    }
    if (promptResult.error) {
      stream.markdown(md(`**Fehler (Prompt):** ${promptResult.error.message}`));
      return undefined;
    }

    const task = taskResult.data;
    if (!task) {
      stream.markdown(md(`Task \`${taskKey}\` nicht gefunden.`));
      return undefined;
    }
    if (!promptResult.data) {
      stream.markdown(md(`Kein Worker-Prompt fuer \`${taskKey}\` verfuegbar.`));
      return undefined;
    }

    stream.markdown(md(renderTaskHeader(task.task_key, task.state, task.title)));
    if (task.description) {
      stream.markdown(md(task.description));
    }

    const criteria = task.definition_of_done?.criteria ?? [];
    if (criteria.length > 0) {
      const criteriaLines = criteria.map(line => `- ${line}`).join('\n');
      stream.markdown(md(`**Definition of Done**\n${criteriaLines}`));
    }

    if (task.guards?.length) {
      const guardSummary = task.guards
        .map(g => `- \`${g.title}\` (${g.status})`)
        .join('\n');
      stream.markdown(md(`**Guards (${task.guards.length})**\n${guardSummary}`));
    }

    stream.markdown(md(`\n## Worker-Prompt fuer \`${task.task_key}\``));
    stream.markdown(md(`*${promptResult.data.token_count} Tokens*`));
    stream.markdown(md('---'));
    stream.markdown(md(`\`\`\`\n${escapeCodeBlock(promptResult.data.prompt)}\n\`\`\``));
    stream.button({
      command: 'hivemind.nextPrompt',
      title: '$(debug-start) In Agent Mode oeffnen',
    });
    return task.task_key;
  } catch (err) {
    stream.markdown(md(`**Fehler:** ${err}`));
    return undefined;
  }
}

async function handleStatus(progress: ChatProgress, stream: vscode.ChatResponseStream): Promise<string | undefined> {
  progress.report({ message: 'Hivemind Status laden...' });

  try {
    const [healthy, tasks] = await Promise.all([checkHealth(), fetchActiveTasks()]);

    stream.markdown(md('## Hivemind Status'));
    stream.markdown(md(`**Backend:** ${healthy ? 'Online' : 'Offline'}`));

    if (tasks.length === 0) {
      stream.markdown(md('**Aktive Tasks:** keine'));
    } else {
      const lines = tasks
        .slice(0, 10)
        .map(t => `- \`${t.task_key}\` — ${t.title} *(${t.state})*`)
        .join('\n');
      stream.markdown(md(`**Aktive Tasks (${tasks.length}):**\n${lines}`));
    }

    const latest = tasks
      .map(t => t.updated_at)
      .filter((v): v is string => typeof v === 'string')
      .sort((a, b) => Date.parse(b) - Date.parse(a))[0];

    if (latest) {
      stream.markdown(md(`**Letzte Aktivitaet:** ${new Date(latest).toLocaleString('de-DE')}`));
    }

    return tasks.find(t => t.state === 'in_progress')?.task_key ?? tasks[0]?.task_key;
  } catch (err) {
    stream.markdown(md(`**Fehler:** ${err}`));
    return undefined;
  }
}

async function handleKartograph(
  request: vscode.ChatRequest,
  progress: ChatProgress,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken
): Promise<void> {
  progress.report({ message: 'Kartograph-Prompt laden...' });

  try {
    const result = await fetchPromptForTask('kartograph', '');
    if (!result.data?.prompt) {
      stream.markdown(md('Kein Kartograph-Prompt verfuegbar — kein offener Explore-Task?'));
      return;
    }

    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
    const repoContext = `Workspace-Pfad: ${workspaceRoot}\n\n`;
    const fullPrompt = repoContext + result.data.prompt;

    stream.markdown(md('## Kartograph-Session gestartet'));
    stream.markdown(md(`*Workspace: \`${workspaceRoot}\` • ${result.data.token_count} Tokens*`));
    stream.markdown(md('---'));

    // Prompt ans Modell schicken — Kartograph führt die Analyse tatsächlich aus
    const messages = [vscode.LanguageModelChatMessage.User(fullPrompt)];
    const response = await request.model.sendRequest(messages, {}, token);
    for await (const chunk of response.text) {
      stream.markdown(new vscode.MarkdownString(chunk));
    }
  } catch (err) {
    stream.markdown(md(`**Fehler:** ${err}`));
  }
}

async function handleHealth(
  request: vscode.ChatRequest,
  progress: ChatProgress,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken
): Promise<void> {
  progress.report({ message: 'Backend-Health pruefen...' });
  const backendHealthy = await checkHealth();

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceRoot) {
    stream.markdown(md('Kein Workspace geoeffnet. `make health` kann nicht ausgefuehrt werden.'));
    stream.markdown(md(`**Backend:** ${backendHealthy ? 'Online' : 'Offline'}`));
    return;
  }

  progress.report({ message: 'Repo-Health (`make health`) ausfuehren...' });
  const healthRun = await runShellCommand('make health', workspaceRoot);
  const rawOutput = `${healthRun.stdout}\n${healthRun.stderr}`.trim();
  const compactOutput = truncate(rawOutput || 'Keine Ausgabe', 6_000);

  stream.markdown(md('## Health Report'));
  stream.markdown(md(`**Backend:** ${backendHealthy ? 'Online' : 'Offline'}`));
  stream.markdown(md(`**make health Exit-Code:** \`${healthRun.exitCode}\``));
  stream.markdown(md(`\`\`\`\n${escapeCodeBlock(compactOutput)}\n\`\`\``));

  const summary = await summarizeWithModel(
    request.model,
    [
      'Fasse die Health-Ausgabe in maximal 5 Bullet-Points zusammen.',
      'Kategorisiere in Fehler, Warnungen, Hinweise.',
      'Wenn kein Finding erkennbar ist, sage das explizit.',
      '',
      compactOutput,
    ].join('\n'),
    token
  );

  if (summary) {
    stream.markdown(md(`### AI-Zusammenfassung\n${summary}`));
  }
}

async function executeGuardForTask(
  progress: ChatProgress,
  stream: vscode.ChatResponseStream,
  guard: HivemindTaskGuard,
  taskKey: string,
  cwd: string
): Promise<{ title: string; status: 'passed' | 'failed' | 'skipped'; reported: boolean }> {
  progress.report({ message: `Guard pruefen: ${guard.title}` });

  let status: 'passed' | 'failed' | 'skipped';
  let resultText: string;

  if (guard.command) {
    const execution = await runShellCommand(guard.command, cwd);
    status = execution.exitCode === 0 ? 'passed' : 'failed';
    resultText = truncate(
      [
        `command: ${guard.command}`,
        `exit_code: ${execution.exitCode}`,
        '',
        'stdout:',
        execution.stdout.trim() || '(empty)',
        '',
        'stderr:',
        execution.stderr.trim() || '(empty)',
      ].join('\n'),
      3_000
    );
  } else if (guard.skippable) {
    status = 'skipped';
    resultText = 'Guard hat keinen ausfuehrbaren Command im Scope; als skipped gemeldet.';
  } else {
    status = 'failed';
    resultText = 'Guard hat keinen ausfuehrbaren Command und ist nicht skippable.';
  }

  const reportResult = await reportGuardResult(taskKey, guard.guard_id, status, resultText);
  if (reportResult.error) {
    stream.markdown(md(`- FAIL \`${guard.title}\`: Report fehlgeschlagen (${reportResult.error.message})`));
    return { title: guard.title, status, reported: false };
  }
  stream.markdown(md(`- ${status.toUpperCase()} \`${guard.title}\``));
  return { title: guard.title, status, reported: true };
}

async function handleGuard(
  request: vscode.ChatRequest,
  progress: ChatProgress,
  stream: vscode.ChatResponseStream
): Promise<string | undefined> {
  const activeTasks = await fetchActiveTasks();
  const taskKey = resolveTaskKeyFromRequest(request, activeTasks);
  if (!taskKey) {
    stream.markdown(md('Kein Task-Kontext gefunden. Nutzung: `@hivemind guard TASK-KEY` oder `#hivemind:task=TASK-...`.'));
    return undefined;
  }

  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspaceRoot) {
    stream.markdown(md('Kein Workspace geoeffnet, Guard-Commands koennen nicht ausgefuehrt werden.'));
    return taskKey;
  }

  progress.report({ message: `Guards fuer ${taskKey} laden...` });
  const guardsResult = await fetchGuards(taskKey);
  if (guardsResult.error) {
    stream.markdown(md(`**Fehler:** ${guardsResult.error.message}`));
    return taskKey;
  }

  const guards = guardsResult.data?.guards ?? [];
  const taskScopedGuards = guards.filter(g => g.scope === 'task');

  stream.markdown(md(`## Guard-Ausfuehrung fuer \`${taskKey}\``));
  if (taskScopedGuards.length === 0) {
    stream.markdown(md('Keine task-spezifischen Guards vorhanden.'));
    return taskKey;
  }

  const pendingGuards = taskScopedGuards.filter(g => !['passed', 'skipped'].includes(g.status));
  if (pendingGuards.length === 0) {
    stream.markdown(md('Alle task-spezifischen Guards sind bereits `passed` oder `skipped`.'));
    return taskKey;
  }

  stream.markdown(md(`Starte ${pendingGuards.length} Guard(s):`));
  const results: Array<{ title: string; status: 'passed' | 'failed' | 'skipped'; reported: boolean }> = [];
  for (const guard of pendingGuards) {
    const result = await executeGuardForTask(progress, stream, guard, taskKey, workspaceRoot);
    results.push(result);
  }

  const passed = results.filter(r => r.status === 'passed').length;
  const failed = results.filter(r => r.status === 'failed').length;
  const skipped = results.filter(r => r.status === 'skipped').length;
  const reported = results.filter(r => r.reported).length;
  stream.markdown(md(`\n**Summary:** ${passed} passed, ${failed} failed, ${skipped} skipped, ${reported}/${results.length} reported.`));

  return taskKey;
}

// ── Register Chat Participant ──────────────────────────────────────────────

export function registerChatParticipant(context: vscode.ExtensionContext): void {
  // Guard: chat API only available in recent VS Code versions
  if (!('chat' in vscode)) {
    return;
  }

  const handler: ChatHandler = async (request, _chatContext, stream, token) => {
    const progress = createProgressReporter(stream);
    const text = request.prompt.trim();
    const command = request.command?.toLowerCase();

    const activeTasks = await fetchActiveTasks();
    const promptTaskKey = parseKey(text, 'TASK');
    const taskKeyFromContext = resolveTaskKeyFromRequest(request, activeTasks);
    const taskKey = promptTaskKey ?? taskKeyFromContext;
    const epicKey = resolveEpicKeyFromRequest(request);
    let handledTaskKey = taskKey;

    if (command === 'next' || text.toLowerCase() === 'next') {
      await handleNext(progress, stream);
    } else if (command === 'task' || text.startsWith('task ')) {
      const explicitTaskKey = parseKey(text.replace(/^task\s+/i, '').trim(), 'TASK') ?? taskKey;
      handledTaskKey = await handleTask(request, progress, stream, explicitTaskKey);
    } else if (command === 'guard' || text.startsWith('guard ')) {
      handledTaskKey = await handleGuard(request, progress, stream);
    } else if (command === 'health') {
      await handleHealth(request, progress, stream, token);
    } else if (command === 'kartograph') {
      await handleKartograph(request, progress, stream, token);
    } else {
      handledTaskKey = await handleStatus(progress, stream);
      stream.markdown(md('\n---\n**Verfuegbare Subcommands:**'));
      stream.markdown(md('- `@hivemind next` — naechster Dispatch-Prompt'));
      stream.markdown(md('- `@hivemind task TASK-KEY` — Task-Details'));
      stream.markdown(md('- `@hivemind guard` — Guards ausfuehren'));
      stream.markdown(md('- `@hivemind health` — Status'));
      stream.markdown(md('- `@hivemind kartograph` — Kartograph-Session'));
    }

    return {
      metadata: {
        command: command ?? 'status',
        taskKey: handledTaskKey,
        epicKey,
      },
    };
  };

  const participant = (vscode as unknown as {
    chat: { createChatParticipant: (id: string, handler: ChatHandler) => vscode.ChatParticipant }
  }).chat.createChatParticipant(PARTICIPANT_ID, handler);

  participant.iconPath = new vscode.ThemeIcon('beaker');
  participant.followupProvider = {
    provideFollowups(result): vscode.ChatFollowup[] {
      const metadata = (result.metadata ?? {}) as { taskKey?: string };
      const taskKey = metadata.taskKey;
      return [
        {
          label: 'Task übernehmen',
          prompt: taskKey ? `task ${taskKey}` : 'next',
        },
        {
          label: 'Guard ausführen',
          prompt: taskKey ? `guard ${taskKey}` : 'guard',
        },
      ];
    },
  };

  context.subscriptions.push(participant);
}
