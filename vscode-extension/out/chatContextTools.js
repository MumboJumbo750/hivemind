"use strict";
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
exports.registerChatContextTools = registerChatContextTools;
const vscode = __importStar(require("vscode"));
const api_1 = require("./api");
function asToolResult(payload) {
    const text = JSON.stringify(payload, null, 2);
    return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(text)]);
}
function registerChatContextTools(context) {
    if (!('lm' in vscode)) {
        return;
    }
    const activeTaskTool = vscode.lm.registerTool('hivemind.activeTask', {
        async invoke() {
            const tasks = await (0, api_1.fetchActiveTasks)();
            const current = tasks.find(t => t.state === 'in_progress') ?? tasks[0];
            if (!current) {
                return asToolResult({
                    data: null,
                    message: 'No active Hivemind task found.',
                });
            }
            const details = await (0, api_1.fetchTask)(current.task_key);
            return asToolResult({
                data: {
                    task_key: current.task_key,
                    title: current.title,
                    state: current.state,
                    epic_key: current.epic_key ?? null,
                    details: details.data ?? null,
                },
            });
        },
    });
    const activeEpicTool = vscode.lm.registerTool('hivemind.activeEpic', {
        async invoke() {
            const tasks = await (0, api_1.fetchActiveTasks)();
            const current = tasks.find(t => t.state === 'in_progress') ?? tasks[0];
            if (!current) {
                return asToolResult({
                    data: null,
                    message: 'No active Hivemind epic found.',
                });
            }
            const details = await (0, api_1.fetchTask)(current.task_key);
            return asToolResult({
                data: {
                    epic_key: current.epic_key ?? null,
                    epic_id: details.data?.epic_id ?? null,
                    source_task_key: current.task_key,
                    source_task_title: current.title,
                    source_task_state: current.state,
                },
            });
        },
    });
    context.subscriptions.push(activeTaskTool, activeEpicTool);
}
//# sourceMappingURL=chatContextTools.js.map