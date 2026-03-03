"use strict";
/**
 * Hivemind SSE Listener — TASK-IDE-003
 *
 * Connects to the backend SSE endpoints and forwards events to:
 * - AgentActivityProvider (live feed)
 * - Notification popups for important events
 *
 * Uses the native fetch() API with ReadableStream for SSE parsing.
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
exports.SseListener = void 0;
const vscode = __importStar(require("vscode"));
class SseListener {
    baseUrl;
    activityProvider;
    onEvent;
    abortController = null;
    reconnectTimer = null;
    endpoints;
    constructor(baseUrl, activityProvider, onEvent) {
        this.baseUrl = baseUrl;
        this.activityProvider = activityProvider;
        this.onEvent = onEvent;
        this.endpoints = [
            `${this.baseUrl}/api/events`,
            `${this.baseUrl}/api/events/tasks`,
            `${this.baseUrl}/api/events/notifications`,
            `${this.baseUrl}/api/events/triage`,
        ];
    }
    start() {
        this._connect();
    }
    stop() {
        this.abortController?.abort();
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }
    }
    async _connect() {
        this.abortController = new AbortController();
        try {
            let response;
            for (const url of this.endpoints) {
                response = await fetch(url, {
                    signal: this.abortController.signal,
                    headers: { Accept: 'text/event-stream' },
                });
                if (response.ok && response.body) {
                    break;
                }
            }
            if (!response?.ok || !response.body) {
                this._scheduleReconnect();
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done)
                    break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() ?? '';
                this._processLines(lines);
            }
            if (!this.abortController.signal.aborted) {
                this._scheduleReconnect();
            }
        }
        catch (err) {
            if (err?.name !== 'AbortError') {
                this._scheduleReconnect();
            }
        }
    }
    _processLines(lines) {
        let eventType = 'message';
        let dataLines = [];
        for (const rawLine of lines) {
            const line = rawLine.replace(/\r$/, '');
            if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
            }
            else if (line.startsWith('data:')) {
                dataLines.push(line.slice(5).trim());
            }
            else if (line === '') {
                // dispatch accumulated event
                if (dataLines.length > 0) {
                    const raw = dataLines.join('\n');
                    try {
                        const data = JSON.parse(raw);
                        this._handleEvent(eventType, data);
                    }
                    catch {
                        this._handleEvent(eventType, raw);
                    }
                    eventType = 'message';
                    dataLines = [];
                }
            }
        }
    }
    _handleEvent(eventType, data) {
        this.onEvent(eventType, data);
        const showNotifications = vscode.workspace
            .getConfiguration('hivemind')
            .get('notifications', true);
        const d = asObject(data);
        const msg = `${eventType}: ${getString(d?.task_key) ?? getString(d?.trigger_id) ?? getString(d?.type) ?? JSON.stringify(data).slice(0, 80)}`;
        this.activityProvider.addEvent(msg);
        if (!showNotifications)
            return;
        if (eventType === 'task_assigned') {
            const taskKey = getString(d?.task_key) ?? 'unknown';
            void vscode.window.showInformationMessage(`Hivemind: Task assigned (${taskKey})`, 'Task öffnen').then(action => {
                if (action) {
                    void vscode.commands.executeCommand('hivemind.openTask', taskKey);
                }
            });
            return;
        }
        if (eventType === 'notification_created') {
            const notifType = getString(d?.type);
            if (notifType === 'task_assigned' || notifType === 'review_requested') {
                const title = getString(d?.title) ?? notifType;
                void vscode.window.showInformationMessage(`Hivemind: ${title}`);
            }
            return;
        }
        if (eventType.startsWith('task_')) {
            const taskKey = getString(d?.task_key) ?? 'unknown';
            const newState = getString(d?.new_state) ?? getString(d?.state) ?? '';
            // Special handling: task moved to in_review → offer direct Review action
            if (newState === 'in_review' || eventType === 'task_in_review') {
                vscode.window.showInformationMessage(`Hivemind: ${taskKey} wartet auf Review`, 'Review starten', 'Approve', 'Task öffnen').then(action => {
                    if (action === 'Review starten') {
                        void vscode.commands.executeCommand('hivemind.openTask', taskKey);
                    }
                    else if (action === 'Approve') {
                        void vscode.commands.executeCommand('workbench.action.chat.open', {
                            query: `@hivemind /task ${taskKey}`,
                        });
                    }
                    else if (action === 'Task öffnen') {
                        void vscode.commands.executeCommand('hivemind.openTask', taskKey);
                    }
                });
                return;
            }
            void vscode.window.showInformationMessage(`Hivemind: ${eventType} (${taskKey})`);
            return;
        }
        if (eventType === 'conductor:dispatch' && isReviewDispatch(d)) {
            const triggerId = getString(d?.trigger_id) ?? 'Task';
            vscode.window.showInformationMessage(`Hivemind: Review benötigt (${triggerId})`, 'Review starten', 'Task öffnen').then(action => {
                if (action === 'Review starten') {
                    void vscode.commands.executeCommand('hivemind.nextPrompt');
                }
                else if (action === 'Task öffnen') {
                    void vscode.commands.executeCommand('hivemind.openTask', triggerId);
                }
            });
        }
    }
    _scheduleReconnect() {
        this.reconnectTimer = setTimeout(() => this._connect(), 5000);
    }
}
exports.SseListener = SseListener;
function asObject(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    return value;
}
function getString(value) {
    return typeof value === 'string' ? value : undefined;
}
function isReviewDispatch(eventData) {
    if (!eventData) {
        return false;
    }
    const promptType = getString(eventData.prompt_type)?.toLowerCase() ?? '';
    const triggerDetail = getString(eventData.trigger_detail)?.toLowerCase() ?? '';
    return promptType.includes('review') || triggerDetail.includes('in_progress->in_review');
}
//# sourceMappingURL=sseListener.js.map