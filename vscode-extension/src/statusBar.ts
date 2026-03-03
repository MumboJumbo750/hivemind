/**
 * Hivemind Status Bar Item — TASK-IDE-003
 *
 * Shows connection status and active task count in the VS Code status bar.
 */

import * as vscode from 'vscode';

export class HivemindStatusBar {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      10
    );
    this.item.command = 'hivemind.nextPrompt';
    this.setDisconnected();
    this.item.show();
  }

  setConnected(activeTaskCount: number, activeTaskKey?: string, role = 'worker'): void {
    if (activeTaskKey) {
      this.item.text = `$(sync~spin) Hivemind: [${role}] ${activeTaskKey}`;
      this.item.tooltip = `Aktiver Task: ${activeTaskKey} (${role})`;
    } else {
      this.item.text = `$(beaker) Hivemind: ${activeTaskCount} in_progress`;
      this.item.tooltip = 'Hivemind verbunden — klicken für nächsten Prompt';
    }
    this.item.backgroundColor = undefined;
  }

  setActiveTask(taskKey: string, role: string): void {
    this.setConnected(1, taskKey, role);
  }

  setDisconnected(): void {
    this.item.text = '$(beaker) Hivemind: offline';
    this.item.tooltip = 'Hivemind nicht erreichbar — Backend läuft?';
    this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  }

  dispose(): void {
    this.item.dispose();
  }
}
