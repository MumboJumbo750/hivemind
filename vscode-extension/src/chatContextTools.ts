import * as vscode from 'vscode';
import { fetchActiveTasks, fetchTask } from './api';

function asToolResult(payload: unknown): vscode.LanguageModelToolResult {
  const text = JSON.stringify(payload, null, 2);
  return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(text)]);
}

export function registerChatContextTools(context: vscode.ExtensionContext): void {
  if (!('lm' in vscode)) {
    return;
  }

  const activeTaskTool = vscode.lm.registerTool('hivemind.activeTask', {
    async invoke(): Promise<vscode.LanguageModelToolResult> {
      const tasks = await fetchActiveTasks();
      const current = tasks.find(t => t.state === 'in_progress') ?? tasks[0];
      if (!current) {
        return asToolResult({
          data: null,
          message: 'No active Hivemind task found.',
        });
      }

      const details = await fetchTask(current.task_key);
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
    async invoke(): Promise<vscode.LanguageModelToolResult> {
      const tasks = await fetchActiveTasks();
      const current = tasks.find(t => t.state === 'in_progress') ?? tasks[0];
      if (!current) {
        return asToolResult({
          data: null,
          message: 'No active Hivemind epic found.',
        });
      }

      const details = await fetchTask(current.task_key);
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
