/**
 * Hivemind Sidebar TreeView Provider — TASK-IDE-003
 *
 * Provides four tree views:
 *   hivemind.activeTasks   — All tasks (incoming → in_review) with inline actions
 *   hivemind.nextPrompts   — Aufgaben-Queue: dispatches + ready/review tasks
 *   hivemind.guardStatus   — Guard results for the selected task
 *   hivemind.agentActivity — Recent dispatch/event activity
 */

import * as vscode from 'vscode';
import {
  fetchActiveTasks,
  fetchGuards,
  fetchPendingDispatches,
  HivemindDispatch,
  HivemindTask,
  HivemindTaskGuard,
} from './api';

export { HivemindTask };

export class TaskItem extends vscode.TreeItem {
  constructor(readonly task: HivemindTask) {
    super(`${task.task_key} — ${task.title}`, vscode.TreeItemCollapsibleState.None);
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

function stateLabel(state: string): string {
  switch (state) {
    case 'incoming':    return '○ Incoming';
    case 'scoped':      return '◌ Scoped';
    case 'ready':       return '● Ready';
    case 'in_progress': return '◎ In Progress';
    case 'in_review':   return '👁 In Review';
    default:            return state;
  }
}

class DispatchItem extends vscode.TreeItem {
  constructor(dispatch: HivemindDispatch) {
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
  constructor(guard: HivemindTaskGuard) {
    super(guard.title, vscode.TreeItemCollapsibleState.None);
    this.description = `${guard.status}${guard.scope ? ` • ${guard.scope}` : ''}`;
    this.tooltip = `${guard.title}\nStatus: ${guard.status}\nType: ${guard.type ?? 'n/a'}\nScope: ${guard.scope ?? 'n/a'}`;
    this.iconPath = guardStatusIcon(guard.status);
  }
}

class PlaceholderItem extends vscode.TreeItem {
  constructor(label: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon('info');
  }
}

function stateIcon(state: string): vscode.ThemeIcon {
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

function guardStatusIcon(status: string): vscode.ThemeIcon {
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

export class ActiveTasksProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  private tasks: HivemindTask[] = [];

  setTasks(tasks: HivemindTask[]): void {
    this.tasks = tasks;
    this.refresh();
  }

  getTasks(): readonly HivemindTask[] {
    return this.tasks;
  }

  async loadData(): Promise<void> {
    this.setTasks(await fetchActiveTasks());
  }

  refresh(): void {
    this.onDidChangeTreeDataEmitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.TreeItem[] {
    if (this.tasks.length === 0) {
      return [new PlaceholderItem('Keine Tasks (incoming / ready / in_progress / in_review)')];
    }
    return this.tasks.map(task => new TaskItem(task));
  }
}

export class NextPromptsProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  private dispatches: HivemindDispatch[] = [];
  private readyTasks: HivemindTask[] = [];
  private reviewTasks: HivemindTask[] = [];

  setDispatches(dispatches: HivemindDispatch[]): void {
    this.dispatches = dispatches;
    this.refresh();
  }

  setTasks(allTasks: HivemindTask[]): void {
    this.readyTasks = allTasks.filter(t => t.state === 'ready');
    this.reviewTasks = allTasks.filter(t => t.state === 'in_review');
    this.refresh();
  }

  async loadData(): Promise<void> {
    this.setDispatches(await fetchPendingDispatches());
  }

  refresh(): void {
    this.onDidChangeTreeDataEmitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.TreeItem[] {
    const items: vscode.TreeItem[] = [];

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

export class GuardStatusProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  private taskKey: string | undefined;
  private guards: HivemindTaskGuard[] = [];
  private errorMessage: string | undefined;

  getCurrentTaskKey(): string | undefined {
    return this.taskKey;
  }

  getCurrentGuards(): readonly HivemindTaskGuard[] {
    return this.guards;
  }

  setTask(taskKey: string | undefined): void {
    if (this.taskKey === taskKey) {
      return;
    }
    this.taskKey = taskKey;
    void this.loadData();
  }

  async loadData(): Promise<void> {
    this.errorMessage = undefined;
    if (!this.taskKey) {
      this.guards = [];
      this.refresh();
      return;
    }

    const response = await fetchGuards(this.taskKey);
    if (response.error) {
      this.guards = [];
      this.errorMessage = response.error.message;
      this.refresh();
      return;
    }

    const rank: Record<string, number> = {
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

  refresh(): void {
    this.onDidChangeTreeDataEmitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.TreeItem[] {
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

export class AgentActivityProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  private events: string[] = [];

  addEvent(message: string): void {
    this.events.unshift(`${new Date().toLocaleTimeString()} — ${message}`);
    if (this.events.length > 50) {
      this.events.pop();
    }
    this.onDidChangeTreeDataEmitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(): vscode.TreeItem[] {
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
