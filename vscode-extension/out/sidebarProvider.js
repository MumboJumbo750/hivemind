"use strict";
/**
 * Hivemind Sidebar TreeView Provider — TASK-IDE-003
 *
 * Provides four tree views:
 *   hivemind.activeTasks   — Tasks in in_progress with epic + priority
 *   hivemind.nextPrompts   — Pending conductor dispatches
 *   hivemind.guardStatus   — Guard results for the selected task
 *   hivemind.agentActivity — Recent dispatch/event activity
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
exports.AgentActivityProvider = exports.GuardStatusProvider = exports.NextPromptsProvider = exports.ActiveTasksProvider = exports.TaskItem = void 0;
const vscode = __importStar(require("vscode"));
const api_1 = require("./api");
class TaskItem extends vscode.TreeItem {
    task;
    constructor(task) {
        super(`${task.task_key} — ${task.title}`, vscode.TreeItemCollapsibleState.None);
        this.task = task;
        this.description = `${task.epic_key ?? 'EPIC-?'} • ${stateLabel(task.state)}`;
        this.tooltip = `${task.task_key}\nState: ${task.state}\nEpic: ${task.epic_key ?? 'n/a'}\nPriority: ${task.priority ?? 'n/a'}`;
        this.iconPath = stateIcon(task.state);
        // contextValue drives inline buttons in package.json view/item/context
        this.contextValue = `hivemind.task.${task.state}`;
        this.command = {
            command: 'hivemind.openTask',
            title: 'Task öffnen',
            arguments: [task.task_key],
        };
    }
}
exports.TaskItem = TaskItem;
function stateLabel(state) {
    switch (state) {
        case 'incoming': return '○ Incoming';
        case 'scoped': return '◌ Scoped';
        case 'ready': return '● Ready';
        case 'in_progress': return '◎ In Progress';
        case 'in_review': return '👁 In Review';
        default: return state;
    }
}
class DispatchItem extends vscode.TreeItem {
    constructor(dispatch) {
        super(`[${dispatch.agent_role.toUpperCase()}] ${dispatch.trigger_id}`, vscode.TreeItemCollapsibleState.None);
        this.description = `${dispatch.prompt_type} • ${dispatch.status}`;
        this.tooltip = `Dispatch: ${dispatch.dispatch_id}\nRole: ${dispatch.agent_role}\nMode: ${dispatch.execution_mode}\nStatus: ${dispatch.status}`;
        this.iconPath = new vscode.ThemeIcon('debug-start');
        this.contextValue = 'hivemind.dispatch';
        this.command = {
            command: 'hivemind.executeDispatch',
            title: 'Dispatch ausführen',
            arguments: [dispatch],
        };
    }
}
class GuardItem extends vscode.TreeItem {
    constructor(guard) {
        super(guard.title, vscode.TreeItemCollapsibleState.None);
        this.description = `${guard.status}${guard.scope ? ` • ${guard.scope}` : ''}`;
        this.tooltip = `${guard.title}\nStatus: ${guard.status}\nType: ${guard.type ?? 'n/a'}\nScope: ${guard.scope ?? 'n/a'}`;
        this.iconPath = guardStatusIcon(guard.status);
    }
}
class PlaceholderItem extends vscode.TreeItem {
    constructor(label) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.iconPath = new vscode.ThemeIcon('info');
    }
}
function stateIcon(state) {
    switch (state) {
        case 'incoming':
            return new vscode.ThemeIcon('inbox');
        case 'scoped':
            return new vscode.ThemeIcon('list-unordered');
        case 'ready':
            return new vscode.ThemeIcon('circle-filled');
        case 'in_progress':
            return new vscode.ThemeIcon('circle-outline');
        case 'in_review':
            return new vscode.ThemeIcon('eye');
        case 'qa_failed':
            return new vscode.ThemeIcon('error');
        default:
            return new vscode.ThemeIcon('circle-outline');
    }
}
function guardStatusIcon(status) {
    switch (status) {
        case 'passed':
            return new vscode.ThemeIcon('pass');
        case 'failed':
            return new vscode.ThemeIcon('error');
        case 'skipped':
            return new vscode.ThemeIcon('debug-step-over');
        case 'pending':
            return new vscode.ThemeIcon('clock');
        case 'inherited':
            return new vscode.ThemeIcon('symbol-property');
        default:
            return new vscode.ThemeIcon('question');
    }
}
class ActiveTasksProvider {
    onDidChangeTreeDataEmitter = new vscode.EventEmitter();
    onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;
    tasks = [];
    setTasks(tasks) {
        this.tasks = tasks;
        this.refresh();
    }
    getTasks() {
        return this.tasks;
    }
    async loadData() {
        this.setTasks(await (0, api_1.fetchActiveTasks)());
    }
    refresh() {
        this.onDidChangeTreeDataEmitter.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
        if (this.tasks.length === 0) {
            return [new PlaceholderItem('Keine Tasks (incoming / ready / in_progress / in_review)')];
        }
        return this.tasks.map(task => new TaskItem(task));
    }
}
exports.ActiveTasksProvider = ActiveTasksProvider;
class NextPromptsProvider {
    onDidChangeTreeDataEmitter = new vscode.EventEmitter();
    onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;
    dispatches = [];
    readyTasks = [];
    reviewTasks = [];
    setDispatches(dispatches) {
        this.dispatches = dispatches;
        this.refresh();
    }
    setTasks(allTasks) {
        this.readyTasks = allTasks.filter(t => t.state === 'ready');
        this.reviewTasks = allTasks.filter(t => t.state === 'in_review');
        this.refresh();
    }
    async loadData() {
        this.setDispatches(await (0, api_1.fetchPendingDispatches)());
    }
    refresh() {
        this.onDidChangeTreeDataEmitter.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
        const items = [];
        // Section: Pending dispatches
        if (this.dispatches.length > 0) {
            const header = new vscode.TreeItem('── Dispatches ──', vscode.TreeItemCollapsibleState.None);
            header.iconPath = new vscode.ThemeIcon('broadcast');
            items.push(header);
            items.push(...this.dispatches.map(d => new DispatchItem(d)));
        }
        // Section: Tasks waiting for review
        if (this.reviewTasks.length > 0) {
            const header = new vscode.TreeItem('── Review wartend ──', vscode.TreeItemCollapsibleState.None);
            header.iconPath = new vscode.ThemeIcon('eye');
            items.push(header);
            items.push(...this.reviewTasks.map(t => new TaskItem(t)));
        }
        // Section: Ready tasks (next work items)
        if (this.readyTasks.length > 0) {
            const header = new vscode.TreeItem('── Bereit zum Start ──', vscode.TreeItemCollapsibleState.None);
            header.iconPath = new vscode.ThemeIcon('play-circle');
            items.push(header);
            items.push(...this.readyTasks.map(t => new TaskItem(t)));
        }
        if (items.length === 0) {
            return [new PlaceholderItem('Keine anstehenden Aufgaben')];
        }
        return items;
    }
}
exports.NextPromptsProvider = NextPromptsProvider;
class GuardStatusProvider {
    onDidChangeTreeDataEmitter = new vscode.EventEmitter();
    onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;
    taskKey;
    guards = [];
    errorMessage;
    getCurrentTaskKey() {
        return this.taskKey;
    }
    getCurrentGuards() {
        return this.guards;
    }
    setTask(taskKey) {
        if (this.taskKey === taskKey) {
            return;
        }
        this.taskKey = taskKey;
        void this.loadData();
    }
    async loadData() {
        this.errorMessage = undefined;
        if (!this.taskKey) {
            this.guards = [];
            this.refresh();
            return;
        }
        const response = await (0, api_1.fetchGuards)(this.taskKey);
        if (response.error) {
            this.guards = [];
            this.errorMessage = response.error.message;
            this.refresh();
            return;
        }
        const rank = {
            failed: 0,
            pending: 1,
            inherited: 2,
            skipped: 3,
            passed: 4,
        };
        this.guards = [...(response.data?.guards ?? [])].sort((a, b) => {
            const aRank = rank[a.status] ?? 99;
            const bRank = rank[b.status] ?? 99;
            if (aRank !== bRank) {
                return aRank - bRank;
            }
            return a.title.localeCompare(b.title);
        });
        this.refresh();
    }
    refresh() {
        this.onDidChangeTreeDataEmitter.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
        if (!this.taskKey) {
            return [new PlaceholderItem('Task auswählen, um Guards zu sehen')];
        }
        if (this.errorMessage) {
            return [new PlaceholderItem(`Guard-Fehler: ${this.errorMessage}`)];
        }
        if (this.guards.length === 0) {
            return [new PlaceholderItem(`Keine Guards für ${this.taskKey}`)];
        }
        return this.guards.map(guard => new GuardItem(guard));
    }
}
exports.GuardStatusProvider = GuardStatusProvider;
class AgentActivityProvider {
    onDidChangeTreeDataEmitter = new vscode.EventEmitter();
    onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;
    events = [];
    addEvent(message) {
        this.events.unshift(`${new Date().toLocaleTimeString()} — ${message}`);
        if (this.events.length > 50) {
            this.events.pop();
        }
        this.onDidChangeTreeDataEmitter.fire();
    }
    getTreeItem(element) {
        return element;
    }
    getChildren() {
        if (this.events.length === 0) {
            return [new PlaceholderItem('Keine Aktivität')];
        }
        return this.events.map(event => {
            const item = new vscode.TreeItem(event, vscode.TreeItemCollapsibleState.None);
            item.iconPath = new vscode.ThemeIcon('history');
            return item;
        });
    }
}
exports.AgentActivityProvider = AgentActivityProvider;
//# sourceMappingURL=sidebarProvider.js.map