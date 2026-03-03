import type { Project, Epic, Task, Skill, SkillForkResponse, SkillListResponse, SkillVersion, ContextBoundary, EpicProposal, EpicProposalListResponse, RequirementDraftResponse, NodeIdentity, PeerNode, FederationSettings, TriageItem, McpToolResponse, AuditListResponse, HivemindNotification, SyncStatusResponse, NodeBugCountItem, KpiSummaryResponse, KpiHistoryResponse, NexusGraph3DResponse, DeadLetterListResponse, ReviewRecommendation, AiProviderConfig, AiModelInfo, AiCredential, GovernanceConfig, McpBridge, McpBridgeTool } from './types'

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
    const detail = body.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
        : `HTTP ${res.status}: ${path}`
    throw new Error(msg)
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

  getSyncStatus: () =>
    request<SyncStatusResponse>('/api/admin/sync-status'),

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

  createTask: (epicKey: string, data: { title: string; description?: string; assigned_to?: string }) =>
    request<Task>(`/api/epics/${epicKey}/tasks`, { method: 'POST', body: JSON.stringify(data) }),

  getContextBoundary: (taskKey: string) =>
    request<ContextBoundary | null>(`/api/tasks/${taskKey}/context-boundary`),

  patchTask: (taskKey: string, patch: Partial<Task> & { expected_version?: number }) =>
    request<Task>(`/api/tasks/${taskKey}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  approveTask: (taskKey: string) =>
    request<Task>(`/api/tasks/${taskKey}/review`, { method: 'POST', body: JSON.stringify({ action: 'approve' }) }),

  rejectTask: (taskKey: string, comment?: string) =>
    request<Task>(`/api/tasks/${taskKey}/review`, { method: 'POST', body: JSON.stringify({ action: 'reject', comment }) }),

  reenterTask: (taskKey: string) =>
    request<Task>(`/api/tasks/${taskKey}/reenter`, { method: 'POST' }),

  // ─── Members ─────────────────────────────────────────────────────────────
  getMembers: (projectId: string) =>
    request<{ project_id: string; user_id: string; role: string }[]>(`/api/projects/${projectId}/members`),

  // ─── Skills ──────────────────────────────────────────────────────────────
  getSkills: (params?: { lifecycle?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams()
    if (params?.lifecycle) qs.set('lifecycle', params.lifecycle)
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    const q = qs.toString()
    return request<SkillListResponse>(`/api/skills${q ? `?${q}` : ''}`)
  },

  getSkill: (skillId: string) =>
    request<Skill>(`/api/skills/${skillId}`),

  getSkillVersions: (skillId: string) =>
    request<SkillVersion[]>(`/api/skills/${skillId}/versions`),

  createSkill: (data: { title: string; content: string; service_scope: string[]; stack: string[]; project_id: string }) =>
    request<Skill>('/api/skills', { method: 'POST', body: JSON.stringify(data) }),

  updateSkill: (skillId: string, data: { title?: string; content?: string; version: number }) =>
    request<Skill>(`/api/skills/${skillId}`, { method: 'PATCH', body: JSON.stringify(data) }),

  submitSkill: (skillId: string) =>
    request<Skill>(`/api/skills/${skillId}/submit`, { method: 'POST' }),

  mergeSkill: (skillId: string) =>
    request<Skill>(`/api/skills/${skillId}/merge`, { method: 'POST' }),

  rejectSkill: (skillId: string, rationale: string) =>
    request<Skill>(`/api/skills/${skillId}/reject`, { method: 'POST', body: JSON.stringify({ rationale }) }),

  forkSkill: (skillId: string) =>
    request<SkillForkResponse>(`/api/skills/${skillId}/fork`, { method: 'POST' }),

  // ─── Epic Proposals ──────────────────────────────────────────────────────
  getEpicProposals: (params?: { state?: string; project_id?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams()
    if (params?.state) qs.set('state', params.state)
    if (params?.project_id) qs.set('project_id', params.project_id)
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.offset) qs.set('offset', String(params.offset))
    const q = qs.toString()
    return request<EpicProposalListResponse>(`/api/epic-proposals${q ? `?${q}` : ''}`)
  },

  getEpicProposal: (proposalId: string) =>
    request<EpicProposal>(`/api/epic-proposals/${proposalId}`),

  acceptEpicProposal: (proposalId: string) =>
    request<EpicProposal>(`/api/epic-proposals/${proposalId}/accept`, { method: 'POST' }),

  rejectEpicProposal: (proposalId: string, reason: string) =>
    request<EpicProposal>(`/api/epic-proposals/${proposalId}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),

  draftRequirement: (data: { project_id: string; text: string; priority_hint?: string; tags?: string[] }) =>
    request<RequirementDraftResponse>('/api/epic-proposals/draft-requirement', { method: 'POST', body: JSON.stringify(data) }),

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

  callMcpTool: async (name: string, args: Record<string, unknown>) => {
    const res = await request<{ result: McpToolResponse[] }>('/api/mcp/call', {
      method: 'POST',
      body: JSON.stringify({ tool: name, arguments: args }),
    })
    return res.result
  },

  // ─── Audit ──────────────────────────────────────────────────────────────
  getAuditEntries: (params?: {
    tool_name?: string
    entity_type?: string
    from?: string
    to?: string
    page?: number
    page_size?: number
  }) => {
    const q = new URLSearchParams()
    if (params?.tool_name) q.set('tool_name', params.tool_name)
    if (params?.entity_type) q.set('entity_type', params.entity_type)
    if (params?.from) q.set('from', params.from)
    if (params?.to) q.set('to', params.to)
    if (params?.page) q.set('page', String(params.page))
    if (params?.page_size) q.set('page_size', String(params.page_size))
    const qs = q.toString()
    return request<AuditListResponse>(`/api/audit${qs ? `?${qs}` : ''}`)
  },

  // ─── Notifications (Phase 6) ─────────────────────────────────────────────
  getNotifications: (params?: {
    read?: boolean
    priority?: string
    type?: string
    limit?: number
    offset?: number
  }) => {
    const q = new URLSearchParams()
    if (params?.read !== undefined) q.set('read', String(params.read))
    if (params?.priority) q.set('priority', params.priority)
    if (params?.type) q.set('type', params.type)
    if (params?.limit) q.set('limit', String(params.limit))
    if (params?.offset) q.set('offset', String(params.offset))
    const qs = q.toString()
    return request<HivemindNotification[]>(`/api/notifications${qs ? `?${qs}` : ''}`)
  },

  getUnreadCount: () =>
    request<{ count: number }>('/api/notifications/unread-count'),

  markNotificationRead: (notificationId: string) =>
    request<{ status: string }>(`/api/notifications/${notificationId}/read`, {
      method: 'PATCH',
    }),

  // ─── Bug-Heatmap (Phase 7) ───────────────────────────────────────────────
  getBugCounts: (projectId?: string) => {
    const qs = projectId ? `?project_id=${projectId}` : ''
    return request<NodeBugCountItem[]>(`/api/nexus/bug-counts${qs}`)
  },

  // ─── KPI Dashboard (Phase 7 / 8) ─────────────────────────────────────────
  getKpiSummary: () =>
    request<KpiSummaryResponse>('/api/kpis/summary'),

  getKpiHistory: (days: 7 | 30 = 7) =>
    request<KpiHistoryResponse>(`/api/kpis/history?days=${days}`),

  // ─── Nexus Grid 3D (Phase 8) ─────────────────────────────────────────────
  getNexusGraph3D: (params?: { project_id?: string; page?: number; page_size?: number }) => {
    const q = new URLSearchParams()
    if (params?.project_id) q.set('project_id', params.project_id)
    if (params?.page !== undefined) q.set('page', String(params.page))
    if (params?.page_size !== undefined) q.set('page_size', String(params.page_size))
    const qs = q.toString()
    return request<NexusGraph3DResponse>(`/api/nexus/graph3d${qs ? `?${qs}` : ''}`)
  },

  // ─── Dead Letter Queue (Phase 7) ─────────────────────────────────────────
  getDeadLetters: (params?: { system?: string; direction?: string; cursor?: string; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.system) q.set('system', params.system)
    if (params?.direction) q.set('direction', params.direction)
    if (params?.cursor) q.set('cursor', params.cursor)
    if (params?.limit !== undefined) q.set('limit', String(params.limit))
    const qs = q.toString()
    return request<DeadLetterListResponse>(`/api/triage/dead-letters${qs ? `?${qs}` : ''}`)
  },

  requeueDeadLetter: (id: string) =>
    request<{ data: unknown }>(`/api/triage/dead-letters/${id}/requeue`, { method: 'POST' }),

  discardDeadLetter: (id: string) =>
    request<{ data: unknown }>(`/api/triage/dead-letters/${id}/discard`, { method: 'POST' }),

  // ─── AI Review Recommendations (Phase 8) ────────────────────────────────
  getReviewRecommendations: async (taskKey: string): Promise<ReviewRecommendation | null> => {
    try {
      const res = await request<{ result: McpToolResponse[] }>('/api/mcp/call', {
        method: 'POST',
        body: JSON.stringify({
          tool: 'hivemind/get_review_recommendations',
          arguments: { task_key: taskKey },
        }),
      })
      const text = res.result?.[0]?.text
      if (!text) return null
      const parsed = JSON.parse(text) as { data?: ReviewRecommendation; error?: { message: string } }
      if (parsed.error) return null
      return parsed.data ?? null
    } catch {
      return null
    }
  },

  vetoAutoReview: (taskKey: string) =>
    request<{ status: string }>(`/api/tasks/${taskKey}/veto-auto-review`, { method: 'POST' }),

  // ─── AI Provider Config (Phase 8) ────────────────────────────────────────
  getAiProviders: () =>
    request<AiProviderConfig[]>('/api/settings/ai-providers'),

  getAiProviderModels: (provider: string, apiKey?: string, endpoint?: string, credentialId?: string, agentRole?: string) => {
    const params = new URLSearchParams({ provider })
    if (apiKey) params.set('api_key', apiKey)
    if (endpoint) params.set('endpoint', endpoint)
    if (credentialId) params.set('credential_id', credentialId)
    if (agentRole) params.set('agent_role', agentRole)
    return request<AiModelInfo[]>(`/api/settings/ai-providers/models?${params.toString()}`)
  },

  upsertAiProvider: (agentRole: string, data: Partial<AiProviderConfig> & { agent_role: string }) =>
    request<AiProviderConfig>(`/api/settings/ai-providers/${encodeURIComponent(agentRole)}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteAiProvider: (agentRole: string) =>
    request<void>(`/api/settings/ai-providers/${encodeURIComponent(agentRole)}`, { method: 'DELETE' }),

  testAiProvider: (agentRole: string) =>
    request<{ ok: boolean; message: string }>(`/api/settings/ai-providers/${encodeURIComponent(agentRole)}/test`, { method: 'POST' }),

  // ─── AI Credentials (zentrale Key-Verwaltung) ────────────────────────────
  getCredentials: () =>
    request<AiCredential[]>('/api/settings/credentials'),

  createCredential: (data: { name: string; provider_type: string; api_key?: string; endpoint?: string; note?: string }) =>
    request<AiCredential>('/api/settings/credentials', { method: 'POST', body: JSON.stringify(data) }),

  updateCredential: (id: string, data: { name?: string; provider_type?: string; api_key?: string; endpoint?: string; note?: string }) =>
    request<AiCredential>(`/api/settings/credentials/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteCredential: (id: string) =>
    request<void>(`/api/settings/credentials/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // ─── Governance Config (Phase 8) ─────────────────────────────────────────
  getGovernance: () =>
    request<GovernanceConfig>('/api/settings/governance'),

  updateGovernance: (data: GovernanceConfig) =>
    request<GovernanceConfig>('/api/settings/governance', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // ─── MCP Bridge Config (Phase 8) ─────────────────────────────────────────
  getMcpBridges: () =>
    request<McpBridge[]>('/api/admin/mcp-bridges'),

  createMcpBridge: (data: {
    name: string
    namespace: string
    transport: 'http' | 'sse' | 'stdio'
    url_or_command: string
    enabled: boolean
    blocklist: string[]
  }) =>
    request<McpBridge>('/api/admin/mcp-bridges', { method: 'POST', body: JSON.stringify(data) }),

  testMcpBridge: (id: string) =>
    request<{ ok: boolean; message: string }>(`/api/admin/mcp-bridges/${encodeURIComponent(id)}/test`, { method: 'POST' }),

  getMcpBridgeTools: (id: string) =>
    request<McpBridgeTool[]>(`/api/admin/mcp-bridges/${encodeURIComponent(id)}/tools`),

  deleteMcpBridge: (id: string) =>
    request<void>(`/api/admin/mcp-bridges/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // ─── Prompt ──────────────────────────────────────────────────────────────
  getPrompt: async (type: string, taskId?: string, epicId?: string, projectId?: string) => {
    const res = await request<{ result: McpToolResponse[] }>('/api/mcp/call', {
      method: 'POST',
      body: JSON.stringify({
        tool: 'hivemind/get_prompt',
        arguments: { type, ...(taskId && { task_id: taskId }), ...(epicId && { epic_id: epicId }), ...(projectId && { project_id: projectId }) },
      }),
    })
    return res.result
  },

  // ─── Conductor Manual Dispatch ───────────────────────────────────────────
  executePrompt: async (agentRole: string, prompt: string, taskKey?: string, epicId?: string) => {
    return request<{
      status: string
      content?: string
      tool_calls?: { name: string; arguments: Record<string, unknown> }[]
      input_tokens?: number
      output_tokens?: number
      message?: string
    }>('/api/admin/conductor/dispatch', {
      method: 'POST',
      body: JSON.stringify({
        agent_role: agentRole,
        prompt,
        ...(taskKey && { task_key: taskKey }),
        ...(epicId && { epic_id: epicId }),
      }),
    })
  },
}
