"use strict";
/**
 * Hivemind Backend API Client — TASK-IDE-003
 *
 * Minimal HTTP client for the Hivemind backend.
 * Uses the VS Code workspace settings for the base URL.
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
exports.fetchActiveTasks = fetchActiveTasks;
exports.fetchPendingDispatches = fetchPendingDispatches;
exports.fetchNextPrompt = fetchNextPrompt;
exports.fetchPromptForTask = fetchPromptForTask;
exports.fetchTask = fetchTask;
exports.fetchGuards = fetchGuards;
exports.reportGuardResult = reportGuardResult;
exports.submitTaskResult = submitTaskResult;
exports.acknowledgeDispatch = acknowledgeDispatch;
exports.markDispatchRunning = markDispatchRunning;
exports.completeDispatch = completeDispatch;
exports.reportDispatchProgress = reportDispatchProgress;
exports.fetchGovernanceConfig = fetchGovernanceConfig;
exports.fetchAuditEntries = fetchAuditEntries;
exports.checkHealth = checkHealth;
const vscode = __importStar(require("vscode"));
function getBaseUrl() {
    return vscode.workspace
        .getConfiguration('hivemind')
        .get('url', 'http://localhost:8000');
}
async function apiFetch(path, options) {
    const url = `${getBaseUrl()}${path}`;
    const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
        ...options,
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText} — ${url}`);
    }
    return response.json();
}
function withQuery(path, query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
        if (value === undefined)
            continue;
        params.set(key, String(value));
    }
    const suffix = params.toString();
    return suffix ? `${path}?${suffix}` : path;
}
function parseMcpEnvelope(envelope) {
    const firstText = envelope.result?.find(part => typeof part.text === 'string')?.text;
    if (!firstText) {
        return {
            error: {
                code: 'invalid_mcp_response',
                message: 'MCP response contained no text payload.',
            },
        };
    }
    try {
        const parsed = JSON.parse(firstText);
        if (parsed.error) {
            return {
                error: {
                    code: parsed.error.code ?? 'mcp_error',
                    message: parsed.error.message ?? 'Unknown MCP error',
                },
            };
        }
        return { data: parsed.data };
    }
    catch {
        return {
            error: {
                code: 'invalid_mcp_json',
                message: 'Failed to parse MCP tool payload as JSON.',
            },
        };
    }
}
async function callMcpTool(tool, args) {
    try {
        const envelope = await apiFetch('/api/mcp/call', {
            method: 'POST',
            body: JSON.stringify({ tool, arguments: args }),
        });
        return parseMcpEnvelope(envelope);
    }
    catch (err) {
        return {
            error: {
                code: 'http_error',
                message: String(err),
            },
        };
    }
}
/** Fetch active in-progress tasks with epic metadata */
async function fetchActiveTasks() {
    const tasksResult = await callMcpTool('hivemind/list_tasks', {
        state: 'in_progress',
        limit: 50,
        offset: 0,
    });
    if (tasksResult.error || !tasksResult.data?.data) {
        return [];
    }
    const tasks = tasksResult.data.data;
    if (tasks.length === 0) {
        return [];
    }
    const epicResult = await callMcpTool('hivemind/list_epics', {
        limit: 200,
        offset: 0,
    });
    const epicMap = new Map();
    if (!epicResult.error && epicResult.data?.data) {
        for (const epic of epicResult.data.data) {
            epicMap.set(epic.id, epic);
        }
    }
    return tasks.map(task => {
        const epic = epicMap.get(task.epic_id);
        return {
            task_key: task.task_key,
            title: task.title,
            state: task.state,
            epic_key: epic?.epic_key ?? task.epic_id,
            priority: epic?.priority ?? 'n/a',
            updated_at: task.created_at,
        };
    });
}
/** Fetch pending dispatches (TASK-IDE-005: execution_mode=ide) */
async function fetchPendingDispatches() {
    try {
        const data = await apiFetch('/api/conductor/dispatches/pending');
        return data.data ?? [];
    }
    catch {
        return [];
    }
}
/** Generate the next prompt */
async function fetchNextPrompt() {
    return callMcpTool('hivemind/get_prompt', { type: 'worker' });
}
/** Generate prompt for a specific task and type */
async function fetchPromptForTask(promptType, taskKey) {
    const args = { type: promptType };
    if (taskKey) {
        args.task_key = taskKey;
        args.task_id = taskKey; // backward-compatible with current backend prompt tool
    }
    return callMcpTool('hivemind/get_prompt', args);
}
/** Fetch task details (state, DoD, guards) */
async function fetchTask(taskKey) {
    return callMcpTool('hivemind/get_task', { task_key: taskKey });
}
/** Fetch full guard list for task */
async function fetchGuards(taskKey) {
    return callMcpTool('hivemind/get_guards', { task_key: taskKey });
}
/** Report guard result */
async function reportGuardResult(taskKey, guardId, status, result) {
    return callMcpTool('hivemind/report_guard_result', {
        task_key: taskKey,
        guard_id: guardId,
        status,
        result,
    });
}
/** Submit task result via worker write-tool */
async function submitTaskResult(taskKey, result, artifacts = []) {
    return callMcpTool('hivemind/submit_result', {
        task_key: taskKey,
        result,
        artifacts,
    });
}
/** Acknowledge an IDE dispatch */
async function acknowledgeDispatch(dispatchId) {
    await apiFetch(`/api/conductor/dispatches/${dispatchId}/acknowledge`, { method: 'POST' });
}
/** Mark an IDE dispatch as running */
async function markDispatchRunning(dispatchId) {
    await apiFetch(`/api/conductor/dispatches/${dispatchId}/running`, { method: 'POST' });
}
/** Complete an IDE dispatch */
async function completeDispatch(dispatchId, result, status = 'completed') {
    await apiFetch(`/api/conductor/dispatches/${dispatchId}/complete`, {
        method: 'POST',
        body: JSON.stringify({ status, result }),
    });
}
/** Report IDE dispatch execution progress */
async function reportDispatchProgress(dispatchId, event) {
    await apiFetch(`/api/conductor/dispatches/${dispatchId}/progress`, {
        method: 'POST',
        body: JSON.stringify(event),
    });
}
/** Fetch governance configuration from backend */
async function fetchGovernanceConfig() {
    try {
        return await apiFetch('/api/settings/governance');
    }
    catch {
        return undefined;
    }
}
/** Fetch recent audit entries (used to infer MCP tool activity in IDE flows) */
async function fetchAuditEntries(fromIso, pageSize = 50) {
    try {
        const path = withQuery('/api/audit', {
            from: fromIso,
            page_size: pageSize,
            page: 1,
        });
        const data = await apiFetch(path);
        return data.data ?? [];
    }
    catch {
        return [];
    }
}
/** Health check */
async function checkHealth() {
    try {
        await apiFetch('/health');
        return true;
    }
    catch {
        return false;
    }
}
//# sourceMappingURL=api.js.map