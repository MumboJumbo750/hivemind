/**
 * Hivemind Backend API Client — TASK-IDE-003
 *
 * Minimal HTTP client for the Hivemind backend.
 * Uses the VS Code workspace settings for the base URL.
 */

import * as vscode from 'vscode';

export interface HivemindTask {
  task_key: string;
  title: string;
  state: string;
  epic_key?: string;
  priority?: string;
  updated_at?: string;
}

interface ListTaskRow {
  id: string;
  task_key: string;
  epic_id: string;
  title: string;
  state: string;
  created_at?: string;
}

interface ListEpicRow {
  id: string;
  epic_key: string;
  priority?: string;
}

interface McpListResponse<T> {
  data: T[];
  meta?: {
    total?: number;
  };
}

export interface HivemindDispatch {
  dispatch_id: string;
  agent_role: string;
  prompt_type: string;
  trigger_id: string;
  prompt?: string;
  tools_needed?: string[];
  execution_mode: string;
  status: string;
}

export type DispatchFinalStatus = 'completed' | 'failed' | 'cancelled' | 'timed_out';

export interface DispatchProgressEvent {
  stage: string;
  message?: string;
  details?: Record<string, unknown>;
}

export interface HivemindError {
  code: string;
  message: string;
}

export interface HivemindPromptResponse {
  data?: {
    prompt_type: string;
    prompt: string;
    token_count: number;
  };
  error?: HivemindError;
}

export interface HivemindTaskGuard {
  guard_id: string;
  title: string;
  type?: string;
  command?: string;
  status: string;
  result?: string;
  skippable: boolean;
  scope?: string;
}

export interface HivemindTaskDetails {
  id: string;
  task_key: string;
  epic_id?: string;
  title: string;
  description?: string;
  state: string;
  definition_of_done?: { criteria?: string[] };
  guards: HivemindTaskGuard[];
  qa_failed_count?: number;
  updated_at?: string;
}

export interface HivemindGuardsResponse {
  task_key: string;
  guards: HivemindTaskGuard[];
  total: number;
}

export interface HivemindGovernanceConfig {
  review: 'manual' | 'assisted' | 'auto';
  epic_proposal: 'manual' | 'assisted' | 'auto';
  epic_scoping: 'manual' | 'assisted' | 'auto';
  skill_merge: 'manual' | 'assisted' | 'auto';
  guard_merge: 'manual' | 'assisted' | 'auto';
  decision_request: 'manual' | 'assisted' | 'auto';
  escalation: 'manual' | 'assisted' | 'auto';
}

export interface AuditEntry {
  id: string;
  tool_name: string;
  target_id?: string;
  input_snapshot?: Record<string, unknown>;
  output_snapshot?: Record<string, unknown>;
  status: string;
  created_at: string;
}

interface AuditListResponse {
  data: AuditEntry[];
  total_count: number;
  has_more: boolean;
  page: number;
  page_size: number;
}

interface McpToolPart {
  type: string;
  text?: string;
}

interface McpCallEnvelope {
  result?: McpToolPart[];
}

interface McpParsed<T> {
  data?: T;
  error?: HivemindError;
}

function getBaseUrl(): string {
  return vscode.workspace
    .getConfiguration('hivemind')
    .get<string>('url', 'http://localhost:8000');
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${getBaseUrl()}${path}`;
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText} — ${url}`);
  }
  return response.json() as Promise<T>;
}

function withQuery(path: string, query: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) continue;
    params.set(key, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

function parseMcpEnvelope<T>(envelope: McpCallEnvelope): McpParsed<T> {
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
    const parsed = JSON.parse(firstText) as {
      data?: T;
      error?: { code?: string; message?: string };
    };
    if (parsed.error) {
      return {
        error: {
          code: parsed.error.code ?? 'mcp_error',
          message: parsed.error.message ?? 'Unknown MCP error',
        },
      };
    }
    return { data: parsed.data };
  } catch {
    return {
      error: {
        code: 'invalid_mcp_json',
        message: 'Failed to parse MCP tool payload as JSON.',
      },
    };
  }
}

