import { computed, ref } from 'vue'
import { api } from '../api'
import type { BugIssueDetail, NodeBugCountItem } from '../api/types'

interface RGB {
  r: number
  g: number
  b: number
}

export interface BugHeatmapConfig {
  minRadius: number
  maxRadius: number
  maxBugs: number
  neutralToken: string
  warningToken: string
  dangerToken: string
}

export interface NodeBugSummary {
  count: number
  lastSeen: string | null
  stackTraceHashPreview: string | null
}

function toNumber(value: string | undefined, fallback: number): number {
  if (!value) return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const DEFAULT_CONFIG: BugHeatmapConfig = {
  minRadius: toNumber(import.meta.env.VITE_BUG_HEATMAP_MIN_RADIUS, 10),
  maxRadius: toNumber(import.meta.env.VITE_BUG_HEATMAP_MAX_RADIUS, 40),
  maxBugs: Math.max(1, toNumber(import.meta.env.VITE_BUG_HEATMAP_MAX_BUGS, 10)),
  neutralToken: '--color-text-muted',
  warningToken: '--color-warning',
  dangerToken: '--color-danger',
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v))
}

function parseRgb(input: string): RGB | null {
  const value = input.trim()
  if (!value) return null

  if (value.startsWith('#')) {
    const hex = value.slice(1)
    if (hex.length === 3) {
      return {
        r: parseInt(hex[0] + hex[0], 16),
        g: parseInt(hex[1] + hex[1], 16),
        b: parseInt(hex[2] + hex[2], 16),
      }
    }
    if (hex.length === 6) {
      return {
        r: parseInt(hex.slice(0, 2), 16),
        g: parseInt(hex.slice(2, 4), 16),
        b: parseInt(hex.slice(4, 6), 16),
      }
    }
  }

  const rgbMatch = value.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/)
  if (rgbMatch) {
    return {
      r: Math.min(255, Number(rgbMatch[1])),
      g: Math.min(255, Number(rgbMatch[2])),
      b: Math.min(255, Number(rgbMatch[3])),
    }
  }

  return null
}

function rgbString(c: RGB): string {
  return `rgb(${c.r},${c.g},${c.b})`
}

function mixColor(a: string, b: string, t: number): string {
  const start = parseRgb(a)
  const end = parseRgb(b)
  if (!start || !end) return t >= 0.5 ? b : a

  const p = clamp01(t)
  return rgbString({
    r: Math.round(lerp(start.r, end.r, p)),
    g: Math.round(lerp(start.g, end.g, p)),
    b: Math.round(lerp(start.b, end.b, p)),
  })
}

function resolveCssColor(token: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  return value || fallback
}

function bugColor(bugCount: number, config: BugHeatmapConfig): string {
  const neutral = resolveCssColor(config.neutralToken, '#7f92b3')
  const warning = resolveCssColor(config.warningToken, '#ffb020')
  const danger = resolveCssColor(config.dangerToken, '#ff4d6d')

  if (bugCount <= 0) return neutral
  const t = clamp01(bugCount / config.maxBugs)

  if (t <= 0.5) {
    return mixColor(neutral, warning, t / 0.5)
  }
  return mixColor(warning, danger, (t - 0.5) / 0.5)
}

function bugRadius(bugCount: number, config: BugHeatmapConfig): number {
  if (bugCount <= 0) return config.minRadius
  const t = clamp01(bugCount / config.maxBugs)
  return Math.round(config.minRadius + t * (config.maxRadius - config.minRadius))
}

function getLatestLastSeen(issues: BugIssueDetail[]): string | null {
  let latest: string | null = null
  let latestTs = 0

  for (const issue of issues) {
    if (!issue.last_seen) continue
    const ts = Date.parse(issue.last_seen)
    if (!Number.isFinite(ts)) continue
    if (!latest || ts > latestTs) {
      latest = issue.last_seen
      latestTs = ts
    }
  }

  return latest
}

function stackHashPreview(issues: BugIssueDetail[]): string | null {
  const hash = issues.find(issue => issue.stack_trace_hash)?.stack_trace_hash
  if (!hash) return null
  return hash.length <= 12 ? hash : `${hash.slice(0, 12)}...`
}

export function useBugHeatmap(
  projectId?: () => string | undefined,
  configOverrides: Partial<BugHeatmapConfig> = {},
) {
  const config: BugHeatmapConfig = { ...DEFAULT_CONFIG, ...configOverrides }

  const heatmapEnabled = ref(false)
  const bugCounts = ref<NodeBugCountItem[]>([])
  const loading = ref(false)
  const error = ref('')

  const bugNodeMap = computed<Map<string, NodeBugCountItem>>(() => {
    const map = new Map<string, NodeBugCountItem>()
    for (const item of bugCounts.value) {
      map.set(item.node_id, item)
    }
    return map
  })

  async function loadBugCounts(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const pid = projectId?.()
      bugCounts.value = await api.getBugCounts(pid)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Fehler beim Laden der Bug-Counts'
    } finally {
      loading.value = false
    }
  }

  async function toggleHeatmap(): Promise<void> {
    heatmapEnabled.value = !heatmapEnabled.value
    if (heatmapEnabled.value) {
      await loadBugCounts()
    }
  }

  function getNodeRadius(nodeId: string, defaultRadius: number): number {
    if (!heatmapEnabled.value) return defaultRadius
    const count = bugNodeMap.value.get(nodeId)?.bug_count ?? 0
    return bugRadius(count, config)
  }

  function getNodeColor(nodeId: string, defaultColor: string): string {
    if (!heatmapEnabled.value) return defaultColor
    const count = bugNodeMap.value.get(nodeId)?.bug_count ?? 0
    return bugColor(count, config)
  }

  function getBugCount(nodeId: string): number {
    return bugNodeMap.value.get(nodeId)?.bug_count ?? 0
  }

  function getBugIssues(nodeId: string): BugIssueDetail[] {
    return bugNodeMap.value.get(nodeId)?.sentry_issues ?? []
  }

  function getBugSummary(nodeId: string): NodeBugSummary {
    const entry = bugNodeMap.value.get(nodeId)
    const issues = entry?.sentry_issues ?? []

    return {
      count: entry?.bug_count ?? 0,
      lastSeen: getLatestLastSeen(issues),
      stackTraceHashPreview: stackHashPreview(issues),
    }
  }

  return {
    heatmapEnabled,
    loading,
    error,
    bugCounts,
    toggleHeatmap,
    loadBugCounts,
    getNodeRadius,
    getNodeColor,
    getBugCount,
    getBugIssues,
    getBugSummary,
  }
}
