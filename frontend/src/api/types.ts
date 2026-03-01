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
  backup_owner_id?: string | null
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

// ─── Context Boundary ──────────────────────────────────────────────────────

export interface ContextBoundary {
  id: string
  task_id: string
  allowed_skills: string[] | null
  allowed_docs: string[] | null
  external_access: string[] | null
  max_token_budget: number | null
  version: number
  set_by: string
  created_at: string
}

// ─── Skills ────────────────────────────────────────────────────────────────

export interface Skill {
  id: string
  title: string
  content: string
  service_scope: string[]
  stack: string[]
  skill_type: 'system' | 'domain'
  lifecycle: 'draft' | 'active' | 'pending_merge' | 'rejected' | 'deprecated'
  federation_scope: 'local' | 'federated'
  confidence: number
  token_count: number | null
  version: number
  owner_id: string | null
  proposed_by: string | null
  proposed_by_username: string | null
  rejection_rationale: string | null
  origin_node_id: string | null
  origin_node_name: string | null
  created_at: string
  updated_at: string | null
}

export interface SkillVersion {
  id: string
  skill_id: string
  version: number
  content: string
  token_count: number | null
  diff_from_previous: string | null
  changed_by: string
  created_at: string
}

export interface SkillListResponse {
  data: Skill[]
  total_count: number
  has_more: boolean
}

export interface SkillForkResponse {
  id: string
  title: string
  origin_node_id: string | null
  federation_scope: string
  created: boolean
}

// ─── Epic Proposals ────────────────────────────────────────────────────────

export interface EpicProposal {
  id: string
  project_id: string
  proposed_by: string
  proposed_by_username: string | null
  title: string
  description: string
  rationale: string | null
  state: 'proposed' | 'accepted' | 'rejected'
  depends_on: string[] | null
  resulting_epic_id: string | null
  rejection_reason: string | null
  version: number
  created_at: string
  updated_at: string
}

export interface EpicProposalListResponse {
  data: EpicProposal[]
  total_count: number
  has_more: boolean
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

export interface AuditEntry {
  id: string
  actor_id: string
  actor_username: string | null
  actor_role: string
  tool_name: string
  epic_id: string | null
  target_id: string | null
  input_snapshot: Record<string, unknown> | null
  input_truncated: boolean
  output_snapshot: Record<string, unknown> | null
  output_truncated: boolean
  duration_ms: number | null
  status: string
  created_at: string
}

export interface AuditListResponse {
  data: AuditEntry[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

// ─── Notifications (Phase 6) ───────────────────────────────────────────────

export interface HivemindNotification {
  id: string
  user_id: string
  type: string
  priority: 'action_now' | 'soon' | 'fyi'
  title: string
  body: string | null
  link: string | null
  entity_type: string | null
  entity_id: string | null
  read: boolean
  created_at: string
}

// ─── Decision Requests ─────────────────────────────────────────────────────

export interface DecisionRequest {
  id: string
  task_id: string | null
  epic_id: string | null
  owner_id: string | null
  backup_owner_id: string | null
  state: 'open' | 'resolved' | 'expired'
  sla_due_at: string | null
  payload: Record<string, unknown> | null
  resolved_by: string | null
  resolved_at: string | null
  created_at: string
}
