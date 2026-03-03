"use strict";
/**
 * Hivemind Status Bar Item — TASK-IDE-003
 *
 * Shows connection status and active task count in the VS Code status bar.
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
exports.HivemindStatusBar = void 0;
const vscode = __importStar(require("vscode"));
class HivemindStatusBar {
    item;
    constructor() {
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
        this.item.command = 'hivemind.nextPrompt';
        this.setDisconnected();
        this.item.show();
    }
    setConnected(activeTaskCount, activeTaskKey, role = 'worker') {
        if (activeTaskKey) {
            this.item.text = `$(sync~spin) Hivemind: [${role}] ${activeTaskKey}`;
            this.item.tooltip = `Aktiver Task: ${activeTaskKey} (${role})`;
        }
        else {
            this.item.text = `$(beaker) Hivemind: ${activeTaskCount} in_progress`;
            this.item.tooltip = 'Hivemind verbunden — klicken für nächsten Prompt';
        }
        this.item.backgroundColor = undefined;
    }
    setActiveTask(taskKey, role) {
        this.setConnected(1, taskKey, role);
    }
    setDisconnected() {
        this.item.text = '$(beaker) Hivemind: offline';
        this.item.tooltip = 'Hivemind nicht erreichbar — Backend läuft?';
        this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
    dispose() {
        this.item.dispose();
    }
}
exports.HivemindStatusBar = HivemindStatusBar;
//# sourceMappingURL=statusBar.js.map