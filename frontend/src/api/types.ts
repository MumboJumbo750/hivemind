export interface Project {
  id: string
  name: string
  slug: string
  description?: string
  created_at: string
}

export interface Epic {
  id: string
  epic_key: string
  project_id: string
  title: string
  state: 'incoming' | 'scoped' | 'in_progress' | 'done' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'critical' | null
  sla_due_at?: string | null
  dod_framework?: { criteria: string[] } | null
  version: number
  owner_id?: string | null
}

export interface Task {
  id: string
  task_key: string
  epic_id: string
  title: string
  description: string | null
  state: 'incoming' | 'scoped' | 'ready' | 'in_progress' | 'in_review' | 'done' | 'qa_failed' | 'blocked' | 'escalated' | 'cancelled'
  definition_of_done?: { criteria: string[] } | null
  review_comment?: string | null
  qa_failed_count: number
  version: number
  assigned_to?: string | null
  assigned_node_id?: string | null
  assigned_node_name?: string | null
}

// ─── Skills ────────────────────────────────────────────────────────────────

export interface Skill {
  id: string
  title: string
  content: string
  service_scope: string[]
  stack: string[]
  skill_type: 'system' | 'domain'
  lifecycle: 'draft' | 'active' | 'deprecated'
  federation_scope: 'local' | 'federated'
  origin_node_id: string | null
  origin_node_name: string | null
  created_at: string
}

export interface SkillForkResponse {
  id: string
  title: string
  origin_node_id: string | null
  federation_scope: string
  created: boolean
}

// ─── Federation ────────────────────────────────────────────────────────────

export interface NodeIdentity {
  node_id: string
  node_name: string
  node_url: string
  public_key: string
}

export interface PeerNode {
  id: string
  node_name: string
  node_url: string
  public_key: string | null
  status: 'active' | 'inactive' | 'blocked'
  last_seen: string | null
}

export interface FederationSettings {
  federation_enabled: boolean
  topology: 'direct_mesh' | 'hub_assisted' | 'hub_relay'
  hive_station_url: string
  hive_station_token: string
  hive_relay_enabled: boolean
  heartbeat_interval: number
  peer_timeout: number
}

// ─── Triage ────────────────────────────────────────────────────────────────

export interface TriageItem {
  id: string
  direction: string
  system: string
  entity_type: string
  entity_id: string
  payload: Record<string, unknown>
  routing_state: 'unrouted' | 'routed' | 'ignored' | 'escalated' | 'dead'
  created_at: string
}

export interface McpToolResponse {
  type: string
  text: string
}

export interface PromptResponse {
  data: {
    prompt: string
    token_count: number
  }
}

export interface McpStatus {
  tools_count: number
  transport: string
  connected: boolean
  last_check: string
}
