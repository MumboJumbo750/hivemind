"use strict";
/**
 * Hivemind VS Code Extension — Entry Point (TASK-IDE-003)
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const api_1 = require("./api");
const autoExecute_1 = require("./autoExecute");
const chatParticipant_1 = require("./chatParticipant");
const chatContextTools_1 = require("./chatContextTools");
const sidebarProvider_1 = require("./sidebarProvider");
const sseListener_1 = require("./sseListener");
const statusBar_1 = require("./statusBar");
let sseListener = null;
let statusBar = null;
let refreshTimer = null;
let autoExecuteManager = null;
let activeTaskKey;
let activeRole = 'worker';
let taskDetailsPanel;
async function activate(context) {
    if (!(await workspaceHasHivemindServer())) {
        return;
    }
    const config = vscode.workspace.getConfiguration('hivemind');
    const autoConnect = config.get('autoConnect', true);
    const baseUrl = config.get('url', 'http://localhost:8000');
    const activeTasksProvider = new sidebarProvider_1.ActiveTasksProvider();
    const nextPromptsProvider = new sidebarProvider_1.NextPromptsProvider();
    const guardStatusProvider = new sidebarProvider_1.GuardStatusProvider();
    const agentActivityProvider = new sidebarProvider_1.AgentActivityProvider();
    context.subscriptions.push(vscode.window.registerTreeDataProvider('hivemind.activeTasks', activeTasksProvider), vscode.window.registerTreeDataProvider('hivemind.nextPrompts', nextPromptsProvider), vscode.window.registerTreeDataProvider('hivemind.guardStatus', guardStatusProvider), vscode.window.registerTreeDataProvider('hivemind.agentActivity', agentActivityProvider));
    autoExecuteManager = new autoExecute_1.AutoExecuteManager(agentActivityProvider);
    statusBar = new statusBar_1.HivemindStatusBar();
    context.subscriptions.push(statusBar);
    context.subscriptions.push(vscode.commands.registerCommand('hivemind.refresh', async () => {
        await refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar);
    }), vscode.commands.registerCommand('hivemind.nextPrompt', async () => {
        try {
            await vscode.commands.executeCommand('workbench.action.chat.open', {
                query: '/hivemind.next',
            });
        }
        catch {
            vscode.window.showInformationMessage('Copilot Chat öffnen und /hivemind.next eingeben.');
        }
    }), vscode.commands.registerCommand('hivemind.runGuard', async () => {
        await runGuardsForCurrentTask(activeTasksProvider, guardStatusProvider);
    }), vscode.commands.registerCommand('hivemind.submitResult', async () => {
        await submitResultDialog(activeTasksProvider, guardStatusProvider);
    }), vscode.commands.registerCommand('hivemind.openTask', async (taskKey) => {
        setActiveTask(taskKey, 'worker', guardStatusProvider);
        await openTaskDetails(taskKey);
    }), vscode.commands.registerCommand('hivemind.executeDispatch', async (dispatch) => {
        const parsed = dispatch;
        if (!parsed?.dispatch_id || !autoExecuteManager) {
            return;
        }
        if (isTaskKey(parsed.trigger_id)) {
            setActiveTask(parsed.trigger_id, parsed.agent_role ?? 'worker', guardStatusProvider);
        }
        statusBar?.setActiveTask(parsed.trigger_id ?? '?', parsed.agent_role ?? '?');
        await autoExecuteManager.handleDispatch(parsed, true);
    }));
    (0, chatParticipant_1.registerChatParticipant)(context);
    (0, chatContextTools_1.registerChatContextTools)(context);
    if (!autoConnect) {
        return;
    }
    await refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar);
    sseListener = new sseListener_1.SseListener(baseUrl, agentActivityProvider, (eventType, data) => {
        const payload = asObject(data);
        const eventTaskKey = getString(payload?.task_key);
        if (eventTaskKey) {
            setActiveTask(eventTaskKey, activeRole, guardStatusProvider);
        }
        if (eventType === 'conductor:dispatch') {
            const dispatch = payload;
            if (dispatch?.execution_mode === 'ide' && dispatch.dispatch_id) {
                if (isTaskKey(dispatch.trigger_id)) {
                    setActiveTask(dispatch.trigger_id, dispatch.agent_role ?? 'worker', guardStatusProvider);
                }
                void autoExecuteManager?.handleDispatch({
                    dispatch_id: dispatch.dispatch_id,
                    agent_role: dispatch.agent_role ?? 'worker',
                    prompt_type: dispatch.prompt_type ?? '',
                    trigger_id: dispatch.trigger_id ?? '',
                    prompt: dispatch.prompt,
                    execution_mode: 'ide',
                    status: dispatch.status ?? 'dispatched',
                }, false);
            }
        }
        if (shouldRefreshForEvent(eventType)) {
            void refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar);
        }
    });
    sseListener.start();
    refreshTimer = setInterval(() => {
        void refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, statusBar);
    }, 30_000);
}
function deactivate() {
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
async function workspaceHasHivemindServer() {
    const files = await vscode.workspace.findFiles('.vscode/mcp.json', '**/{node_modules,.git}/**', 1);
    if (files.length === 0) {
        return false;
    }
    try {
        const raw = await vscode.workspace.fs.readFile(files[0]);
        const json = JSON.parse(Buffer.from(raw).toString('utf8'));
        const serverMap = (json.servers ?? json.mcpServers);
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
    }
    catch {
        return false;
    }
    return false;
}
function setActiveTask(taskKey, role, guardStatusProvider) {
    activeTaskKey = taskKey;
    activeRole = role || 'worker';
    guardStatusProvider.setTask(taskKey);
    statusBar?.setActiveTask(taskKey, activeRole);
}
function shouldRefreshForEvent(eventType) {
    if (eventType === 'conductor:dispatch' || eventType === 'notification_created') {
        return true;
    }
    return eventType.startsWith('task_') || eventType === 'task_assigned';
}
async function refreshAll(activeTasksProvider, nextPromptsProvider, guardStatusProvider, status) {
    const healthy = await (0, api_1.checkHealth)();
    if (!healthy) {
        status.setDisconnected();
        return;
    }
    const [tasks, dispatches] = await Promise.all([(0, api_1.fetchActiveTasks)(), (0, api_1.fetchPendingDispatches)()]);
    activeTasksProvider.setTasks(tasks);
    nextPromptsProvider.setDispatches(dispatches);
    if (!activeTaskKey || !tasks.some(task => task.task_key === activeTaskKey)) {
        activeTaskKey = tasks[0]?.task_key;
        activeRole = 'worker';
    }
    if (guardStatusProvider.getCurrentTaskKey() !== activeTaskKey) {
        guardStatusProvider.setTask(activeTaskKey);
    }
    else {
        void guardStatusProvider.loadData();
    }
    status.setConnected(tasks.length, activeTaskKey, activeRole);
}
async function runGuardsForCurrentTask(activeTasksProvider, guardStatusProvider) {
    const taskKey = guardStatusProvider.getCurrentTaskKey() ?? activeTaskKey ?? activeTasksProvider.getTasks()[0]?.task_key;
    if (!taskKey) {
        vscode.window.showInformationMessage('Kein aktiver Task für Guard-Ausführung vorhanden.');
        return;
    }
    const guardsResponse = await (0, api_1.fetchGuards)(taskKey);
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
        const report = await (0, api_1.reportGuardResult)(taskKey, guard.guard_id, status, resultText);
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
async function askGuardStatus(taskKey, guard) {
    const options = [
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
async function submitResultDialog(activeTasksProvider, guardStatusProvider) {
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
    const response = await (0, api_1.submitTaskResult)(taskKey, resultText);
    if (response.error) {
        vscode.window.showErrorMessage(`submit_result fehlgeschlagen: ${response.error.message}`);
        return;
    }
    setActiveTask(taskKey, activeRole, guardStatusProvider);
    vscode.window.showInformationMessage(`Result für ${taskKey} gespeichert. Danach Task-State auf in_review setzen.`);
}
async function openTaskDetails(taskKey) {
    const [taskResponse, guardsResponse] = await Promise.all([(0, api_1.fetchTask)(taskKey), (0, api_1.fetchGuards)(taskKey)]);
    if (!taskDetailsPanel) {
        taskDetailsPanel = vscode.window.createWebviewPanel('hivemind.taskDetails', `Hivemind ${taskKey}`, vscode.ViewColumn.Beside, { enableCommandUris: true });
        taskDetailsPanel.onDidDispose(() => {
            taskDetailsPanel = undefined;
        });
    }
    else {
        taskDetailsPanel.title = `Hivemind ${taskKey}`;
        taskDetailsPanel.reveal(vscode.ViewColumn.Beside, true);
    }
    const task = taskResponse.data;
    const guards = guardsResponse.data?.guards ?? [];
    taskDetailsPanel.webview.html = renderTaskDetailsHtml(taskKey, task, guards, taskResponse.error?.message);
}
function renderTaskDetailsHtml(taskKey, task, guards, errorMessage) {
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
function parseDodCriteria(raw) {
    const parsed = asObject(raw);
    const criteria = parsed?.criteria;
    if (!Array.isArray(criteria)) {
        return [];
    }
    return criteria.map(item => String(item));
}
function asObject(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    return value;
}
function getString(value) {
    return typeof value === 'string' ? value : undefined;
}
function isTaskKey(value) {
    return typeof value === 'string' && /^TASK-/i.test(value);
}
function escapeHtml(value) {
    return value
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}
//# sourceMappingURL=extension.js.map