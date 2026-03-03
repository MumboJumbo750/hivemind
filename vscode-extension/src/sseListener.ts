/**
 * Hivemind SSE Listener — TASK-IDE-003
 *
 * Connects to the backend SSE endpoints and forwards events to:
 * - AgentActivityProvider (live feed)
 * - Notification popups for important events
 *
 * Uses the native fetch() API with ReadableStream for SSE parsing.
 */

import * as vscode from 'vscode';
import { AgentActivityProvider } from './sidebarProvider';

type EventHandler = (event: string, data: unknown) => void;

export class SseListener {
  private abortController: AbortController | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly endpoints: string[];

  constructor(
    private readonly baseUrl: string,
    private readonly activityProvider: AgentActivityProvider,
    private readonly onEvent: EventHandler
  ) {
    this.endpoints = [
      `${this.baseUrl}/api/events`,
      `${this.baseUrl}/api/events/tasks`,
      `${this.baseUrl}/api/events/notifications`,
      `${this.baseUrl}/api/events/triage`,
    ];
  }

  start(): void {
    this._connect();
  }

  stop(): void {
    this.abortController?.abort();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
  }

  private async _connect(): Promise<void> {
    this.abortController = new AbortController();

    try {
      let response: Response | undefined;
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
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        this._processLines(lines);
      }
      if (!this.abortController.signal.aborted) {
        this._scheduleReconnect();
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        this._scheduleReconnect();
      }
    }
  }

  private _processLines(lines: string[]): void {
    let eventType = 'message';
    let dataLines: string[] = [];

    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, '');
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      } else if (line === '') {
        // dispatch accumulated event
        if (dataLines.length > 0) {
          const raw = dataLines.join('\n');
          try {
            const data = JSON.parse(raw);
            this._handleEvent(eventType, data);
          } catch {
            this._handleEvent(eventType, raw);
          }
          eventType = 'message';
          dataLines = [];
        }
      }
    }
  }

  private _handleEvent(eventType: string, data: unknown): void {
    this.onEvent(eventType, data);

    const showNotifications = vscode.workspace
      .getConfiguration('hivemind')
      .get<boolean>('notifications', true);

    const d = asObject(data);
    const msg = `${eventType}: ${getString(d?.task_key) ?? getString(d?.trigger_id) ?? getString(d?.type) ?? JSON.stringify(data).slice(0, 80)}`;
    this.activityProvider.addEvent(msg);

    if (!showNotifications) return;

    if (eventType === 'task_assigned') {
      const taskKey = getString(d?.task_key) ?? 'unknown';
      void vscode.window.showInformationMessage(
        `Hivemind: Task assigned (${taskKey})`,
        'Task öffnen'
      ).then(action => {
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
      void vscode.window.showInformationMessage(`Hivemind: ${eventType} (${taskKey})`);
      return;
    }

    if (eventType === 'conductor:dispatch' && isReviewDispatch(d)) {
      const triggerId = getString(d?.trigger_id) ?? 'Task';
      vscode.window.showInformationMessage(
        `Hivemind: Review needed (${triggerId})`,
        'Next Prompt'
      ).then(action => {
        if (action) {
          void vscode.commands.executeCommand('hivemind.nextPrompt');
        }
      });
    }
  }

  private _scheduleReconnect(): void {
    this.reconnectTimer = setTimeout(() => this._connect(), 5000);
  }
}

function asObject(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }
  return value as Record<string, unknown>;
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function isReviewDispatch(eventData: Record<string, unknown> | undefined): boolean {
  if (!eventData) {
    return false;
  }
  const promptType = getString(eventData.prompt_type)?.toLowerCase() ?? '';
  const triggerDetail = getString(eventData.trigger_detail)?.toLowerCase() ?? '';
  return promptType.includes('review') || triggerDetail.includes('in_progress->in_review');
}