async function callMcpTool<T>(tool: string, args: Record<string, unknown>): Promise<McpParsed<T>> {
  try {
    const envelope = await apiFetch<McpCallEnvelope>('/api/mcp/call', {
      method: 'POST',
      body: JSON.stringify({ tool, arguments: args }),
    });
    const parsed = parseMcpEnvelope<T>(envelope);
    if (parsed.error) {
      console.error(`[hivemind] callMcpTool(${tool}) error:`, parsed.error);
    }
    return parsed;
  } catch (err) {
    console.error(`[hivemind] callMcpTool(${tool}) fetch failed:`, err);
    return {
      error: {
        code: 'http_error',
        message: String(err),
      },
    };
  }
}

/** Fetch tasks that need attention: incoming, scoped, ready (startable), in_progress, in_review */
export async function fetchActiveTasks(): Promise<HivemindTask[]> {
  const [incomingResult, scopedResult, readyResult, inProgressResult, inReviewResult] = await Promise.all([
    callMcpTool<ListTaskRow[]>('hivemind/list_tasks', { state: 'incoming', limit: 20, offset: 0 }),
    callMcpTool<ListTaskRow[]>('hivemind/list_tasks', { state: 'scoped',   limit: 20, offset: 0 }),
    callMcpTool<ListTaskRow[]>('hivemind/list_tasks', { state: 'ready',    limit: 50, offset: 0 }),
    callMcpTool<ListTaskRow[]>('hivemind/list_tasks', { state: 'in_progress', limit: 50, offset: 0 }),
    callMcpTool<ListTaskRow[]>('hivemind/list_tasks', { state: 'in_review',   limit: 50, offset: 0 }),
  ]);

  const tasks: ListTaskRow[] = [
    ...(incomingResult.data ?? []),
    ...(scopedResult.data ?? []),
    ...(readyResult.data ?? []),
    ...(inProgressResult.data ?? []),
    ...(inReviewResult.data ?? []),
  ];

  if (tasks.length === 0) {
    return [];
  }

  const epicResult = await callMcpTool<ListEpicRow[]>('hivemind/list_epics', {
    limit: 200,
    offset: 0,
  });

  const epicMap = new Map<string, ListEpicRow>();
  if (!epicResult.error && epicResult.data) {
    for (const epic of epicResult.data) {
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

/** Transition task to a new state via MCP */
export async function transitionTaskState(
  taskKey: string,
  targetState: string
): Promise<McpParsed<Record<string, unknown>>> {
  return callMcpTool<Record<string, unknown>>('hivemind/update_task_state', {
    task_key: taskKey,
    target_state: targetState,
  });
}

/** Fetch pending dispatches (TASK-IDE-005: execution_mode=ide) */
export async function fetchPendingDispatches(): Promise<HivemindDispatch[]> {
  try {
    const data = await apiFetch<{ data?: HivemindDispatch[] }>('/api/conductor/dispatches/pending');
    return data.data ?? [];
  } catch {
    return [];
  }
}

/** Generate the next prompt */
export async function fetchNextPrompt(): Promise<HivemindPromptResponse> {
  return callMcpTool<HivemindPromptResponse['data']>('hivemind/get_prompt', { type: 'worker' });
}

/** Generate prompt for a specific task and type */
export async function fetchPromptForTask(
  promptType: string,
  taskKey: string
): Promise<HivemindPromptResponse> {
  const args: Record<string, unknown> = { type: promptType };
  if (taskKey) {
    args.task_key = taskKey;
    args.task_id = taskKey; // backward-compatible with current backend prompt tool
  }
  return callMcpTool<HivemindPromptResponse['data']>('hivemind/get_prompt', args);
}

/** Fetch task details (state, DoD, guards) */
export async function fetchTask(taskKey: string): Promise<McpParsed<HivemindTaskDetails>> {
  return callMcpTool<HivemindTaskDetails>('hivemind/get_task', { task_key: taskKey });
}

/** Fetch full guard list for task */
export async function fetchGuards(taskKey: string): Promise<McpParsed<HivemindGuardsResponse>> {
  return callMcpTool<HivemindGuardsResponse>('hivemind/get_guards', { task_key: taskKey });
}

/** Report guard result */
export async function reportGuardResult(
  taskKey: string,
  guardId: string,
  status: 'passed' | 'failed' | 'skipped',
  result: string
): Promise<McpParsed<Record<string, unknown>>> {
  return callMcpTool<Record<string, unknown>>('hivemind/report_guard_result', {
    task_key: taskKey,
    guard_id: guardId,
    status,
    result,
  });
}

/** Submit task result via worker write-tool */
export async function submitTaskResult(
  taskKey: string,
  result: string,
  artifacts: Array<Record<string, unknown>> = []
): Promise<McpParsed<Record<string, unknown>>> {
  return callMcpTool<Record<string, unknown>>('hivemind/submit_result', {
    task_key: taskKey,
    result,
    artifacts,
  });
}

/** Approve a task in review (transition → done via review gate) */
export async function approveTask(
  taskKey: string,
  comment = ''
): Promise<McpParsed<Record<string, unknown>>> {
  return callMcpTool<Record<string, unknown>>('hivemind/approve_review', {
    task_key: taskKey,
    comment,
  });
}

/** Reject a task in review (transition → qa_failed) */
export async function rejectTask(
  taskKey: string,
  comment: string
): Promise<McpParsed<Record<string, unknown>>> {
  return callMcpTool<Record<string, unknown>>('hivemind/reject_review', {
    task_key: taskKey,
    comment,
  });
}

/** Acknowledge an IDE dispatch */
export async function acknowledgeDispatch(dispatchId: string): Promise<void> {
  await apiFetch(`/api/conductor/dispatches/${dispatchId}/acknowledge`, { method: 'POST' });
}

/** Mark an IDE dispatch as running */
export async function markDispatchRunning(dispatchId: string): Promise<void> {
  await apiFetch(`/api/conductor/dispatches/${dispatchId}/running`, { method: 'POST' });
}

/** Complete an IDE dispatch */
export async function completeDispatch(
  dispatchId: string,
  result: string,
  status: DispatchFinalStatus = 'completed'
): Promise<void> {
  await apiFetch(`/api/conductor/dispatches/${dispatchId}/complete`, {
    method: 'POST',
    body: JSON.stringify({ status, result }),
  });
}

/** Report IDE dispatch execution progress */
export async function reportDispatchProgress(
  dispatchId: string,
  event: DispatchProgressEvent
): Promise<void> {
  await apiFetch(`/api/conductor/dispatches/${dispatchId}/progress`, {
    method: 'POST',
    body: JSON.stringify(event),
  });
}

/** Fetch governance configuration from backend */
export async function fetchGovernanceConfig(): Promise<HivemindGovernanceConfig | undefined> {
  try {
    return await apiFetch<HivemindGovernanceConfig>('/api/settings/governance');
  } catch {
    return undefined;
  }
}

/** Fetch recent audit entries (used to infer MCP tool activity in IDE flows) */
export async function fetchAuditEntries(
  fromIso: string,
  pageSize = 50
): Promise<AuditEntry[]> {
  try {
    const path = withQuery('/api/audit', {
      from: fromIso,
      page_size: pageSize,
      page: 1,
    });
    const data = await apiFetch<AuditListResponse>(path);
    return data.data ?? [];
  } catch {
    return [];
  }
}

/** Health check */
export async function checkHealth(): Promise<boolean> {
  try {
    await apiFetch<{ status: string }>('/health');
    return true;
  } catch {
    return false;
  }
}
