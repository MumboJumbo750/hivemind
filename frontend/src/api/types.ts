export interface Project {
  id: string
  name: string
  slug: string
  description?: string
  repo_host_path?: string | null
  workspace_root?: string | null
  workspace_mode?: 'read_only' | 'read_write' | null
  onboarding_status?: 'pending' | 'ready' | 'error' | null
  default_branch?: string | null
  remote_url?: string | null
  detected_stack?: string[] | null
  created_by?: string
  created_at: string
}

export type ProjectIntegrationProvider = 'youtrack' | 'sentry' | 'in_app' | 'github_projects'
export type ProjectIntegrationStatus = 'active' | 'incomplete' | 'error' | 'disabled'

export interface ProjectIntegration {
  id: string
  project_id: string
  provider: ProjectIntegrationProvider
  display_name?: string | null
  integration_key?: string | null
  base_url?: string | null
  external_project_key?: string | null
  project_selector?: Record<string, unknown> | null
  status_mapping?: Record<string, unknown> | null
  routing_hints?: Record<string, unknown> | null
  config?: Record<string, unknown> | null
  sync_enabled: boolean
  sync_direction: string
  github_repo?: string | null
  github_project_id?: string | null
  status_field_id?: string | null
  priority_field_id?: string | null
  has_webhook_secret: boolean
  has_access_token: boolean
  status: ProjectIntegrationStatus
  status_detail: string
  last_health_state?: string | null
  last_health_detail?: string | null
  health_checked_at?: string | null
  last_event_at?: string | null
  last_error_at?: string | null
  last_error_detail?: string | null
  created_at: string
  updated_at: string
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

export interface EpicRun {
  id: string
  epic_id: string
  started_by: string
  status: 'dry_run' | 'blocked' | 'started' | 'running' | 'waiting' | 'completed'
  dry_run: boolean
  config: Record<string, unknown>
  analysis: Record<string, unknown>
  started_at: string
  completed_at?: string | null
}

export interface EpicStartResponse {
  run_id: string
  epic_key: string
  status: string
  dry_run: boolean
  startable: boolean
  epic_state: string
  config: Record<string, unknown>
  blockers: { code: string; message: string }[]
  analysis: Record<string, unknown>
}

export interface EpicRunArtifact {
  id: string
  epic_run_id: string
  epic_id: string
  task_id?: string | null
  task_key?: string | null
  artifact_type: string
  state: string
  source_role?: string | null
  target_role?: string | null
  title: string
  summary?: string | null
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
  released_at?: string | null
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
  state: 'draft' | 'proposed' | 'accepted' | 'rejected'
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

// ─── Requirement Draft ──────────────────────────────────────────────────────

export interface RequirementDraftResponse {
  prompt: string
  token_count: number
  draft_id: string
  enrichment: {
    priority_hint: string | null
    tags: string[]
  }
  intake: {
    stage: string
    source_kind: string
    materialization: string
    project_id: string
    triage_required: boolean
    context_refs: {
      task_keys: string[]
      epic_keys: string[]
    }
    existing_proposal_id?: string
  }
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
  project_id?: string | null
  integration_id?: string | null
  entity_type: string
  entity_id: string
  payload: Record<string, unknown>
  routing_state: 'unrouted' | 'routed' | 'ignored' | 'escalated' | 'dead'
  routing_detail?: Record<string, unknown> | null
  created_at: string
}

export type SyncProviderState = 'online' | 'degraded' | 'offline' | 'not_configured'

export interface SyncQueueOverview {
  pending_outbound: number
  pending_inbound: number
  dead_letters: number
  delivered_today: number
}

export interface SyncDeliveredItem {
  id: string
  timestamp: string
  direction: string
  payload_type: string
  duration_ms: number | null
}

export interface SyncFailedItem {
  id: string
  timestamp: string
  attempts: number
  last_error: string
  dlq_url: string
}

export interface SyncProviderStatus {
  state: SyncProviderState
  detail: string | null
  checked_at: string
}

export interface SyncStatusResponse {
  queue: SyncQueueOverview
  recent_delivered: SyncDeliveredItem[]
  recent_failed: SyncFailedItem[]
  providers: {
    ollama: SyncProviderStatus
    youtrack: SyncProviderStatus
  }
  checked_at: string
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

// ─── Bug-Heatmap (Phase 7) ─────────────────────────────────────────────────

export interface BugIssueDetail {
  sentry_issue_id: string | null
  count: number
  last_seen: string | null
  stack_trace_hash: string | null
}

export interface NodeBugCountItem {
  node_id: string
  bug_count: number
  sentry_issues: BugIssueDetail[]
}

// ─── KPI Dashboard (Phase 7) ───────────────────────────────────────────────

export type KpiStatus = 'ok' | 'warn' | 'critical'

export interface KpiItem {
  kpi: string
  value: number
  target: number
  status: KpiStatus
  computed_at: string
}

export interface KpiSummaryResponse {
  kpis: KpiItem[]
  computed_at: string | null
}

// ─── KPI History (Phase 8) ─────────────────────────────────────────────────

export interface KpiDataPoint {
  date: string
  value: number
}

export interface KpiHistoryResponse {
  days: number
  series: {
    tasks_done: KpiDataPoint[]
    tasks_in_progress: KpiDataPoint[]
    cycle_time_avg_hours: KpiDataPoint[]
    bug_rate: KpiDataPoint[]
    skill_coverage: KpiDataPoint[]
    review_pass_rate: KpiDataPoint[]
  }
}

// ─── Nexus Grid 3D (Phase 8) ───────────────────────────────────────────────

export interface Node3DItem {
  id: string
  label: string
  type: string
  x: number
  y: number
  z: number
  fog_of_war: boolean
  discovery_count: number
}

export interface Edge3DItem {
  source: string
  target: string
  type: string
}

export interface NexusGraph3DResponse {
  nodes: Node3DItem[]
  edges: Edge3DItem[]
  total_nodes: number
  page: number
  page_size: number
  has_more: boolean
}

// ─── Dead Letter Queue (Phase 7) ───────────────────────────────────────────

export interface DeadLetterItem {
  id: string
  system: string
  entity_type: string
  attempts: number
  last_error: string | null
  error: string | null
  failed_at: string | null
  requeued_at: string | null
  payload_preview: string | null
}

export interface DeadLetterListResponse {
  items: DeadLetterItem[]
  next_cursor: string | null
  has_more: boolean
  total: number
  limit: number
}

// ─── AI Review Recommendations (Phase 8) ──────────────────────────────────

export interface ReviewChecklistItem {
  label: string
  passed: boolean
}

export type ReviewVerdict = 'approve' | 'reject' | 'needs_review'

export interface ReviewRecommendation {
  verdict: ReviewVerdict
  confidence: number          // 0–100
  reasoning: string
  checklist: ReviewChecklistItem[]
  auto_approved?: boolean
  grace_period_ends_at?: string | null
}

// ─── AI Provider Config (Phase 8) ─────────────────────────────────────────

export interface AiProviderConfig {
  agent_role: string
  provider: string
  model: string | null
  endpoint: string | null
  api_key?: string
  has_api_key: boolean
  credential_id: string | null
  credential_name: string | null
  rpm_limit: number | null
  daily_token_budget: number | null
  enabled: boolean
}

export interface AiModelInfo {
  id: string
  name: string
  vendor?: string
  category?: string        // 'powerful' | 'versatile' | 'lightweight'
  premium_multiplier?: number  // e.g. 0.25, 1, 50
  max_context_tokens?: number
  max_prompt_tokens?: number
  max_output_tokens?: number
  supports_vision?: boolean
  supports_tool_calls?: boolean
  supports_streaming?: boolean
}

export interface AiCredential {
  id: string
  name: string
  provider_type: string
  endpoint: string | null
  note: string | null
  has_api_key: boolean
  usage_count: number
}

// ─── Governance Config (Phase 8) ──────────────────────────────────────────

export type GovernanceLevel = 'manual' | 'assisted' | 'auto'

export type GovernanceConfig = Record<string, GovernanceLevel>

// ─── MCP Bridge Config (Phase 8) ──────────────────────────────────────────

export interface McpBridge {
  id: string
  name: string
  namespace: string
  transport: 'http' | 'sse' | 'stdio'
  url_or_command: string
  enabled: boolean
  status: 'connected' | 'disconnected' | 'unknown'
  tool_count: number | null
  blocklist: string[]
  created_at: string
}

export interface McpBridgeTool {
  name: string
  description: string
  blocked: boolean
}

// ─── Dispatch Policies ──────────────────────────────────────────────────────

export interface DispatchPolicy {
  agent_role: string
  preferred_execution_mode: string
  fallback_chain: string[]
  rpm_limit: number
  token_budget: number
  max_parallel: number
  cooldown_seconds: number
  enabled: boolean
  source: 'db' | 'default'
  active_dispatches: number | null
  at_limit: boolean | null
}

export interface DispatchPolicyListResponse {
  policies: DispatchPolicy[]
}

// ─── Agent Thread Sessions ──────────────────────────────────────────────────

export interface AgentSession {
  id: string
  thread_key: string
  agent_role: string
  thread_policy: string
  project_id: string | null
  epic_id: string | null
  task_id: string | null
  status: string
  dispatch_count: number
  summary: string | null
  session_metadata: Record<string, unknown> | null
  started_at: string
  last_activity_at: string
}

export interface AgentSessionListResponse {
  data: AgentSession[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

// ─── Governance Audit ────────────────────────────────────────────────────────

export interface GovernanceAuditEntry {
  id: string
  governance_type: string
  governance_level: string
  target_type: string
  target_ref: string
  status: string
  agent_role: string
  prompt_type: string | null
  action: string | null
  confidence: number | null
  rationale: string | null
  payload: Record<string, unknown> | null
  dispatch_id: string | null
  created_at: string
  executed_at: string | null
}

export interface GovernanceAuditListResponse {
  data: GovernanceAuditEntry[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

export interface GovernanceAuditStatsEntry {
  governance_type: string
  governance_level: string
  count: number
}

export interface GovernanceAuditStats {
  total: number
  auto_approve_rate: number
  veto_count: number
  stats: GovernanceAuditStatsEntry[]
}

// ─── Learning Artifacts ─────────────────────────────────────────────────────

export interface LearningArtifact {
  id: string
  artifact_type: string
  status: string
  source_type: string
  source_ref: string
  source_dispatch_id: string | null
  agent_role: string | null
  project_id: string | null
  epic_id: string | null
  task_id: string | null
  summary: string
  detail: Record<string, unknown> | null
  confidence: number | null
  created_at: string
}

export interface LearningListResponse {
  data: LearningArtifact[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

export interface LearningStatsEntry {
  artifact_type: string
  status: string
  count: number
}

export interface LearningStatsResponse {
  stats: LearningStatsEntry[]
  total: number
  skill_candidates: number
}

// ─── Memory Ledger ─────────────────────────────────────────────────────────

export interface MemorySession {
  id: string
  actor_id: string
  agent_role: string
  scope: string
  scope_id: string | null
  started_at: string
  ended_at: string | null
  entry_count: number
  compacted: boolean
}

export interface MemoryEntry {
  id: string
  actor_id: string
  agent_role: string
  scope: string
  scope_id: string | null
  session_id: string
  content: string
  tags: string[]
  covered_by: string | null
  created_at: string
}

export interface MemorySummary {
  id: string
  actor_id: string
  agent_role: string
  scope: string
  scope_id: string | null
  session_id: string | null
  content: string
  source_entry_ids: string[]
  source_fact_ids: string[]
  source_count: number
  open_questions: string[]
  graduated: boolean
  graduated_to: Record<string, unknown> | null
  created_at: string
}

export interface MemorySessionListResponse {
  data: MemorySession[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

export interface MemoryEntryListResponse {
  data: MemoryEntry[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

export interface MemorySummaryListResponse {
  data: MemorySummary[]
  total_count: number
  has_more: boolean
  page: number
  page_size: number
}

export interface MemorySearchResult {
  level: 'L0' | 'L1' | 'L2'
  id: string
  scope?: string
  scope_id?: string | null
  content?: string
  tags?: string[]
  created_at?: string
  search_mode: 'text' | 'semantic' | 'hybrid'
  similarity?: number
  entry_id?: string
  entity?: string
  key?: string
  value?: string
  confidence?: number
  source_tags?: string[]
  open_questions?: string[]
  graduated?: boolean
}

export interface MemorySearchResponse {
  results: MemorySearchResult[]
  count: number
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
