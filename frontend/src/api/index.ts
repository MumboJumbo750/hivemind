import type { Project, Epic, Task, Skill, SkillForkResponse, NodeIdentity, PeerNode, FederationSettings, TriageItem, McpToolResponse, PromptResponse } from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'

// Lazy import to avoid circular dep (authStore imports api, api imports authStore)
async function _getToken(): Promise<string | null> {
  const { useAuthStore } = await import('../stores/authStore')
  const { getActivePinia } = await import('pinia')
  if (!getActivePinia()) return null
  return useAuthStore().accessToken
}

async function request<T>(path: string, init?: RequestInit, _retry = true): Promise<T> {
  const token = await _getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers })

  // Automatischer Token-Refresh bei 401
  if (res.status === 401 && _retry) {
    const { useAuthStore } = await import('../stores/authStore')
    const { getActivePinia } = await import('pinia')
    if (getActivePinia()) {
      const ok = await useAuthStore().refreshToken()
      if (ok) return request<T>(path, init, false)
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `HTTP ${res.status}: ${path}`)
  }
  return res.json()
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export const api = {
  // ─── Auth ────────────────────────────────────────────────────────────────
  login: (username: string, password: string) =>
    request<TokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  logout: () =>
    fetch(`${BASE_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' }),

  refreshToken: () =>
    request<TokenResponse>('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    }, false),

  // ─── Settings ────────────────────────────────────────────────────────────
  getSettings: () =>
    request<{ mode: string; notification_mode: string }>('/api/settings'),

  updateSettings: (mode: 'solo' | 'team') =>
    request<{ mode: string; notification_mode: string }>('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify({ mode }),
    }),

  // ─── Projects ────────────────────────────────────────────────────────────
  getProjects: () =>
    request<Project[]>('/api/projects'),

  createProject: (data: { name: string; slug: string; description?: string }) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),

  // ─── Epics ───────────────────────────────────────────────────────────────
  getEpics: (projectId: string) =>
    request<Epic[]>(`/api/projects/${projectId}/epics`),

  patchEpic: (epicKey: string, patch: Partial<Epic> & { expected_version?: number }) =>
    request<Epic>(`/api/epics/${epicKey}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  // Legacy alias
  patchEpicState: (epicKey: string, patch: { state?: string; priority?: string; sla_due_at?: string; dod_framework?: unknown }) =>
    request<Epic>(`/api/epics/${epicKey}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  // ─── Tasks ───────────────────────────────────────────────────────────────
  getTasks: (epicKey: string) =>
    request<Task[]>(`/api/epics/${epicKey}/tasks`),

  patchTask: (taskKey: string, patch: Partial<Task> & { expected_version?: number }) =>
    request<Task>(`/api/tasks/${taskKey}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  approveTask: (taskKey: string) =>
    request<Task>(`/api/tasks/${taskKey}/review`, { method: 'POST', body: JSON.stringify({ action: 'approve' }) }),

  rejectTask: (taskKey: string, comment?: string) =>
    request<Task>(`/api/tasks/${taskKey}/review`, { method: 'POST', body: JSON.stringify({ action: 'reject', comment }) }),

  // ─── Members ─────────────────────────────────────────────────────────────
  getMembers: (projectId: string) =>
    request<{ project_id: string; user_id: string; role: string }[]>(`/api/projects/${projectId}/members`),

  // ─── Skills ──────────────────────────────────────────────────────────────
  getSkills: (federationScope?: string) =>
    request<Skill[]>(`/api/skills${federationScope ? `?federation_scope=${federationScope}` : ''}`),

  forkSkill: (skillId: string) =>
    request<SkillForkResponse>(`/api/skills/${skillId}/fork`, { method: 'POST' }),

  // ─── Search ──────────────────────────────────────────────────────────────
  search: (q: string, type = 'tasks,epics') =>
    request<{ tasks?: unknown[]; epics?: unknown[] }>(`/api/search?q=${encodeURIComponent(q)}&type=${type}`),

  // ─── Federation / Nodes ──────────────────────────────────────────────────
  getNodeIdentity: () =>
    request<NodeIdentity>('/api/node-identity'),

  getNodes: () =>
    request<PeerNode[]>('/api/nodes'),

  createNode: (data: { node_name: string; node_url: string; public_key?: string }) =>
    request<PeerNode>('/api/nodes', { method: 'POST', body: JSON.stringify(data) }),

  updateNode: (nodeId: string, data: { status?: string; node_name?: string }) =>
    request<PeerNode>(`/api/nodes/${nodeId}`, { method: 'PATCH', body: JSON.stringify(data) }),

  deleteNode: (nodeId: string) =>
    request<void>(`/api/nodes/${nodeId}`, { method: 'DELETE' }),

  getFederationSettings: () =>
    request<FederationSettings>('/api/settings/federation'),

  updateFederationSettings: (data: Partial<FederationSettings>) =>
    request<FederationSettings>('/api/settings/federation', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // ─── Triage ──────────────────────────────────────────────────────────────
  getTriageItems: (state?: string) =>
    request<TriageItem[]>(`/api/sync-outbox?direction=inbound${state ? `&routing_state=${state}` : ''}`),

  // ─── MCP ─────────────────────────────────────────────────────────────────
  getMcpTools: () =>
    request<{ name: string; description: string }[]>('/api/mcp/tools'),

  callMcpTool: (name: string, args: Record<string, unknown>) =>
    request<McpToolResponse[]>('/api/mcp/call', {
      method: 'POST',
      body: JSON.stringify({ name, arguments: args }),
    }),

  // ─── Prompt ──────────────────────────────────────────────────────────────
  getPrompt: (type: string, taskId?: string, epicId?: string, projectId?: string) =>
    request<McpToolResponse[]>('/api/mcp/call', {
      method: 'POST',
      body: JSON.stringify({
        name: 'hivemind/get_prompt',
        arguments: { type, ...(taskId && { task_id: taskId }), ...(epicId && { epic_id: epicId }), ...(projectId && { project_id: projectId }) },
      }),
    }),
}
