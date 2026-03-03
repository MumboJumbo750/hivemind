/**
 * Hivemind Sidebar TreeView Provider — TASK-IDE-003
 *
 * Provides four tree views:
 *   hivemind.activeTasks   — Tasks in in_progress with epic + priority
 *   hivemind.nextPrompts   — Pending conductor dispatches
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

class TaskItem extends vscode.TreeItem {
  constructor(task: HivemindTask) {
    super(`${task.task_key} — ${task.title}`, vscode.TreeItemCollapsibleState.None);
    this.description = `${task.epic_key ?? 'EPIC-?'} • ${task.priority ?? 'n/a'}`;
    this.tooltip = `${task.task_key}\nState: ${task.state}\nEpic: ${task.epic_key ?? 'n/a'}\nPriority: ${task.priority ?? 'n/a'}`;
    this.iconPath = stateIcon(task.state);
    this.contextValue = 'hivemind.task';
    this.command = {
      command: 'hivemind.openTask',
      title: 'Task öffnen',
      arguments: [task.task_key],
    };
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
    case 'in_progress':
      return new vscode.ThemeIcon('sync~spin');
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
      return [new PlaceholderItem('Keine Tasks in in_progress')];
    }
    return this.tasks.map(task => new TaskItem(task));
  }
}

export class NextPromptsProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<vscode.TreeItem | undefined | null | void>();
  readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  private dispatches: HivemindDispatch[] = [];

  setDispatches(dispatches: HivemindDispatch[]): void {
    this.dispatches = dispatches;
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
    if (this.dispatches.length === 0) {
      return [new PlaceholderItem('Keine anstehenden Dispatches')];
    }
    return this.dispatches.map(dispatch => new DispatchItem(dispatch));
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
