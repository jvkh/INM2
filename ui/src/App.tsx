import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, useTransition, type CSSProperties, type FormEvent, type MouseEvent, type ReactNode } from 'react'
import {
  Activity, ArrowDown, ArrowDownRight, ArrowRight, ArrowUp, ArrowUpRight, BarChart3, Bell, Blocks, BookOpenText, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, ChevronsLeft, ChevronsRight, CircleHelp,
  Clock3, Command, Copy, Database, FileText, Filter, Globe2, LayoutDashboard, List, LockKeyhole, LockOpen, Menu,
  Network, Search, Settings, Settings2, ShieldAlert, SkipBack, SkipForward, Sun, Trash2, Users, X, LogOut, Bug, Shield,
} from 'lucide-react'
import { messages, type Language, type MessageKey } from './i18n'

type Theme = 'auto' | 'cloud' | 'midnight' | 'moss'
type PageKey = 'dashboard' | 'bursts' | 'incidents' | 'actors' | 'hosts' | 'categories' | 'requests' | 'statistics' | 'administration' | 'categoryGuide' | 'burstGuide' | 'countGuide' | 'hostGuide' | 'pathsGuide' | 'incidentGuide' | 'logging' | 'honeypot' | 'cowrie' | 'honeypotGuide' | 'cowrieGuide'
const pageKeys: PageKey[] = ['dashboard', 'bursts', 'incidents', 'actors', 'hosts', 'categories', 'requests', 'statistics', 'administration', 'categoryGuide', 'burstGuide', 'countGuide', 'hostGuide', 'pathsGuide', 'incidentGuide', 'logging', 'honeypot', 'cowrie', 'honeypotGuide', 'cowrieGuide']
function pageFromUrl(): PageKey | null {
  const value = new URLSearchParams(window.location.search).get('page')
  return value && pageKeys.includes(value as PageKey) ? value as PageKey : null
}
function writePageToUrl(page: PageKey, replace = false) {
  const url = new URL(window.location.href)
  url.searchParams.set('page', page)
  if (replace) window.history.replaceState({ page }, '', url)
  else window.history.pushState({ page }, '', url)
}
type TableKey = 'bursts' | 'actors' | 'hosts' | 'categories' | 'requests' | 'honeypot'
type PageSize = 10 | 25 | 50 | 100 | 200 | 500
const allowedPageSizes: PageSize[] = [10, 25, 50, 100, 200, 500]
const defaultTablePageSize: PageSize = 25
type BurstSortColumn = 'burst_id' | 'start_time' | 'actor_ip' | 'host' | 'country' | 'duration' | 'requests' | 'avg_count'
type BurstSort = { column: BurstSortColumn; direction: 'asc' | 'desc' }
type BurstFilters = { search: string; host: string; known: '' | 'own' | 'foreign'; country: string; protectedOnly: boolean }
type ActorSortColumn = 'ip' | 'first_time' | 'last_time' | 'provider' | 'asn' | 'city' | 'country' | 'request_count'
type ActorSort = { column: ActorSortColumn; direction: 'asc' | 'desc' }
type ActorFilters = { search: string; country: string; protectedOnly: boolean }
type HostSortColumn = 'host' | 'total_count' | 'read_count' | 'write_count' | 'other_count' | 'https_count' | 'https_share'
type HostSort = { column: HostSortColumn; direction: 'asc' | 'desc' }
type HostFilters = { search: string; known: '' | 'own' | 'foreign' }
type CategorySortColumn = 'category_name' | 'total_count' | 'read_count' | 'write_count' | 'other_count' | 'traffic_share' | 'https_share'
type CategorySort = { column: CategorySortColumn; direction: 'asc' | 'desc' }
type CategoryFilters = { search: string }
type RequestSortColumn = 'start_utc' | 'request_method' | 'request_path' | 'user_agent' | 'downstream_status' | 'actor_ip' | 'host' | 'duration' | 'downstream_content_size' | 'request_content_size'
type RequestSort = { column: RequestSortColumn; direction: 'asc' | 'desc' }
type RequestFilters = { search: string; status: '' | '2xx' | '3xx' | '4xx' | '5xx'; withoutBurst: boolean }
type HoneypotSortColumn = 'time' | 'client_ip' | 'request_count' | 'post_count' | 'path_count' | 'body_bytes'
type HoneypotSort = { column: HoneypotSortColumn; direction: 'asc' | 'desc' }
type HoneypotFilters = { search: string; postsOnly: boolean; protectedOnly: boolean }
type IncidentFilters = { search: string; state: '' | 'open' | 'acknowledged' | 'resolved'; incidentType: '' | IncidentType; protectedOnly: boolean }
type CowrieFilters = { search: string; eventType: string; protectedOnly: boolean; detailSearch: string }
const defaultBurstSort: BurstSort = { column: 'start_time', direction: 'asc' }
const defaultBurstFilters: BurstFilters = { search: '', host: '', known: '', country: '', protectedOnly: false }
const defaultActorSort: ActorSort = { column: 'first_time', direction: 'asc' }
const defaultActorFilters: ActorFilters = { search: '', country: '', protectedOnly: false }
const defaultHostSort: HostSort = { column: 'total_count', direction: 'desc' }
const defaultHostFilters: HostFilters = { search: '', known: '' }
const defaultCategorySort: CategorySort = { column: 'category_name', direction: 'asc' }
const defaultCategoryFilters: CategoryFilters = { search: '' }
const defaultRequestSort: RequestSort = { column: 'start_utc', direction: 'desc' }
const defaultRequestFilters: RequestFilters = { search: '', status: '', withoutBurst: false }
const defaultHoneypotSort: HoneypotSort = { column: 'time', direction: 'desc' }
const defaultHoneypotFilters: HoneypotFilters = { search: '', postsOnly: false, protectedOnly: false }
const defaultIncidentFilters: IncidentFilters = { search: '', state: '', incidentType: '', protectedOnly: false }
const defaultCowrieFilters: CowrieFilters = { search: '', eventType: '', protectedOnly: false, detailSearch: '' }

type SearchField = 'ip' | 'host' | 'country' | 'city' | 'provider' | 'asn' | 'path' | 'category' | 'method' | 'status' | 'scheme' | 'user_agent'
// Keep localized aliases in sync with common/search.py. English canonical names
// always work, regardless of the selected interface language.
const searchFieldAliases: Record<string, SearchField> = {
  ip: 'ip', actor: 'ip', akteur: 'ip', host: 'host', country: 'country', land: 'country',
  city: 'city', stadt: 'city', provider: 'provider', anbieter: 'provider', asn: 'asn',
  path: 'path', pfad: 'path', category: 'category', kategorie: 'category',
  method: 'method', methode: 'method', status: 'status', scheme: 'scheme', protokoll: 'scheme',
  ua: 'user_agent', 'user-agent': 'user_agent', user_agent: 'user_agent',
}

function parseSearchField(value: string): { field: SearchField | null; term: string } {
  const separator = value.indexOf(':')
  if (separator < 0) return { field: null, term: value.trim() }
  const field = searchFieldAliases[value.slice(0, separator).trim().toLowerCase()]
  return field ? { field, term: value.slice(separator + 1).trim() } : { field: null, term: value.trim() }
}

const navigation: { key: PageKey; icon: typeof LayoutDashboard }[] = [
  { key: 'dashboard', icon: LayoutDashboard }, { key: 'bursts', icon: Activity },
  { key: 'incidents', icon: ShieldAlert },
  { key: 'actors', icon: Users }, { key: 'hosts', icon: Globe2 },
  { key: 'categories', icon: Blocks }, { key: 'requests', icon: List },
  { key: 'statistics', icon: BarChart3 },
]

type RangePreset = 'last24h' | 'today' | 'yesterday' | 'last6h' | 'last7d' | 'last30d' | 'last90d' | 'custom'
type DashboardChartMode = 'requests' | 'bursts' | 'incidents'
type TimeRange = { from: Date; to: Date; preset: RangePreset; query: string }
type TrafficBucket = { from: string; to: string; source?: 'honeypot-group' }
type StatisticsSection = 'overview' | 'traffic' | 'patterns' | 'hostsActors' | 'insights' | 'incidents' | 'honeypot' | 'ssh'
type CountryStatisticsItem = { name: string | null; event_count: number; group_count: number; event_share_percent: number; group_share_percent: number }
type HoneypotStatistics = { access_count: number; matched_access_count: number; unmatched_access_count: number; matched_incident_count: number; by_method: StatisticsItem[]; by_rule: StatisticsItem[]; countries: CountryStatisticsItem[]; timeline: { from: string; to: string; request_count: number }[] }
type HoneypotSummary = { request_count: number; actor_count: number; post_with_data_count: number; uploaded_execution_attempt_count: number }
type IncidentStatistics = { incident_count: number; actor_count: number; host_count: number; linked_request_count: number; by_type: StatisticsItem[]; timeline: { from: string; to: string; incident_count: number; incidents?: NotificationIncident[] }[]; top_actors: StatisticsItem[]; top_hosts: StatisticsItem[]; error_metrics: { incident_count: number; error_count: number; non_error_count: number; non_error_share_percent: number }; request_spike_metrics: { incident_count: number; average_rps: number | null; min_rps: number | null; max_rps: number | null } }
type UiPreferences = { language?: Language; theme?: Theme; lastPage?: PageKey; sidebarCollapsed?: boolean; systemNavOpen?: boolean; helpNavOpen?: boolean; dashboardChartMode?: DashboardChartMode; dashboardOverviewMode?: 'bursts' | 'incidents'; dashboardTableMode?: 'bursts' | 'incidents'; statisticsSection?: StatisticsSection; statisticsCountryMode?: 'events' | 'groups'; cowrieGroupPanel?: CowrieGroupPanel; timeRange?: { preset: RangePreset; from?: string; to?: string }; tablePageSizes?: Partial<Record<TableKey, PageSize>>; burstSort?: BurstSort; burstFilters?: BurstFilters; actorSort?: ActorSort; actorFilters?: ActorFilters; hostSort?: HostSort; hostFilters?: HostFilters; categorySort?: CategorySort; categoryFilters?: CategoryFilters; requestSort?: RequestSort; requestFilters?: RequestFilters; honeypotSort?: HoneypotSort; honeypotFilters?: HoneypotFilters; incidentFilters?: IncidentFilters; cowrieFilters?: CowrieFilters }
type ApiResult<T> = { items: T[]; total?: number; total_count?: number; known_count?: number; summary?: Record<string, number | null> }
type ActorItem = { actor_id: number; ip: string; first_time: string; last_time: string; provider: string | null; asn: string | null; city: string | null; country: string | null; request_count: number; total_request_count: number; burst_count: number }
type BurstItem = { burst_id: number; actor_ip: string; country: string | null; provider: string | null; asn: string | null; city: string | null; host: string | null; known: number; start_time: string; end_time: string; avg_count: number; read_count: number; write_count: number; other_count: number }
type HostItem = { host_id: number; host: string; known: number; total_count: number; read_count: number; write_count: number; other_count: number; http_count: number; https_count: number; other_scheme_count: number }
type CategoryItem = { category_id: number; category_name: string; total_count: number; read_count: number; write_count: number; other_count: number; http_count: number; https_count: number; other_scheme_count: number }
type RequestItem = { request_id: number; start_utc: string; actor_ip: string; provider: string | null; asn: string | null; city: string | null; country: string | null; host: string | null; host_known: number; request_method: string; request_path: string; request_scheme: string; user_agent: string | null; categories: string | null; downstream_status: number; downstream_content_size: number; request_content_size: number | null; duration: number }
type GlobalSearchActor = Pick<ActorItem, 'actor_id' | 'ip' | 'provider' | 'asn' | 'city' | 'country' | 'request_count'>
type GlobalSearchHost = Pick<HostItem, 'host_id' | 'host' | 'total_count'>
type GlobalSearchCategory = Pick<CategoryItem, 'category_id' | 'category_name' | 'total_count'>
type GlobalSearchPath = { path: string; request_count: number; last_seen: string }
type GlobalSearchResults = { actors: GlobalSearchActor[]; hosts: GlobalSearchHost[]; categories: GlobalSearchCategory[]; paths: GlobalSearchPath[] }
type NotificationRequest = { request_id: number; start_utc: string; actor_ip: string; provider: string | null; asn: string | null; country: string | null; city: string | null; host: string | null; host_known: number; request_method: string; request_path: string; downstream_status: number | null }
type NotificationBurst = { burst_id: number; start_time: string; actor_ip: string; provider: string | null; asn: string | null; country: string | null; city: string | null; host: string | null; request_count: number }
type IncidentType = 'path_scan' | 'failed_login' | 'sensitive_file_access' | 'exploit_response' | 'write_activity' | 'http_error_spike' | 'scanner_activity' | 'activity_spike' | 'dormant_host_activity' | 'low_slow_path_scan' | 'unknown_host_404_activity'
type NotificationIncident = { incident_id: number; incident_type: IncidentType; incident_types?: IncidentType[]; first_seen: string; last_seen: string; request_count: number; indicator_count: number; indicators: string[]; summary: Record<string, number>; actor_ip: string; country: string | null; city: string | null; provider: string | null; asn: string | null; host: string | null }
type Incident = NotificationIncident & { actor_id: number; state: 'open' | 'acknowledged' | 'resolved' }
type NotificationData = { request_count: number; request_since_utc: string | null; burst_count: number; incident_count: number; requests: NotificationRequest[]; bursts: NotificationBurst[]; incidents: NotificationIncident[]; request_cursor: number; burst_cursor: number; incident_cursor: number }
type StatusData = { status: string; database: string; honeypot_available: boolean; honeypot_configured: boolean; cowrie_configured: boolean; cowrie_available: boolean; collector_status: { available: boolean; last_import: string | null; activity: string; import_file: string; last_import_file: string; import_count: number; last_import_files: { file: string; count: number }[] }; environment: Record<string, string> }
type LogService = 'collector' | 'api' | 'ui_access' | 'ui_error'
type LogResponse = { service: LogService; content: string; truncated: boolean }
type HoneypotEvent = { event_id: string; time: string; client_ip: string | null; provider: string | null; asn: string | null; country: string | null; city: string | null; host: string | null; scheme: string | null; session_id: string | null; session_phase: string | null; method: string; path: string; user_agent: string | null; content_type: string | null; body_bytes: number; body_clipped: number; body_sha256: string | null; rule: string | null; response_page: string | null; status: number | null; duration: number; has_body: number }
type HoneypotGroup = { first_time: string; last_time: string; client_ip: string | null; provider: string | null; asn: string | null; country: string | null; city: string | null; request_count: number; post_count: number; body_count: number; body_bytes: number; path_count: number }
type HoneypotGroupsResponse = { items: HoneypotGroup[]; total: number; total_events: number; limit: number; offset: number; session_gap_seconds: number }
type HoneypotEventsResponse = { items: HoneypotEvent[]; total: number }
type HoneypotEventDetail = Omit<HoneypotEvent, 'has_body'> & { body_text: string | null; body_base64: string | null; body_file: string | null }
type CowrieEvent = { event_id: string; time: string; src_ip: string | null; session: string | null; event_type: string; username: string | null; password: string | null; input: string | null; message: string | null; sensor: string | null; provider: string | null; asn: string | null; country: string | null; city: string | null; extra_json: string | null }
type CowrieGroup = { first_time: string; last_time: string; src_ip: string | null; provider: string | null; asn: string | null; country: string | null; city: string | null; event_count: number; failed_login_count: number; command_count: number; tty_recording_count: number }
type CowrieCommandAnalysis = { normalized_command: string; command: string; occurrences: number; session_count: number; first_time: string; last_time: string; category: 'persistence' | 'credential_access' | 'download' | 'execution' | 'destructive' | 'discovery' | 'other' }
type CowrieCommandSequence = { commands: string[]; session_count: number; first_time: string; last_time: string }
type CowrieGroupAnalysis = { src_ip: string; from: string; to: string; commands: CowrieCommandAnalysis[]; command_total: number; command_sequences: CowrieCommandSequence[]; command_sequence_total: number; command_sequences_truncated: boolean }
type CowrieSummary = { event_count: number; actor_count: number; session_count: number; failed_login_count: number; command_count: number }
type CowrieStatistics = CowrieSummary & { by_type: { name: string; event_count: number; share_percent: number }[]; countries: CountryStatisticsItem[]; timeline: { from: string; to: string; event_count: number }[] }
type BurstResponse = { summary: Record<string, number | null>; items: BurstItem[]; total?: number; limit: number; offset: number }
type CountItem = { read_count: number; write_count: number; other_count: number; total_count?: number; from?: string; to?: string }
type StatisticsItem = { name: string | null; request_count: number; share_percent: number; known?: number; status_class?: string; total_count?: number; provider?: string | null; asn?: string | null; country?: string | null; city?: string | null }
type StatisticsBucket = { from: string; to: string; known_count?: number; other_count?: number; actor_count?: number; host_count?: number }
type StatisticsResponse = { total_requests: number; burst_count: number; burst_request_count: number; non_burst_request_count: number; burst_request_share_percent: number; avg_requests_per_burst: number | null; min_requests_per_burst: number | null; max_requests_per_burst: number | null; avg_burst_duration_seconds: number | null; min_burst_duration_seconds: number | null; max_burst_duration_seconds: number | null; min_duration_request_count: number | null; max_duration_request_count: number | null; incident_count: number; avg_requests_per_incident: number | null; min_requests_per_incident: number | null; max_requests_per_incident: number | null; min_requests_incident: NotificationIncident | null; max_requests_incident: NotificationIncident | null; avg_incident_duration_seconds: number | null; min_incident_duration_seconds: number | null; max_incident_duration_seconds: number | null; min_duration_incident: NotificationIncident | null; max_duration_incident: NotificationIncident | null; incident_request_count: number; non_incident_request_count: number; incident_request_share_percent: number; providers: StatisticsItem[]; countries: StatisticsItem[]; hosts: StatisticsItem[]; categories: StatisticsItem[]; status_codes: StatisticsItem[]; burst_sizes: StatisticsItem[]; methods: StatisticsItem[]; paths: StatisticsItem[]; host_traffic: StatisticsBucket[]; new_entities: StatisticsBucket[]; request_gaps: StatisticsItem[] }
type StatisticsInsights = { error_hosts: StatisticsItem[]; error_paths: StatisticsItem[]; active_actors: (StatisticsItem & { provider: string | null; asn: string | null; country: string | null; city: string | null })[]; weekday_hours: { weekday: number; hour: number; request_count: number }[]; status_trend: { bucket_index: number; from_utc: string; to_utc: string; status_1xx: number; status_2xx: number; status_3xx: number; status_4xx: number; status_5xx: number }[] }
type BurstExtreme = 'min_requests' | 'max_requests' | 'min_duration' | 'max_duration'
type StatisticRequestFilter = { field: 'provider' | 'country'; value: string }
type BurstChartItem = Pick<BurstItem, 'burst_id' | 'start_time' | 'end_time' | 'avg_count' | 'read_count' | 'write_count' | 'other_count' | 'actor_ip' | 'provider' | 'asn' | 'city' | 'country' | 'host'>
type BurstChartBucket = { from: string; to: string; burst_count: number; bursts: BurstChartItem[] }
type BurstChartResponse = { items: BurstChartBucket[]; from: string; to: string; bars: number }

let pendingApiRequests = 0
let liveRefreshVersion = 0
const liveRefreshListeners = new Set<() => void>()
function subscribeLiveRefresh(listener: () => void) { liveRefreshListeners.add(listener); return () => liveRefreshListeners.delete(listener) }
function getLiveRefreshVersion() { return liveRefreshVersion }
function triggerLiveRefresh() {
  liveRefreshVersion += 1
  liveRefreshListeners.forEach((listener) => listener())
}
const apiRequestListeners = new Set<() => void>()
function updatePendingApiRequests(delta: number) {
  pendingApiRequests = Math.max(0, pendingApiRequests + delta)
  apiRequestListeners.forEach((listener) => listener())
}
function subscribeToApiRequests(listener: () => void) {
  apiRequestListeners.add(listener)
  return () => apiRequestListeners.delete(listener)
}
function getPendingApiRequests() { return pendingApiRequests }
type PagedResponse<T> = { items: T[]; total: number; limit: number; offset: number }
type RequestPageResponse = PagedResponse<RequestItem> & { matching_burst_count?: number; burst_extreme_value?: number | null }

function makeRange(preset: RangePreset, start?: string, end?: string): TimeRange {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  let from: Date
  let to = now
  if (preset === 'last24h') from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  else if (preset === 'today') from = today
  else if (preset === 'yesterday') {
    to = today
    from = new Date(to.getFullYear(), to.getMonth(), to.getDate() - 1)
  } else if (preset === 'last6h') from = new Date(now.getTime() - 6 * 60 * 60 * 1000)
  else if (preset === 'last7d') from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6)
  else if (preset === 'last30d') from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29)
  else if (preset === 'last90d') from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 89)
  else {
    from = new Date(start ?? '')
    to = new Date(end ?? '')
  }
  const query = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() }).toString()
  return { from, to, preset, query }
}

function trafficBucketOptions(range: TimeRange): Record<string, string> {
  if (range.preset === 'custom') return { bars: '20' }
  const minutesByPreset: Partial<Record<RangePreset, number>> = {
    last24h: 60, today: 60, yesterday: 60, last6h: 15,
    last7d: 480, last30d: 1440, last90d: 4320,
  }
  const bucketMinutes = minutesByPreset[range.preset] ?? 60
  const anchor = new Date(range.from)
  // Rolling ranges must start at their exact filter boundary; rounding the
  // anchor creates a gap at the end of the fixed 24 buckets.
  return {
    bars: '24', bucket_minutes: String(bucketMinutes), bucket_anchor: anchor.toISOString(),
    bucket_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  }
}

function localDateInput(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function localDateTimeInput(date: Date) {
  return `${localDateInput(date)}T${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function countryFlag(country: string | null | undefined) {
  if (!country) return '🌐'
  const codeByName: Record<string, string> = {
    australia: 'AU', austria: 'AT', belgium: 'BE', brazil: 'BR', bulgaria: 'BG', canada: 'CA',
    china: 'CN', colombia: 'CO', croatia: 'HR', cyprus: 'CY', czechia: 'CZ', 'czech republic': 'CZ',
    denmark: 'DK', egypt: 'EG', finland: 'FI', france: 'FR', germany: 'DE', greece: 'GR',
    hungary: 'HU', india: 'IN', indonesia: 'ID', ireland: 'IE', israel: 'IL', italy: 'IT', japan: 'JP',
    lithuania: 'LT', luxembourg: 'LU', malaysia: 'MY', mexico: 'MX', netherlands: 'NL', nigeria: 'NG', norway: 'NO', pakistan: 'PK', panama: 'PA', poland: 'PL',
    portugal: 'PT', romania: 'RO', russia: 'RU', singapore: 'SG', slovakia: 'SK', slovenia: 'SI',
    seychelles: 'SC', 'south africa': 'ZA', 'south korea': 'KR', spain: 'ES', sweden: 'SE', switzerland: 'CH',
    taiwan: 'TW', thailand: 'TH', turkey: 'TR', ukraine: 'UA', 'united kingdom': 'GB',
    'united arab emirates': 'AE', 'united states': 'US', 'united states of america': 'US', vietnam: 'VN',
    'russian federation': 'RU', turkiye: 'TR', 'viet nam': 'VN', 'north korea': 'KP',
    'democratic people s republic of korea': 'KP', 'republic of korea': 'KR',
    'iran islamic republic of': 'IR', iran: 'IR', 'syrian arab republic': 'SY', syria: 'SY',
    'lao people s democratic republic': 'LA', laos: 'LA', 'brunei darussalam': 'BN', brunei: 'BN',
    'moldova republic of': 'MD', moldova: 'MD', 'tanzania united republic of': 'TZ', tanzania: 'TZ',
    'venezuela bolivarian republic of': 'VE', venezuela: 'VE', 'bolivia plurinational state of': 'BO', bolivia: 'BO',
    'ivory coast': 'CI', 'cote d ivoire': 'CI', 'democratic republic of the congo': 'CD',
    'congo the democratic republic of the': 'CD', 'republic of the congo': 'CG', 'congo': 'CG',
    'north macedonia': 'MK', 'palestine state of': 'PS', palestine: 'PS', 'taiwan province of china': 'TW',
    'hong kong': 'HK', 'macao': 'MO', 'macau': 'MO', 'united states minor outlying islands': 'UM',
  }
  const normalized = country.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/^the\s+/, '').replace(/[^a-z0-9]+/g, ' ').trim()
  const code = /^[a-z]{2}$/i.test(country.trim()) ? country.trim().toUpperCase() : codeByName[normalized] ?? countryCodeByEnglishName[normalized]
  if (!code) return '🌐'
  return String.fromCodePoint(...[...code].map((letter) => 127397 + letter.charCodeAt(0)))
}

const isoCountryCodes = 'AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split(' ')
const countryDisplayNames = typeof Intl.DisplayNames === 'undefined' ? null : new Intl.DisplayNames(['en'], { type: 'region' })
const countryCodeByEnglishName = Object.fromEntries(isoCountryCodes.map((code) => {
  const name = countryDisplayNames?.of(code) ?? code
  const normalized = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/^the\s+/, '').replace(/[^a-z0-9]+/g, ' ').trim()
  return [normalized, code]
})) as Record<string, string>

function ActorMetadata({ provider, asn, country, city, className = '' }: { provider?: string | null; asn?: string | null; country?: string | null; city?: string | null; className?: string }) {
  return <span className={`actor-metadata ${className}`.trim()}>
    <small>{provider?.trim() || '—'} · {asn?.trim() || '—'}</small>
    <small className="country-cell"><span className="country-flag" title={country || ''}>{countryFlag(country)}</span>{country?.trim() || '—'} · {city?.trim() || '—'}</small>
  </span>
}

function MaintenanceExclusionToggle({ ip, t }: { ip?: string | null; t: (key: MessageKey) => string }) {
  const [excluded, setExcluded] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!ip) return
    let active = true
    apiFetch(apiUrl(`maintenance/exclusions/${encodeURIComponent(ip)}`), { headers: { Accept: 'application/json' } })
      .then((response) => response.ok ? response.json() : null)
      .then((data) => { if (active && data) setExcluded(Boolean(data.excluded)) })
      .catch(() => {})
    return () => { active = false }
  }, [ip])
  if (!ip) return null
  const toggle = async () => {
    if (excluded === null || saving) return
    const previous = excluded
    const next = !previous
    setExcluded(next)
    setSaving(true)
    try {
      const response = await apiFetch(apiUrl(`maintenance/exclusions/${encodeURIComponent(ip)}`), {
        method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ excluded: next }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setExcluded(Boolean((await response.json()).excluded))
    } catch {
      setExcluded(previous)
    } finally { setSaving(false) }
  }
  return <button type="button" className={`maintenance-exclusion-toggle${excluded ? ' is-excluded' : ''}`} onClick={() => void toggle()} disabled={excluded === null || saving} title={excluded ? t('maintenanceIncluded') : t('maintenanceExclude')} aria-label={`${excluded ? t('maintenanceIncluded') : t('maintenanceExclude')}: ${ip}`}><Shield size={16} fill={excluded ? 'var(--maintenance-shield-fill)' : 'none'} stroke='var(--muted)' strokeWidth={2.5} /></button>
}

function rangeLabel(range: TimeRange, t: (key: MessageKey) => string, language: Language) {
  const key: Partial<Record<RangePreset, MessageKey>> = { last24h: 'last24h', today: 'todayRange', yesterday: 'yesterdayRange', last6h: 'last6h', last7d: 'last7d', last30d: 'last30d', last90d: 'last90d' }
  if (range.preset !== 'custom') return t(key[range.preset] ?? 'last24h')
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' })
  return `${formatter.format(range.from)} – ${formatter.format(range.to)}`
}

function rangeTick(range: TimeRange, fraction: number, language: Language, timeOnly = false) {
  const value = new Date(range.from.getTime() + (range.to.getTime() - range.from.getTime()) * fraction)
  const locale = language === 'de' ? 'de-DE' : 'en-GB'
  const options: Intl.DateTimeFormatOptions = timeOnly || range.to.getTime() - range.from.getTime() <= 24 * 60 * 60 * 1000
    ? { hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit' }
  return new Intl.DateTimeFormat(locale, options).format(value)
}

function timelineAxisLabels(range: TimeRange, from: string | undefined, to: string | undefined, language: Language) {
  if (!from || !to) return []
  const chartRange = { ...range, from: new Date(from), to: new Date(to) }
  return [0, .25, .5, .75, 1].map((fraction) => rangeTick(chartRange, fraction, language, range.preset === 'last24h'))
}

function useApiData<T>(url: string | null, showActivityToast = true, pollIntervalMs = 0) {
  const refreshVersion = useSyncExternalStore(subscribeLiveRefresh, getLiveRefreshVersion, getLiveRefreshVersion)
  const [data, setData] = useState<T | null>(null)
  const dataRef = useRef<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const previousUrl = useRef<string | null>(null)
  const previousRefreshVersion = useRef(refreshVersion)
  const silentReload = useRef(false)

  useEffect(() => {
    const isImportRefresh = previousRefreshVersion.current !== refreshVersion
    previousRefreshVersion.current = refreshVersion
    const showToastForRequest = showActivityToast && !isImportRefresh && !silentReload.current
    silentReload.current = false
    if (url === null) {
      previousUrl.current = null
      dataRef.current = null
      setData(null)
      setLoading(false)
      setError(null)
      return
    }
    const controller = new AbortController()
    let requestFinished = false
    let pollTimer: number | undefined
    const finishRequest = () => {
      if (!requestFinished) {
        requestFinished = true
        if (showToastForRequest) updatePendingApiRequests(-1)
      }
    }
    if (showToastForRequest) updatePendingApiRequests(1)
    if (dataRef.current === null || previousUrl.current !== url) setLoading(true)
    previousUrl.current = url
    setError(null)
    apiFetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<T>
      })
      .then((result) => { if (!controller.signal.aborted) { dataRef.current = result; setData(result) } })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || (reason instanceof DOMException && reason.name === 'AbortError')) return
        setError(reason instanceof Error ? reason.message : 'Request failed')
      })
      .finally(() => {
        finishRequest()
        if (!controller.signal.aborted) {
          setLoading(false)
          if (pollIntervalMs > 0) pollTimer = window.setTimeout(() => {
            silentReload.current = true
            setReloadKey((key) => key + 1)
          }, pollIntervalMs)
        }
      })
    return () => { if (pollTimer !== undefined) window.clearTimeout(pollTimer); finishRequest(); controller.abort() }
  }, [url, reloadKey, showActivityToast, pollIntervalMs, refreshVersion])

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  return { data, loading, error, reload }
}

function apiUrl(path: string, query?: string, extras?: Record<string, string>) {
  const params = new URLSearchParams(query ?? '')
  for (const [key, value] of Object.entries(extras ?? {})) params.set(key, value)
  return `/api/v1/${path}${params.size ? `?${params.toString()}` : ''}`
}

async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, { ...init, credentials: 'same-origin' })
  if (response.status === 401 && !String(input).includes('/auth/')) {
    window.dispatchEvent(new Event('inm2-auth-expired'))
  }
  return response
}

type MetricTrendKey = 'request_count' | 'error_request_count' | 'write_request_count' | 'burst_count' | 'incident_count' | 'actor_count' | 'new_actor_count' | 'country_count' | 'host_count' | 'category_count' | 'top_host_request_count' | 'top_category_request_count' | 'https_share' | 'burst_actor_count' | 'burst_request_count' | 'avg_burst_duration' | 'avg_requests_per_actor'
type MetricTrend = { current: number; previous: number; change_percent: number; direction: 'up' | 'down' | 'steady' }
type MetricTrendResponse = { metrics: Partial<Record<MetricTrendKey, MetricTrend>> }
function useMetricTrends(range: TimeRange, page: string, filters: Record<string, string> = {}) {
  const refreshVersion = useSyncExternalStore(subscribeLiveRefresh, getLiveRefreshVersion, getLiveRefreshVersion)
  const extras = Object.fromEntries(Object.entries({ page, ...filters }).filter(([, value]) => value))
  const url = apiUrl('metric_trends', range.query, extras)
  const [result, setResult] = useState<{ url: string; data: MetricTrendResponse } | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    apiFetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<MetricTrendResponse>
      })
      .then((data) => { if (!controller.signal.aborted) setResult({ url, data }) })
      .catch((error: unknown) => { if (!controller.signal.aborted) console.error('Could not load metric trends', error) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => { controller.abort() }
  }, [url, reloadKey, refreshVersion])
  return { data: result?.url === url ? result.data : undefined, loading, reload: () => setReloadKey((key) => key + 1) }
}

const preferenceGroup = 'ui_preferences'

function parsePreferences(items: { name: string; value: string | null }[]): UiPreferences {
  const values = Object.fromEntries(items.map(({ name, value }) => [name, value]))
  const preferences: UiPreferences = {}
  if (values.language === 'de' || values.language === 'en') preferences.language = values.language
  if (values.theme === 'auto' || values.theme === 'cloud' || values.theme === 'midnight' || values.theme === 'moss') preferences.theme = values.theme
  if (values.last_page && pageKeys.includes(values.last_page as PageKey)) preferences.lastPage = values.last_page as PageKey
  if (values.sidebar_collapsed === 'true' || values.sidebar_collapsed === 'false') preferences.sidebarCollapsed = values.sidebar_collapsed === 'true'
  if (values.system_nav_open === 'true' || values.system_nav_open === 'false') preferences.systemNavOpen = values.system_nav_open === 'true'
  if (values.help_nav_open === 'true' || values.help_nav_open === 'false') preferences.helpNavOpen = values.help_nav_open === 'true'
  if (values.dashboard_chart_mode === 'requests' || values.dashboard_chart_mode === 'bursts' || values.dashboard_chart_mode === 'incidents') preferences.dashboardChartMode = values.dashboard_chart_mode
  if (values.dashboard_overview_mode === 'bursts' || values.dashboard_overview_mode === 'incidents') preferences.dashboardOverviewMode = values.dashboard_overview_mode
  if (values.dashboard_table_mode === 'bursts' || values.dashboard_table_mode === 'incidents') preferences.dashboardTableMode = values.dashboard_table_mode
  if (values.statistics_section === 'overview' || values.statistics_section === 'traffic' || values.statistics_section === 'patterns' || values.statistics_section === 'hostsActors' || values.statistics_section === 'insights' || values.statistics_section === 'incidents' || values.statistics_section === 'honeypot' || values.statistics_section === 'ssh') preferences.statisticsSection = values.statistics_section
  if (values.statistics_country_mode === 'events' || values.statistics_country_mode === 'groups') preferences.statisticsCountryMode = values.statistics_country_mode
  if (values.cowrie_group_panel === 'commands' || values.cowrie_group_panel === 'ssh') preferences.cowrieGroupPanel = values.cowrie_group_panel
  if (values.table_page_sizes) {
    try {
      const parsed = JSON.parse(values.table_page_sizes) as Partial<Record<TableKey, number>>
      const validTables: TableKey[] = ['bursts', 'actors', 'hosts', 'categories', 'requests', 'honeypot']
      const parsedSizes: Partial<Record<TableKey, PageSize>> = {}
      for (const table of validTables) {
        if (allowedPageSizes.includes(parsed?.[table] as PageSize)) parsedSizes[table] = parsed[table] as PageSize
      }
      preferences.tablePageSizes = parsedSizes
    } catch { /* Ignore malformed page-size preferences and use the defaults. */ }
  }
  if (values.time_range) {
    try {
      const parsed = JSON.parse(values.time_range) as UiPreferences['timeRange']
      const validPresets: RangePreset[] = ['last24h', 'today', 'yesterday', 'last6h', 'last7d', 'last30d', 'last90d', 'custom']
      if (parsed && validPresets.includes(parsed.preset)) preferences.timeRange = parsed
    } catch { /* Ignore malformed saved preferences and use defaults. */ }
  }
  if (values.burst_sort) {
    try {
      const parsed = JSON.parse(values.burst_sort) as BurstSort
      const columns: BurstSortColumn[] = ['burst_id', 'start_time', 'actor_ip', 'host', 'country', 'duration', 'requests', 'avg_count']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.burstSort = parsed
    } catch { /* Ignore malformed saved sorting and use the default order. */ }
  }
  if (values.burst_filters) {
    try {
      const parsed = JSON.parse(values.burst_filters) as BurstFilters
      if (parsed && typeof parsed.search === 'string' && typeof parsed.host === 'string' && typeof parsed.country === 'string' && (parsed.known === undefined || ['', 'own', 'foreign'].includes(parsed.known))) preferences.burstFilters = { ...parsed, known: parsed.known ?? '', protectedOnly: parsed.protectedOnly === true }
    } catch { /* Ignore malformed filter preferences and use empty filters. */ }
  }
  if (values.actor_sort) {
    try {
      const parsed = JSON.parse(values.actor_sort) as ActorSort
      const columns: ActorSortColumn[] = ['ip', 'first_time', 'last_time', 'provider', 'asn', 'city', 'country', 'request_count']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.actorSort = parsed
    } catch { /* Ignore malformed actor sorting preferences. */ }
  }
  if (values.actor_filters) {
    try {
      const parsed = JSON.parse(values.actor_filters) as ActorFilters
      if (parsed && typeof parsed.search === 'string' && typeof parsed.country === 'string') preferences.actorFilters = { ...parsed, protectedOnly: parsed.protectedOnly === true }
    } catch { /* Ignore malformed actor filter preferences. */ }
  }
  if (values.host_sort) {
    try {
      const parsed = JSON.parse(values.host_sort) as HostSort
      const columns: HostSortColumn[] = ['host', 'total_count', 'read_count', 'write_count', 'other_count', 'https_count', 'https_share']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.hostSort = parsed
    } catch { /* Ignore malformed host sorting preferences. */ }
  }
  if (values.host_filters) {
    try {
      const parsed = JSON.parse(values.host_filters) as HostFilters
      if (parsed && typeof parsed.search === 'string' && (parsed.known === undefined || ['', 'own', 'foreign'].includes(parsed.known))) preferences.hostFilters = { search: parsed.search, known: parsed.known ?? '' }
    } catch { /* Ignore malformed host filter preferences. */ }
  }
  if (values.category_sort) {
    try {
      const parsed = JSON.parse(values.category_sort) as CategorySort
      const columns: CategorySortColumn[] = ['category_name', 'total_count', 'read_count', 'write_count', 'other_count', 'traffic_share', 'https_share']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.categorySort = parsed
    } catch { /* Ignore malformed category sorting preferences. */ }
  }
  if (values.category_filters) {
    try {
      const parsed = JSON.parse(values.category_filters) as CategoryFilters
      if (parsed && typeof parsed.search === 'string') preferences.categoryFilters = parsed
    } catch { /* Ignore malformed category filter preferences. */ }
  }
  if (values.request_sort) {
    try {
      const parsed = JSON.parse(values.request_sort) as RequestSort
      const columns: RequestSortColumn[] = ['start_utc', 'request_method', 'request_path', 'user_agent', 'downstream_status', 'actor_ip', 'host', 'duration', 'downstream_content_size', 'request_content_size']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.requestSort = parsed
    } catch { /* Ignore malformed request sorting preferences. */ }
  }
  if (values.request_filters) {
    try {
      const parsed = JSON.parse(values.request_filters) as RequestFilters
      if (parsed && typeof parsed.search === 'string' && ['', '2xx', '3xx', '4xx', '5xx'].includes(parsed.status)) preferences.requestFilters = { ...defaultRequestFilters, ...parsed, withoutBurst: parsed.withoutBurst === true }
    } catch { /* Ignore malformed request filter preferences. */ }
  }
  if (values.honeypot_sort) {
    try {
      const parsed = JSON.parse(values.honeypot_sort) as HoneypotSort
      const columns: HoneypotSortColumn[] = ['time', 'client_ip', 'request_count', 'post_count', 'path_count', 'body_bytes']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.honeypotSort = parsed
    } catch { /* Ignore malformed honeypot sorting preferences. */ }
  }
  if (values.honeypot_filters) {
    try {
      const parsed = JSON.parse(values.honeypot_filters) as HoneypotFilters
      if (parsed && typeof parsed.search === 'string' && typeof parsed.postsOnly === 'boolean') preferences.honeypotFilters = { ...parsed, protectedOnly: parsed.protectedOnly === true }
    } catch { /* Ignore malformed honeypot filter preferences. */ }
  }
  if (values.incident_filters) {
    try {
      const parsed = JSON.parse(values.incident_filters) as IncidentFilters
      if (parsed && typeof parsed.search === 'string' && ['', 'open', 'acknowledged', 'resolved'].includes(parsed.state) && (parsed.incidentType === '' || typeof parsed.incidentType === 'string')) preferences.incidentFilters = { ...defaultIncidentFilters, ...parsed, protectedOnly: parsed.protectedOnly === true }
    } catch { /* Ignore malformed incident filter preferences. */ }
  }
  if (values.cowrie_filters) {
    try {
      const parsed = JSON.parse(values.cowrie_filters) as CowrieFilters
      if (parsed && typeof parsed.search === 'string' && typeof parsed.eventType === 'string') preferences.cowrieFilters = { ...defaultCowrieFilters, ...parsed, protectedOnly: parsed.protectedOnly === true, detailSearch: typeof parsed.detailSearch === 'string' ? parsed.detailSearch : '' }
    } catch { /* Ignore malformed Cowrie filter preferences. */ }
  }
  return preferences
}

function numberText(value: number | null | undefined, language: Language) {
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US').format(value ?? 0)
}

function decimalText(value: number | null | undefined, language: Language) {
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(value ?? 0)
}

function shareText(value: number, total: number, language: Language) {
  return `${decimalText(total ? value / total * 100 : 0, language)}%`
}

function dateText(value: string | null | undefined, language: Language) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function timeText(value: string | null | undefined, language: Language) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { hour: '2-digit', minute: '2-digit' }).format(date)
}

function timestampMillisText(value: string | null | undefined, language: Language) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-GB', { minimumIntegerDigits: 3, useGrouping: false }).format(date.getMilliseconds())
}

function elapsedDurationText(totalMilliseconds: number, language: Language) {
  if (!Number.isFinite(totalMilliseconds)) return '—'
  let remaining = Math.max(0, Math.round(totalMilliseconds * 1_000) / 1_000)
  const days = Math.floor(remaining / 86_400_000)
  remaining -= days * 86_400_000
  const hours = Math.floor(remaining / 3_600_000)
  remaining -= hours * 3_600_000
  const minutes = Math.floor(remaining / 60_000)
  remaining -= minutes * 60_000
  const seconds = Math.floor(remaining / 1_000)
  remaining -= seconds * 1_000
  const units = [
    { value: days, label: 'T' },
    { value: hours, label: 'h' },
    { value: minutes, label: 'm' },
    { value: seconds, label: 's' },
  ]
  const firstPresentUnit = units.findIndex(({ value }) => value > 0)
  const parts = units.slice(firstPresentUnit < 0 ? units.length : firstPresentUnit)
    .map(({ value, label }) => `${numberText(value, language)} ${label}`)
  const milliseconds = new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 3 }).format(remaining)
  parts.push(`${milliseconds} ms`)
  return parts.join(' · ')
}

function incidentDurationText(start: string | null | undefined, end: string | null | undefined, language: Language) {
  if (!start || !end) return '—'
  const startMs = new Date(start).getTime()
  const endMs = new Date(end).getTime()
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return '—'
  return elapsedDurationText(endMs - startMs, language)
}

function honeypotPhaseText(phase: string | null | undefined, t: (key: MessageKey) => string) {
  if (!phase) return '—'
  if (phase === 'anonymous') return t('honeypotPhaseAnonymous')
  if (phase === 'authenticated') return t('honeypotPhaseAuthenticated')
  if (phase === 'useradmin-viewed') return t('honeypotPhaseUseradminViewed')
  if (phase === 'useradmin-access-denied') return t('honeypotPhaseUseradminAccessDenied')
  if (phase === 'file-manager-viewed') return t('honeypotPhaseFileManagerViewed')
  if (phase === 'public-upload-form-viewed') return t('honeypotPhasePublicUploadFormViewed')
  if (phase === 'file-upload-received') return t('honeypotPhaseUploadReceived')
  if (phase === 'uploaded-script-requested') return t('honeypotPhaseUploadedScriptRequested')
  if (phase === 'uploaded-file-opened') return t('honeypotPhaseUploadedFileOpened')
  if (phase === 'terminal-opened') return t('honeypotPhaseTerminalOpened')
  if (phase === 'terminal-command') return t('honeypotPhaseTerminalCommand')
  if (phase === 'uploaded-execution-attempt') return t('honeypotPhaseUploadedExecutionAttempt')
  if (phase === 'contact-form-viewed') return t('honeypotPhaseContactFormViewed')
  if (phase === 'contact-message-submitted') return t('honeypotPhaseContactMessageSubmitted')
  if (phase === 'club-members-viewed') return t('honeypotPhaseClubMembers')
  if (phase === 'login-required') return t('honeypotPhaseLoginRequired')
  if (phase === 'signed-out') return t('honeypotPhaseSignedOut')
  if (phase === 'password-reset-requested') return t('honeypotPhasePasswordReset')
  const attempt = phase.match(/^login-attempt-(\d+)$/)
  return attempt ? `${t('honeypotPhaseLoginAttempt')} ${attempt[1]}` : phase
}

type HoneypotMultipartPart = { name: string; headers: string[]; body: string }

function parseHoneypotMultipart(body: string, contentType: string | null | undefined): HoneypotMultipartPart[] {
  const declaredBoundary = contentType?.match(/boundary=(?:"([^"]+)"|([^;\s]+))/i)
  const firstLine = body.split(/\r?\n/, 1)[0]
  const boundary = declaredBoundary?.[1] ?? declaredBoundary?.[2] ?? (firstLine.startsWith('--') ? firstLine.slice(2) : '')
  if (!boundary) return []

  return body.split(`--${boundary}`).slice(1).flatMap((rawPart) => {
    const part = rawPart.replace(/^\r?\n/, '').replace(/\r?\n$/, '')
    if (!part || part === '--') return []
    const separator = part.search(/\r?\n\r?\n/)
    if (separator < 0) return []
    const rawHeaders = part.slice(0, separator)
    const headers = rawHeaders.split(/\r?\n/).filter(Boolean)
    const disposition = rawHeaders.match(/(?:^|\r?\n)Content-Disposition:[^\r\n]*\bname="([^"]*)"/i)
    const partBody = part.slice(separator).replace(/^\r?\n\r?\n/, '')
    return [{ name: disposition?.[1] || '', headers, body: partBody }]
  })
}

function formatHoneypotBody(body: string, hideEmbeddedCode = false, embeddedCodePlaceholder = 'embedded code') {
  const decodeRestPath = (value: string): string => {
    if (!value.startsWith('/') || !/[?&][^=]+=[^&]*%[\da-f]{2}/i.test(value)) return value
    const queryStart = value.indexOf('?')
    if (queryStart < 0) return value
    const hashStart = value.indexOf('#', queryStart)
    const queryEnd = hashStart < 0 ? value.length : hashStart
    try {
      const query = decodeURIComponent(value.slice(queryStart + 1, queryEnd).replace(/\+/g, ' '))
      return `${value.slice(0, queryStart + 1)}${query}${value.slice(queryEnd)}`
    } catch {
      return value
    }
  }
  const decodePaths = (value: unknown): unknown => {
    if (typeof value === 'string') return hideEmbeddedCode && looksLikeCode(value) ? `[${embeddedCodePlaceholder}]` : decodeRestPath(value)
    if (Array.isArray(value)) return value.map(decodePaths)
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, decodePaths(item)]))
    return value
  }
  try {
    return JSON.stringify(decodePaths(JSON.parse(body)), null, 2)
  } catch {
    return body
  }
}

type PayloadView = 'formatted' | 'raw'

function looksLikeCode(value: string) {
  return /(?:\b(?:async\s+)?function\b|\b(?:const|let|var)\s+[\w$]+\s*=|=>|\bprocess\.env\b|\bimport\s*\(|\brequire\s*\()/i.test(value)
}

function formatEmbeddedCode(source: string) {
  let output = ''
  let indent = 0
  let parens = 0
  let quote = ''
  let escaped = false
  let lineComment = false
  let blockComment = false
  let pendingSpace = false
  const write = (value: string) => {
    if (!output || output.endsWith('\n')) output += '  '.repeat(Math.max(0, indent))
    else if (pendingSpace && ![' ', '\n', '\t', '(', '[', '{', '.'].includes(output[output.length - 1] ?? '')) output += ' '
    output += value
    pendingSpace = false
  }
  const newline = () => {
    output = output.replace(/[ \t]+$/, '')
    if (output && !output.endsWith('\n')) output += '\n'
    pendingSpace = false
  }

  for (let index = 0; index < source.length; index += 1) {
    const char = source[index]
    const next = source[index + 1]
    if (quote) {
      output += char
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === quote) quote = ''
      continue
    }
    if (lineComment) {
      write(char)
      if (char === '\n') { lineComment = false; newline() }
      continue
    }
    if (blockComment) {
      output += char
      if (char === '*' && next === '/') { output += '/'; index += 1; blockComment = false }
      continue
    }
    if (char === '/' && next === '/') { pendingSpace = true; write('//'); index += 1; lineComment = true; continue }
    if (char === '/' && next === '*') { pendingSpace = true; write('/*'); index += 1; blockComment = true; continue }
    if (char === '"' || char === "'" || char === '`') { pendingSpace = true; write(char); quote = char; continue }
    if (/\s/.test(char)) { pendingSpace = true; continue }
    if (char === '(' || char === '[') { write(char); parens += 1; continue }
    if (char === ')' || char === ']') { write(char); parens = Math.max(0, parens - 1); continue }
    if (char === '{') { pendingSpace = true; write('{'); indent += 1; newline(); continue }
    if (char === '}') { newline(); indent = Math.max(0, indent - 1); write('}'); if (!/[;,)]/.test(next ?? '')) newline(); continue }
    if (char === ';') { write(';'); if (parens === 0) newline(); else pendingSpace = true; continue }
    if (char === ',') { write(','); pendingSpace = true; continue }
    write(char)
  }
  return output.trim()
}

function extractEmbeddedCode(body: string) {
  const sources: string[] = []
  let visitedValues = 0
  const visit = (value: unknown) => {
    visitedValues += 1
    if (visitedValues > 5000 || sources.length >= 12) return
    if (typeof value === 'string') {
      if (value.length <= 200_000 && looksLikeCode(value)) sources.push(value)
      return
    }
    if (Array.isArray(value)) value.forEach(visit)
    else if (value && typeof value === 'object') Object.values(value).forEach(visit)
  }
  try { visit(JSON.parse(body)) } catch { if (looksLikeCode(body)) sources.push(body) }

  const decoded: { text: string; depth: number }[] = []
  const roots = [...new Set(sources)].map((text) => ({ text, depth: 0 }))
  const nodes = [...roots]
  const parentsWithChildren = new Set<string>()
  const seen = new Set(sources)
  const pending = sources.map((text) => ({ text, depth: 0 }))
  let decodedCharacters = 0
  while (pending.length && decoded.length < 12 && decodedCharacters < 500_000) {
    const { text: source, depth } = pending.shift()!
    if (depth >= 5) continue
    const hexLiteral = /(?:\.from|from)\(\s*(['"])([\da-f]{80,200000})\1\s*,\s*(['"])hex\3\s*\)/gi
    let literals = 0
    for (const match of source.matchAll(hexLiteral)) {
      literals += 1
      if (literals > 4 || decoded.length >= 12 || decodedCharacters >= 500_000) break
      const hex = match[2].slice(0, match[2].length - (match[2].length % 2))
      try {
        const bytes = Uint8Array.from(hex.match(/.{2}/g) ?? [], (pair) => Number.parseInt(pair, 16))
        const decodedText = new TextDecoder().decode(bytes)
        if (looksLikeCode(decodedText)) {
          parentsWithChildren.add(source)
          if (!seen.has(decodedText)) {
            seen.add(decodedText)
            decoded.push({ text: decodedText, depth: depth + 1 })
            const child = { text: decodedText, depth: depth + 1 }
            nodes.push(child)
            pending.push(child)
            decodedCharacters += decodedText.length
          }
        }
      } catch { /* Keep undecodable payloads in the original code block. */ }
    }
  }
  const finalCode = nodes.filter(({ text }) => !parentsWithChildren.has(text))
  return { sources: [...new Set(sources)], decoded, finalCode }
}

function PayloadViewTabs({ view, onChange, t }: { view: PayloadView; onChange: (view: PayloadView) => void; t: (key: MessageKey) => string }) {
  return <div className="payload-view-tabs" role="tablist" aria-label={t('payloadView')}><button type="button" role="tab" aria-selected={view === 'formatted'} className={view === 'formatted' ? 'active' : ''} onClick={() => onChange('formatted')}>{t('formattedView')}</button><button type="button" role="tab" aria-selected={view === 'raw'} className={view === 'raw' ? 'active' : ''} onClick={() => onChange('raw')}>{t('rawView')}</button></div>
}

function formatPayloadText(body: string, t: (key: MessageKey) => string) {
  const embedded = extractEmbeddedCode(body)
  const finalCode = embedded.finalCode.filter(({ text }) => text !== body)
  let formattedBody = formatHoneypotBody(body, finalCode.length > 0, t('embeddedCode'))
  let directCode = false
  let isJson = false
  try { JSON.parse(body); isJson = true } catch { if (looksLikeCode(body)) { formattedBody = ''; directCode = true } }
  const code = directCode ? body : finalCode.map(({ text }) => text).join('\n\n')
  const decoded = embedded.decoded.length > 0
  const codeLabel = directCode ? t('embeddedCode') : decoded ? t('decodedHex') : t('embeddedCode')
  const copyText = `${formattedBody}${code ? `${formattedBody ? '\n\n' : ''}${codeLabel}:\n${formatEmbeddedCode(code)}` : ''}`
  return { formattedBody, code, decoded, directCode, isJson, copyText }
}

function formatMultipartPayloadText(body: string, contentType: string | null | undefined, t: (key: MessageKey) => string) {
  const parts = parseHoneypotMultipart(body, contentType)
  return parts.length ? parts.map((part, index) => `${part.name || `${t('honeypotFields')} ${index + 1}`}\n${part.headers.join('\n')}\n\n${formatPayloadText(part.body, t).copyText}`).join('\n\n────────────────────────────────────────\n\n') : formatPayloadText(body, t).copyText
}

function HighlightedCode({ code }: { code: string }) {
  const tokenPattern = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|false|finally|for|from|function|if|import|in|instanceof|let|new|null|of|return|static|super|switch|this|throw|true|try|typeof|undefined|var|void|while|yield)\b|\b\d+(?:\.\d+)?\b)/g
  const output: ReactNode[] = []
  let cursor = 0
  for (const match of code.matchAll(tokenPattern)) {
    const token = match[0]
    const start = match.index ?? 0
    if (start > cursor) output.push(code.slice(cursor, start))
    let className = 'code-token-keyword'
    if (token.startsWith('//') || token.startsWith('/*')) className = 'code-token-comment'
    else if (/^["'`]/.test(token)) className = 'code-token-string'
    else if (/^\d/.test(token)) className = 'code-token-number'
    output.push(<span className={className} key={`${start}-${token.length}`}>{token}</span>)
    cursor = start + token.length
  }
  if (cursor < code.length) output.push(code.slice(cursor))
  return <>{output}</>
}

function HighlightedJson({ text }: { text: string }) {
  const tokenPattern = /("(?:\\.|[^"\\])*")(?=\s*:)|("(?:\\.|[^"\\])*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b|([{}\[\],:])/g
  const output: ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(tokenPattern)) {
    const token = match[0]
    const start = match.index ?? 0
    if (start > cursor) output.push(text.slice(cursor, start))
    const className = match[1] ? 'json-token-key' : match[2] ? 'json-token-string' : match[3] ? 'json-token-number' : match[4] ? 'json-token-literal' : 'json-token-punctuation'
    output.push(<span className={className} key={`${start}-${token.length}`}>{token}</span>)
    cursor = start + token.length
  }
  if (cursor < text.length) output.push(text.slice(cursor))
  return <>{output}</>
}

function FormattedPayloadContent({ formatted, t }: { formatted: ReturnType<typeof formatPayloadText>; t: (key: MessageKey) => string }) {
  return <><span>{formatted.isJson ? <HighlightedJson text={formatted.formattedBody} /> : formatted.formattedBody}</span>{formatted.code && <><span className="payload-decoded-label">{formatted.formattedBody ? '\n\n' : ''}{formatted.directCode ? t('embeddedCode') : formatted.decoded ? t('decodedHex') : t('embeddedCode')}:{'\n'}</span><span className="payload-decoded-area"><HighlightedCode code={formatEmbeddedCode(formatted.code)} /></span></>}</>
}

function CopyPayloadButton({ text, t }: { text: string; t: (key: MessageKey) => string }) {
  const [copied, setCopied] = useState(false)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timeout = window.setTimeout(() => setCopied(false), 1600)
    return () => window.clearTimeout(timeout)
  }, [copied])
  const copy = async () => {
    setFailed(false)
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
      else {
        const input = document.createElement('textarea')
        input.value = text
        input.style.position = 'fixed'
        input.style.opacity = '0'
        document.body.appendChild(input)
        input.select()
        const succeeded = document.execCommand('copy')
        input.remove()
        if (!succeeded) throw new Error('Clipboard copy failed')
      }
      setCopied(true)
    } catch { setFailed(true) }
  }
  const label = failed ? t('copyPayloadFailed') : copied ? t('payloadCopied') : t('copyPayload')
  return <button type="button" className="payload-copy-button" onClick={() => void copy()} aria-label={label} title={label}>{copied ? <Check size={13} /> : <Copy size={13} />}</button>
}

function PayloadFrame({ children, className = '', height }: { children: ReactNode; className?: string; height?: number }) {
  return <div className="payload-frame"><pre style={height ? { height } : undefined} className={`honeypot-body honeypot-body-modal ${className}`}>{children}</pre></div>
}

function PayloadText({ body, view, t, className = '', rawContent, height }: { body: string; view: PayloadView; t: (key: MessageKey) => string; className?: string; rawContent?: ReactNode; height?: number }) {
  const formatted = view === 'formatted' ? formatPayloadText(body, t) : null
  return <PayloadFrame className={`${className}${view === 'formatted' ? ' payload-format-view' : ''}`} height={height}>{view === 'raw' ? rawContent ?? body : <FormattedPayloadContent formatted={formatted!} t={t} />}</PayloadFrame>
}

function requestDateTimeText(value: string | null | undefined, language: Language) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'medium', timeStyle: 'medium' }).format(date)
}

function secondsText(seconds: number | null | undefined, language: Language) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const totalSeconds = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(totalSeconds / 60)
  const remaining = totalSeconds % 60
  return minutes ? `${minutes}${language === 'de' ? ' Min' : 'm'} ${remaining}${language === 'de' ? ' s' : 's'}` : `${remaining}${language === 'de' ? ' s' : 's'}`
}

function preciseSecondsText(seconds: number, language: Language) {
  if (!Number.isFinite(seconds)) return '—'
  const safeSeconds = Math.max(0, seconds)
  const minutes = Math.floor(safeSeconds / 60)
  const remainingSeconds = safeSeconds - minutes * 60
  const formattedSeconds = new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(remainingSeconds)
  return minutes
    ? `${minutes}${language === 'de' ? ' Min' : 'm'} ${formattedSeconds}${language === 'de' ? ' s' : 's'}`
    : `${formattedSeconds}${language === 'de' ? ' s' : 's'}`
}

function PageDataState({ loading, error, retry, t }: { loading: boolean; error: string | null; retry: () => void; t: (key: MessageKey) => string }) {
  if (loading) return null
  if (error) return <div className="panel data-state error-state"><strong>{t('apiError')}</strong><span>{t('apiUnavailable')}</span><small>{error}</small><button className="select-button" onClick={retry}>{t('retry')}</button></div>
  return null
}

function ApiActivityToast({ t }: { t: (key: MessageKey) => string }) {
  const pending = useSyncExternalStore(subscribeToApiRequests, getPendingApiRequests, getPendingApiRequests)
  if (pending === 0) return null
  return <div className="api-activity-toast" role="status" aria-live="polite"><span className="loading-spinner" /><span>{t('apiCallInProgress')}</span></div>
}

function AppHints({ suppress, notificationOpen, pageKey }: { suppress: boolean; notificationOpen: boolean; pageKey: string }) {
  const [hint, setHint] = useState<{ text: string; left: number; top: number } | null>(null)
  useEffect(() => {
    let active: Element | null = null
    let timer: number | undefined
    const hide = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = undefined
      active = null
      setHint(null)
    }
    // Clear a bell or popup button hint whenever its popover opens/closes.
    hide()
    const show = (target: Element | null) => {
      if (suppress) return
      if (!target || target === active) return
      hide()
      const nativeTitle = target.getAttribute('title')
      if (nativeTitle) {
        target.setAttribute('data-app-hint', nativeTitle)
        target.removeAttribute('title')
      }
      const text = target.getAttribute('data-hint') || target.getAttribute('data-app-hint')
      if (!text?.trim()) return
      active = target
      timer = window.setTimeout(() => {
        const rect = target.getBoundingClientRect()
        const left = Math.max(120, Math.min(window.innerWidth - 120, rect.left + rect.width / 2))
        const top = rect.bottom + 8 < window.innerHeight - 60 ? rect.bottom + 8 : Math.max(8, rect.top - 48)
        setHint({ text, left, top })
      }, 500)
    }
    const findTarget = (event: Event) => {
      const source = event.target
      return source instanceof Element ? source.closest('[data-hint], [data-app-hint], [title]') : null
    }
    const onPointerOver = (event: Event) => suppress ? hide() : show(findTarget(event))
    const onPointerOut = (event: Event) => {
      const target = findTarget(event)
      const next = event instanceof PointerEvent && event.relatedTarget instanceof Element ? event.relatedTarget : null
      if (target && target === active && (!next || !target.contains(next))) hide()
    }
    const onFocusIn = (event: Event) => suppress ? hide() : show(findTarget(event))
    const onFocusOut = (event: Event) => {
      const target = findTarget(event)
      if (target && target === active) hide()
    }
    const onDocumentClick = (event: Event) => {
      const source = event.target
      if (!(source instanceof Element)) return
      if (active && (active === source || active.contains(source))) hide()
      if (source.closest('.notification-button')) hide()
    }
    const observer = new MutationObserver(() => {
      if (active && !active.isConnected) hide()
    })
    observer.observe(document.body, { childList: true, subtree: true })
    document.addEventListener('pointerover', onPointerOver)
    document.addEventListener('pointerout', onPointerOut)
    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', onFocusOut)
    document.addEventListener('click', onDocumentClick)
    return () => {
      hide()
      observer.disconnect()
      document.removeEventListener('pointerover', onPointerOver)
      document.removeEventListener('pointerout', onPointerOut)
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('focusout', onFocusOut)
      document.removeEventListener('click', onDocumentClick)
    }
  }, [suppress, notificationOpen, pageKey])
  return hint ? <div className="app-hint" role="tooltip" style={{ left: hint.left, top: hint.top }}>{hint.text}</div> : null
}

function NotificationPopover({ data, t, language, onClose, onSelect, onMarkRead, marking, closing }: { data: NotificationData | null; t: (key: MessageKey) => string; language: Language; onClose: () => void; onSelect: (item: { type: 'request' | 'burst' | 'incident'; id: number; actorIp: string; firstSeen?: string; lastSeen?: string; incident?: NotificationIncident }) => void; onMarkRead: () => void; marking: boolean; closing: boolean }) {
  return <section className={`notification-popover${closing ? ' notification-closing' : ''}`} aria-label={t('notifications')}>
    <header><strong>{t('notifications')}</strong><div className="notification-header-actions">{data && <button type="button" className="icon-button notification-mark-read" aria-label={t('markNotificationsRead')} title={t('markNotificationsRead')} disabled={marking || data.request_count + data.burst_count + data.incident_count === 0} onClick={onMarkRead}><Check size={15} /></button>}<button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={15} /></button></div></header>
    {!data ? <p className="notification-empty">{t('loadingData')}</p> : <>
      <p className="notification-summary">{numberText(data.incident_count, language)} {t('newIncidents')} · {numberText(data.request_count, language)} {t('newRequests')} · {numberText(data.burst_count, language)} {t('newBursts')}</p>
      <p className="notification-selection-hint">{t('notificationSelectionHint')}</p>
      <p className="notification-since">{t('newRequestsSince')}: {dateText(data.request_since_utc, language)}</p>
      {data.incidents.map((incident) => <button type="button" key={`incident-${incident.incident_id}`} className="notification-row notification-incident" onClick={() => onSelect({ type: 'incident', id: incident.incident_id, actorIp: incident.actor_ip, firstSeen: incident.first_seen, lastSeen: incident.last_seen, incident })}><span><strong>{incidentTypeText(incident, t)} · {incident.actor_ip}</strong><ActorMetadata {...incident} /><small>{incident.summary?.host_count > 1 ? t('multipleHosts') : incident.host || '—'} · {numberText(incident.request_count, language)} {t('requestsLabel')} · {dateText(incident.first_seen, language)}</small><small className="notification-path-preview">{incidentMetricLabels(incident, t, language).join(' · ')}</small></span><ArrowUpRight size={14} /></button>)}
      {data.bursts.map((burst) => <button type="button" key={`burst-${burst.burst_id}`} className="notification-row" onClick={() => onSelect({ type: 'burst', id: burst.burst_id, actorIp: burst.actor_ip })}><span><strong>{t('newBurst')} · {burst.actor_ip}</strong><ActorMetadata {...burst} /><small>{burst.host || '—'} · {numberText(burst.request_count, language)} {t('requestsLabel')}</small></span><ArrowUpRight size={14} /></button>)}
      {data.requests.map((item) => <button type="button" key={`request-${item.request_id}`} className="notification-row" onClick={() => onSelect({ type: 'request', id: item.request_id, actorIp: item.actor_ip })}><span><strong>{item.request_method || 'GET'} {item.request_path || '/'}</strong><small>{item.actor_ip}</small><ActorMetadata {...item} /><small>{item.host || '—'} · {dateText(item.start_utc, language)}</small></span><ArrowUpRight size={14} /></button>)}
      {data.request_count + data.burst_count + data.incident_count === 0 && <p className="notification-empty">{t('noNewNotifications')}</p>}
    </>}
  </section>
}

function EmptyRows({ t, columns }: { t: (key: MessageKey) => string; columns: number }) {
  return <tr><td colSpan={columns} className="empty-cell">{t('noResults')}</td></tr>
}

function activityText(activity: string | undefined, t: (key: MessageKey) => string) {
  if (activity === 'Import') return t('importInProgress')
  if (activity === 'Maintenance') return t('maintenanceInProgress')
  if (activity === 'Idle') return t('idle')
  return activity || '—'
}

function DashboardApp({ onLogout }: { onLogout: () => void }) {
  const [language, setLanguage] = useState<Language>('de')
  const [theme, setTheme] = useState<Theme>('midnight')
  const [systemPrefersDark, setSystemPrefersDark] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const activeTheme: Exclude<Theme, 'auto'> = theme === 'auto' ? (systemPrefersDark ? 'midnight' : 'cloud') : theme
  const [menuOpen, setMenuOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [systemNavOpen, setSystemNavOpen] = useState(true)
  const [honeypotNavOpen, setHoneypotNavOpen] = useState(true)
  const [helpNavOpen, setHelpNavOpen] = useState(true)
  const [dashboardChartMode, setDashboardChartMode] = useState<DashboardChartMode>('requests')
  const [dashboardOverviewMode, setDashboardOverviewMode] = useState<'bursts' | 'incidents'>('bursts')
  const [dashboardTableMode, setDashboardTableMode] = useState<'bursts' | 'incidents'>('bursts')
  const [statisticsSection, setStatisticsSection] = useState<StatisticsSection>('overview')
  const [statisticsCountryMode, setStatisticsCountryMode] = useState<'events' | 'groups'>('events')
  const [cowrieGroupPanel, setCowrieGroupPanel] = useState<CowrieGroupPanel>('commands')
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchClosing, setSearchClosing] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [notificationData, setNotificationData] = useState<NotificationData | null>(null)
  const [notificationSnapshot, setNotificationSnapshot] = useState<NotificationData | null>(null)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [notificationsClosing, setNotificationsClosing] = useState(false)
  const [notificationsMarking, setNotificationsMarking] = useState(false)
  const notificationRefreshVersion = useRef(0)
  const searchCloseTimer = useRef<number | undefined>(undefined)
  const notificationsCloseTimer = useRef<number | undefined>(undefined)
  const notificationWrapRef = useRef<HTMLDivElement>(null)
  const closeNotificationsRef = useRef<() => void>(() => {})
  const [activePage, setActivePage] = useState<PageKey>(() => pageFromUrl() ?? 'dashboard')
  const [range, setRange] = useState<TimeRange>(() => makeRange('last24h'))
  const [burstSort, setBurstSort] = useState<BurstSort>(defaultBurstSort)
  const [burstFilters, setBurstFilters] = useState<BurstFilters>(defaultBurstFilters)
  const [actorSort, setActorSort] = useState<ActorSort>(defaultActorSort)
  const [actorFilters, setActorFilters] = useState<ActorFilters>(defaultActorFilters)
  const [hostSort, setHostSort] = useState<HostSort>(defaultHostSort)
  const [hostFilters, setHostFilters] = useState<HostFilters>(defaultHostFilters)
  const [categorySort, setCategorySort] = useState<CategorySort>(defaultCategorySort)
  const [categoryFilters, setCategoryFilters] = useState<CategoryFilters>(defaultCategoryFilters)
  const [requestSort, setRequestSort] = useState<RequestSort>(defaultRequestSort)
  const [requestFilters, setRequestFilters] = useState<RequestFilters>(defaultRequestFilters)
  const [honeypotSort, setHoneypotSort] = useState<HoneypotSort>(defaultHoneypotSort)
  const [honeypotFilters, setHoneypotFilters] = useState<HoneypotFilters>(defaultHoneypotFilters)
  const [incidentFilters, setIncidentFilters] = useState<IncidentFilters>(defaultIncidentFilters)
  const [cowrieFilters, setCowrieFilters] = useState<CowrieFilters>(defaultCowrieFilters)
  const [tablePageSizes, setTablePageSizes] = useState<Partial<Record<TableKey, PageSize>>>({})
  const [selectedBurstId, setSelectedBurstId] = useState<number | null>(null)
  const [selectedBurstExtreme, setSelectedBurstExtreme] = useState<BurstExtreme | null>(null)
  const [selectedStatisticFilter, setSelectedStatisticFilter] = useState<StatisticRequestFilter | null>(null)
  const [selectedActorIp, setSelectedActorIp] = useState<string | null>(null)
  const [selectedHost, setSelectedHost] = useState<string | null>(null)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const [selectedTrafficBucket, setSelectedTrafficBucket] = useState<TrafficBucket | null>(null)
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null)
  const [selectedIncident, setSelectedIncident] = useState<NotificationIncident | null>(null)
  const [preferencesLoaded, setPreferencesLoaded] = useState(false)
  const [preferencesError, setPreferencesError] = useState(false)
  const preferenceSaves = useRef<Record<string, AbortController>>({})
  const searchInputRef = useRef<HTMLInputElement>(null)
  const topbarRef = useRef<HTMLElement>(null)
  const sidebarToggleRef = useRef<HTMLButtonElement>(null)
  const sidebarTogglePinned = useRef(false)
  const lastObservedImport = useRef<string | null | undefined>(undefined)
  const t = (key: MessageKey) => messages[language][key]
  const refreshNotifications = useCallback(async () => {
    const version = ++notificationRefreshVersion.current
    try {
      const response = await apiFetch(apiUrl('notifications'), { headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json() as NotificationData
      if (version === notificationRefreshVersion.current) {
        setNotificationData(data)
        setNotificationSnapshot(data)
      }
    } catch {
      // Keep the last known notification state during temporary API failures.
    }
  }, [])
  useEffect(() => { void refreshNotifications() }, [refreshNotifications])
  const liveStatus = useApiData<StatusData>(apiUrl('status'), false)
  const collectorImportInterval = Number(liveStatus.data?.environment?.INPUT_INTERVAL_SECONDS || 3600)
  const collectorStatusPollDelay = liveStatus.data?.collector_status.activity === 'Import'
    ? 2_000
    : Math.max(1_000, (Number.isFinite(collectorImportInterval) && collectorImportInterval > 0 ? collectorImportInterval : 3600) * 1000)

  useEffect(() => {
    if (!liveStatus.data) return
    const timer = window.setTimeout(liveStatus.reload, collectorStatusPollDelay)
    return () => window.clearTimeout(timer)
  }, [liveStatus.data, collectorStatusPollDelay])

  useEffect(() => {
    const refreshStatusAfterManualImport = () => liveStatus.reload()
    window.addEventListener('inm2-collector-import', refreshStatusAfterManualImport)
    return () => window.removeEventListener('inm2-collector-import', refreshStatusAfterManualImport)
  }, [liveStatus.reload])

  useLayoutEffect(() => {
    const updatePosition = () => {
      const topbar = topbarRef.current
      const toggle = sidebarToggleRef.current
      if (!topbar || !toggle) return
      if (window.matchMedia('(max-width: 850px)').matches) {
        sidebarTogglePinned.current = false
        toggle.style.removeProperty('position')
        toggle.style.removeProperty('top')
        toggle.style.removeProperty('left')
        toggle.style.removeProperty('transform')
        return
      }
      const top = topbar.getBoundingClientRect().top
      if (sidebarTogglePinned.current ? top >= 4 : top <= 0) sidebarTogglePinned.current = !sidebarTogglePinned.current
      if (sidebarTogglePinned.current) {
        toggle.style.position = 'fixed'
        toggle.style.top = '33px'
        toggle.style.left = `${topbar.getBoundingClientRect().left}px`
        toggle.style.transform = 'translate(-50%, -50%)'
      } else {
        toggle.style.removeProperty('position')
        toggle.style.removeProperty('top')
        toggle.style.removeProperty('left')
        toggle.style.removeProperty('transform')
      }
    }
    updatePosition()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updatePosition)
    if (topbarRef.current) observer?.observe(topbarRef.current)
    window.addEventListener('scroll', updatePosition, { passive: true, capture: true })
    window.addEventListener('resize', updatePosition)
    return () => {
      window.removeEventListener('scroll', updatePosition, true)
      window.removeEventListener('resize', updatePosition)
      observer?.disconnect()
    }
  }, [sidebarCollapsed])

  useEffect(() => {
    const importedAt = liveStatus.data?.collector_status.last_import
    if (importedAt === undefined) return
    const previousImport = lastObservedImport.current
    lastObservedImport.current = importedAt
    if (previousImport === undefined || importedAt === previousImport) return
    void refreshNotifications()
    if (importedAt && range.preset === 'last24h') setRange(makeRange('last24h'))
    triggerLiveRefresh()
  }, [liveStatus.data?.collector_status.last_import, range.preset])

  useEffect(() => {
    const onShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onShortcut)
    return () => window.removeEventListener('keydown', onShortcut)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    apiFetch(apiUrl('params', undefined, { group_name: preferenceGroup }), { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (response.status === 404) return null
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<{ items: { name: string; value: string | null }[] }>
      })
      .then((result) => {
        if (!result || controller.signal.aborted) return
        const saved = parsePreferences(result.items)
        if (saved.tablePageSizes) setTablePageSizes(saved.tablePageSizes)
        if (saved.language) setLanguage(saved.language)
        if (saved.sidebarCollapsed && window.matchMedia('(min-width: 851px)').matches) setSidebarCollapsed(true)
        if (saved.systemNavOpen !== undefined) setSystemNavOpen(saved.systemNavOpen)
        if (saved.helpNavOpen !== undefined) setHelpNavOpen(saved.helpNavOpen)
        if (saved.dashboardChartMode) setDashboardChartMode(saved.dashboardChartMode)
        if (saved.dashboardOverviewMode) setDashboardOverviewMode(saved.dashboardOverviewMode)
        if (saved.dashboardTableMode) setDashboardTableMode(saved.dashboardTableMode)
        if (saved.statisticsSection) setStatisticsSection(saved.statisticsSection)
        if (saved.statisticsCountryMode) setStatisticsCountryMode(saved.statisticsCountryMode)
        if (saved.cowrieGroupPanel) setCowrieGroupPanel(saved.cowrieGroupPanel)
        const initialPage = pageFromUrl() ?? saved.lastPage ?? 'dashboard'
        setActivePage(initialPage)
        writePageToUrl(initialPage, true)
        if (saved.theme) setTheme(saved.theme)
        if (saved.burstSort) setBurstSort(saved.burstSort)
        if (saved.burstFilters) setBurstFilters(saved.burstFilters)
        if (saved.actorSort) setActorSort(saved.actorSort)
        if (saved.actorFilters) setActorFilters(saved.actorFilters)
        if (saved.hostSort) setHostSort(saved.hostSort)
        if (saved.hostFilters) setHostFilters(saved.hostFilters)
        if (saved.categorySort) setCategorySort(saved.categorySort)
        if (saved.categoryFilters) setCategoryFilters(saved.categoryFilters)
        if (saved.requestSort) setRequestSort(saved.requestSort)
        if (saved.requestFilters) setRequestFilters(saved.requestFilters)
        if (saved.honeypotSort) setHoneypotSort(saved.honeypotSort)
        if (saved.honeypotFilters) setHoneypotFilters(saved.honeypotFilters)
        if (saved.incidentFilters) setIncidentFilters(saved.incidentFilters)
        if (saved.cowrieFilters) setCowrieFilters(saved.cowrieFilters)
        if (saved.timeRange) {
          const stored = saved.timeRange
          if (stored.preset === 'custom' && stored.from && stored.to && new Date(stored.from) < new Date(stored.to)) {
            setRange(makeRange('custom', stored.from, stored.to))
          } else if (stored.preset !== 'custom') setRange(makeRange(stored.preset))
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setPreferencesError(true)
      })
      .finally(() => { if (!controller.signal.aborted) { if (!pageFromUrl()) writePageToUrl('dashboard', true); setPreferencesLoaded(true) } })
    return () => controller.abort()
  }, [])

  useEffect(() => () => Object.values(preferenceSaves.current).forEach((controller) => controller.abort()), [])

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const updateSystemTheme = () => setSystemPrefersDark(media.matches)
    updateSystemTheme()
    media.addEventListener('change', updateSystemTheme)
    return () => media.removeEventListener('change', updateSystemTheme)
  }, [])

  useEffect(() => {
    document.documentElement.lang = language
    document.documentElement.dataset.theme = activeTheme
  }, [language, activeTheme])

  const savePreference = (name: string, value: string) => {
    preferenceSaves.current[name]?.abort()
    const controller = new AbortController()
    preferenceSaves.current[name] = controller
    apiFetch(apiUrl('params', undefined, { group_name: preferenceGroup, name, value }), { method: 'PUT', signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`) })
      .then(() => { if (!controller.signal.aborted) setPreferencesError(false) })
      .catch(() => { if (!controller.signal.aborted) setPreferencesError(true) })
      .finally(() => { if (preferenceSaves.current[name] === controller) delete preferenceSaves.current[name] })
  }

  const navigateToPage = (page: PageKey) => {
    if (page !== activePage) writePageToUrl(page)
    if (page !== 'requests') { setSelectedBurstExtreme(null); setSelectedStatisticFilter(null) }
    if (page !== 'requests') setSelectedIncidentId(null)
    setActivePage(page)
    savePreference('last_page', page)
  }
  useEffect(() => {
    if (liveStatus.data && (((activePage === 'honeypot' || activePage === 'honeypotGuide') && !liveStatus.data.honeypot_configured) || ((activePage === 'cowrie' || activePage === 'cowrieGuide') && !liveStatus.data.cowrie_configured))) {
      navigateToPage('dashboard')
    }
  }, [liveStatus.data?.honeypot_configured, liveStatus.data?.cowrie_configured, activePage])
  const toggleSidebar = () => {
    const next = !sidebarCollapsed
    setSidebarCollapsed(next)
    if (window.matchMedia('(min-width: 851px)').matches) savePreference('sidebar_collapsed', String(next))
  }
  const toggleSystemNavigation = () => { const next = !systemNavOpen; setSystemNavOpen(next); savePreference('system_nav_open', String(next)) }
  const toggleHoneypotNavigation = () => setHoneypotNavOpen((open) => !open)
  const toggleHelpNavigation = () => { const next = !helpNavOpen; setHelpNavOpen(next); savePreference('help_nav_open', String(next)) }
  const updateDashboardChartMode = (value: DashboardChartMode) => { setDashboardChartMode(value); savePreference('dashboard_chart_mode', value) }
  const updateDashboardOverviewMode = (value: 'bursts' | 'incidents') => { setDashboardOverviewMode(value); savePreference('dashboard_overview_mode', value) }
  const updateDashboardTableMode = (value: 'bursts' | 'incidents') => { setDashboardTableMode(value); savePreference('dashboard_table_mode', value) }
  const updateStatisticsSection = (value: StatisticsSection) => { setStatisticsSection(value); savePreference('statistics_section', value) }
  const updateStatisticsCountryMode = (value: 'events' | 'groups') => { setStatisticsCountryMode(value); savePreference('statistics_country_mode', value) }
  const updateCowrieGroupPanel = (value: CowrieGroupPanel) => { setCowrieGroupPanel(value); savePreference('cowrie_group_panel', value) }
  useEffect(() => {
    const onPopState = () => {
      const page = pageFromUrl() ?? 'dashboard'
      setActivePage(page)
      savePreference('last_page', page)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])
  useEffect(() => {
    if (!preferencesLoaded) return
    const page = pageFromUrl() ?? activePage
    if (page !== activePage) setActivePage(page)
    if (!pageFromUrl()) writePageToUrl(page, true)
    savePreference('last_page', page)
  }, [preferencesLoaded])

  const updateLanguage = (value: Language) => { setLanguage(value); savePreference('language', value) }
  const updateTheme = (value: Theme) => { setTheme(value); savePreference('theme', value) }
  const updateRange = (value: TimeRange) => {
    setRange(value)
    const stored = value.preset === 'custom'
      ? { preset: value.preset, from: value.from.toISOString(), to: value.to.toISOString() }
      : { preset: value.preset }
    savePreference('time_range', JSON.stringify(stored))
  }
  const updateBurstSort = (value: BurstSort) => {
    setBurstSort(value)
    savePreference('burst_sort', JSON.stringify(value))
  }
  const updateBurstFilters = (value: BurstFilters) => {
    setBurstFilters(value)
    savePreference('burst_filters', JSON.stringify(value))
  }
  const updateActorSort = (value: ActorSort) => { setActorSort(value); savePreference('actor_sort', JSON.stringify(value)) }
  const updateActorFilters = (value: ActorFilters) => { setActorFilters(value); savePreference('actor_filters', JSON.stringify(value)) }
  const updateHostSort = (value: HostSort) => { setHostSort(value); savePreference('host_sort', JSON.stringify(value)) }
  const updateHostFilters = (value: HostFilters) => { setHostFilters(value); savePreference('host_filters', JSON.stringify(value)) }
  const updateCategorySort = (value: CategorySort) => { setCategorySort(value); savePreference('category_sort', JSON.stringify(value)) }
  const updateCategoryFilters = (value: CategoryFilters) => { setCategoryFilters(value); savePreference('category_filters', JSON.stringify(value)) }
  const updateRequestSort = (value: RequestSort) => { setRequestSort(value); savePreference('request_sort', JSON.stringify(value)) }
  const updateRequestFilters = (value: RequestFilters) => { setRequestFilters(value); savePreference('request_filters', JSON.stringify(value)) }
  const updateHoneypotSort = (value: HoneypotSort) => { setHoneypotSort(value); savePreference('honeypot_sort', JSON.stringify(value)) }
  const updateHoneypotFilters = (value: HoneypotFilters) => { setHoneypotFilters(value); savePreference('honeypot_filters', JSON.stringify(value)) }
  const updateIncidentFilters = (value: IncidentFilters) => { setIncidentFilters(value); savePreference('incident_filters', JSON.stringify(value)) }
  const updateCowrieFilters = (value: CowrieFilters) => { setCowrieFilters(value); savePreference('cowrie_filters', JSON.stringify(value)) }
  const clearRequestJumpFilters = () => {
    setSelectedBurstId(null)
    setSelectedIncidentId(null)
    setSelectedIncident(null)
    setSelectedBurstExtreme(null)
    setSelectedStatisticFilter(null)
    setSelectedTrafficBucket(null)
    setSelectedActorIp(null)
    setSelectedHost(null)
    setSelectedCategory(null)
    setSelectedPath(null)
  }
  const selectIncidentRequests = (incident: NotificationIncident) => {
    setSelectedTrafficBucket({ from: incident.first_seen, to: new Date(new Date(incident.last_seen).getTime() + 1000).toISOString() })
    setSelectedIncidentId(incident.incident_id)
    setSelectedIncident(incident)
    setSelectedBurstId(null)
    setSelectedBurstExtreme(null)
    setSelectedStatisticFilter(null)
    setSelectedActorIp(null)
    setSelectedHost(null)
    setSelectedCategory(null)
    setSelectedPath(null)
    setRequestFilters({ ...defaultRequestFilters })
    navigateToPage('requests')
  }
  const selectTrafficBucketRequests = (bucket: TrafficBucket) => {
    setSelectedTrafficBucket(bucket)
    setSelectedIncidentId(null)
    setSelectedIncident(null)
    setSelectedBurstId(null)
    setSelectedBurstExtreme(null)
    setSelectedStatisticFilter(null)
    setSelectedActorIp(null)
    setSelectedHost(null)
    setSelectedCategory(null)
    setSelectedPath(null)
    setRequestFilters({ ...defaultRequestFilters })
    navigateToPage('requests')
  }
  const selectHoneypotGroupRequests = (group: HoneypotGroup) => {
    // The honeypot timestamps its event after sending the response, while
    // Traefik records the request start. Include a small lead-in so the first
    // matching proxy request is not excluded by the inclusive lower bound.
    setSelectedTrafficBucket({
      from: new Date(new Date(group.first_time).getTime() - 1000).toISOString(),
      to: new Date(new Date(group.last_time).getTime() + 1000).toISOString(),
      source: 'honeypot-group',
    })
    setSelectedIncidentId(null)
    setSelectedIncident(null)
    setSelectedBurstId(null)
    setSelectedBurstExtreme(null)
    setSelectedStatisticFilter(null)
    setSelectedActorIp(group.client_ip)
    setSelectedHost(null)
    setSelectedCategory(null)
    setSelectedPath(null)
    setRequestFilters({ ...defaultRequestFilters })
    navigateToPage('requests')
  }
  const selectBurstRequests = (id: number) => {
    setSelectedTrafficBucket(null)
    setSelectedIncidentId(null)
    setSelectedIncident(null)
    setSelectedBurstId(id)
    setSelectedBurstExtreme(null)
    setSelectedStatisticFilter(null)
    setSelectedActorIp(null)
    setSelectedHost(null)
    setSelectedCategory(null)
    setSelectedPath(null)
    setRequestFilters({ ...defaultRequestFilters })
    navigateToPage('requests')
  }
  const updateTablePageSize = (table: TableKey, value: PageSize) => {
    const next = { ...tablePageSizes, [table]: value }
    setTablePageSizes(next)
    savePreference('table_page_sizes', JSON.stringify(next))
  }
  const openSearch = () => {
    if (searchCloseTimer.current !== undefined) window.clearTimeout(searchCloseTimer.current)
    searchCloseTimer.current = undefined
    setSearchClosing(false)
    setSearchOpen(true)
  }
  const closeSearch = () => {
    if (!searchOpen) return
    if (searchCloseTimer.current !== undefined) window.clearTimeout(searchCloseTimer.current)
    setSearchClosing(true)
    searchCloseTimer.current = window.setTimeout(() => {
      setSearchOpen(false)
      setSearchClosing(false)
      searchCloseTimer.current = undefined
    }, 180)
  }
  const closeNotifications = () => {
    if (!notificationsOpen) return
    if (notificationsCloseTimer.current !== undefined) window.clearTimeout(notificationsCloseTimer.current)
    setNotificationsClosing(true)
    notificationsCloseTimer.current = window.setTimeout(() => {
      setNotificationsOpen(false)
      setNotificationsClosing(false)
      notificationsCloseTimer.current = undefined
    }, 160)
  }
  closeNotificationsRef.current = closeNotifications
  useEffect(() => {
    if (!notificationsOpen || notificationsClosing) return
    const handleOutsidePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && notificationWrapRef.current?.contains(event.target)) return
      closeNotificationsRef.current()
    }
    document.addEventListener('pointerdown', handleOutsidePointerDown)
    return () => document.removeEventListener('pointerdown', handleOutsidePointerDown)
  }, [notificationsOpen, notificationsClosing])
  const toggleNotifications = () => {
    if (notificationsOpen && !notificationsClosing) {
      closeNotifications()
      return
    }
    if (notificationsCloseTimer.current !== undefined) window.clearTimeout(notificationsCloseTimer.current)
    notificationsCloseTimer.current = undefined
    setNotificationsClosing(false)
    setNotificationSnapshot(notificationData)
    setNotificationsOpen(true)
    void refreshNotifications()
  }
  const markNotificationsRead = async () => {
    const snapshot = notificationSnapshot ?? notificationData
    if (!snapshot || notificationsMarking || snapshot.request_count + snapshot.burst_count + snapshot.incident_count === 0) return
    notificationRefreshVersion.current += 1
    setNotificationsMarking(true)
    closeNotifications()
    try {
      const cursors = new URLSearchParams({ request_cursor: String(snapshot.request_cursor), burst_cursor: String(snapshot.burst_cursor), incident_cursor: String(snapshot.incident_cursor) })
      const response = await apiFetch(apiUrl('notifications/seen', cursors.toString()), { method: 'PUT' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const refreshed = await apiFetch(apiUrl('notifications'), { headers: { Accept: 'application/json' } })
      if (!refreshed.ok) throw new Error(`HTTP ${refreshed.status}`)
      const data = await refreshed.json() as NotificationData
      setNotificationData(data)
      setNotificationSnapshot(data)
      setPreferencesError(false)
    } catch {
      setPreferencesError(true)
    } finally {
      setNotificationsMarking(false)
    }
  }

  useEffect(() => () => {
    if (searchCloseTimer.current !== undefined) window.clearTimeout(searchCloseTimer.current)
    if (notificationsCloseTimer.current !== undefined) window.clearTimeout(notificationsCloseTimer.current)
  }, [])

  if (!preferencesLoaded) return <div className="preferences-loading">{messages.de.loadingPreferences}</div>

  return (
    <div className="app-shell" data-theme={activeTheme}>
      <aside className={`sidebar${sidebarCollapsed ? ' sidebar-collapsed' : ''}${menuOpen ? ' sidebar-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><Activity size={19} strokeWidth={2.4} /></div>
          <div className="brand-copy"><strong>INM<span>2</span></strong><small>{t('product')}</small></div>
          <button className="icon-button mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="nav-caption">{t('navigation')}</div>
        <nav className="main-nav" aria-label={t('navigation')}>
          {navigation.map(({ key, icon: Icon }) => (
            <a key={key} href="#" title={sidebarCollapsed ? t(key) : undefined} className={`nav-link ${activePage === key ? 'active' : ''}`} aria-current={activePage === key ? 'page' : undefined} onClick={(event) => { event.preventDefault(); if (key === 'requests') clearRequestJumpFilters(); navigateToPage(key); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedPath(null); setMenuOpen(false) }}>
              <Icon size={18} strokeWidth={1.9} /><span>{t(key)}</span>
            </a>
          ))}
        </nav>
        {(liveStatus.data?.honeypot_configured || liveStatus.data?.cowrie_configured) && <div className="admin-navigation honeypot-navigation">
          <button type="button" className="nav-section-toggle honeypot-nav-heading" aria-expanded={honeypotNavOpen} onClick={toggleHoneypotNavigation}><Bug size={17} /><span>{t('honeypotGroup')}</span><ChevronDown size={14} /></button>
          {honeypotNavOpen && <div className="nav-section-links">
            {liveStatus.data?.honeypot_configured && <a href="#" title={sidebarCollapsed ? t('honeypot') : undefined} className={`nav-link ${activePage === 'honeypot' ? 'active' : ''}`} onClick={(event) => { event.preventDefault(); navigateToPage('honeypot'); setMenuOpen(false) }}><Bug size={18} /><span>{t('honeypot')}</span></a>}
            {liveStatus.data?.cowrie_configured && <a href="#" title={sidebarCollapsed ? t('cowrie') : undefined} className={`nav-link ${activePage === 'cowrie' ? 'active' : ''}`} onClick={(event) => { event.preventDefault(); navigateToPage('cowrie'); setMenuOpen(false) }}><Network size={18} /><span>{t('cowrie')}</span></a>}
          </div>}
        </div>}

        <div className="admin-navigation system-navigation">
          <button type="button" className="nav-section-toggle" aria-expanded={systemNavOpen} onClick={toggleSystemNavigation}><Settings size={17} /><span>{t('systemHelp')}</span><ChevronDown size={14} /></button>
          {systemNavOpen && <div className="nav-section-links">
            <a href="#" title={sidebarCollapsed ? t('administration') : undefined} className={`nav-link ${activePage === 'administration' ? 'active' : ''}`} aria-current={activePage === 'administration' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('administration'); setMenuOpen(false) }}><Settings2 size={18} /><span>{t('administration')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('logging') : undefined} className={`nav-link ${activePage === 'logging' ? 'active' : ''}`} aria-current={activePage === 'logging' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('logging'); setMenuOpen(false) }}><FileText size={18} /><span>{t('logging')}</span></a>
          </div>}
        </div>
        <div className="admin-navigation help-navigation">
          <button type="button" className="nav-section-toggle" aria-expanded={helpNavOpen} onClick={toggleHelpNavigation}><CircleHelp size={17} /><span>{t('helpSection')}</span><ChevronDown size={14} /></button>
          {helpNavOpen && <div className="nav-section-links">
            <a href="#" title={sidebarCollapsed ? t('categoryGuide') : undefined} className={`nav-link ${activePage === 'categoryGuide' ? 'active' : ''}`} aria-current={activePage === 'categoryGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('categoryGuide'); setMenuOpen(false) }}><BookOpenText size={18} /><span>{t('categoryGuide')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('burstGuide') : undefined} className={`nav-link ${activePage === 'burstGuide' ? 'active' : ''}`} aria-current={activePage === 'burstGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('burstGuide'); setMenuOpen(false) }}><Activity size={18} /><span>{t('burstGuide')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('countGuide') : undefined} className={`nav-link ${activePage === 'countGuide' ? 'active' : ''}`} aria-current={activePage === 'countGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('countGuide'); setMenuOpen(false) }}><Database size={18} /><span>{t('countGuide')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('hostGuide') : undefined} className={`nav-link ${activePage === 'hostGuide' ? 'active' : ''}`} aria-current={activePage === 'hostGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('hostGuide'); setMenuOpen(false) }}><Globe2 size={18} /><span>{t('hostGuide')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('incidentGuide') : undefined} className={`nav-link ${activePage === 'incidentGuide' ? 'active' : ''}`} aria-current={activePage === 'incidentGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('incidentGuide'); setMenuOpen(false) }}><ShieldAlert size={18} /><span>{t('incidentGuide')}</span></a>
            <a href="#" title={sidebarCollapsed ? t('pathsGuide') : undefined} className={`nav-link ${activePage === 'pathsGuide' ? 'active' : ''}`} aria-current={activePage === 'pathsGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('pathsGuide'); setMenuOpen(false) }}><List size={18} /><span>{t('pathsGuide')}</span></a>
            {liveStatus.data?.honeypot_configured && <a href="#" title={sidebarCollapsed ? t('honeypotGuide') : undefined} className={`nav-link ${activePage === 'honeypotGuide' ? 'active' : ''}`} aria-current={activePage === 'honeypotGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('honeypotGuide'); setMenuOpen(false) }}><Bug size={18} /><span>{t('honeypotGuide')}</span></a>}
            {liveStatus.data?.cowrie_configured && <a href="#" title={sidebarCollapsed ? t('cowrieGuide') : undefined} className={`nav-link ${activePage === 'cowrieGuide' ? 'active' : ''}`} aria-current={activePage === 'cowrieGuide' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); navigateToPage('cowrieGuide'); setMenuOpen(false) }}><Network size={18} /><span>{t('cowrieGuide')}</span></a>}
          </div>}
        </div>
        <div className="sidebar-spacer" />
      </aside>

      {menuOpen && <button className="mobile-scrim" onClick={() => setMenuOpen(false)} aria-label="Close menu" />}

      <main className="main-area">
        <header ref={topbarRef} className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label={t('navigation')}><Menu size={20} /></button>
          <button ref={sidebarToggleRef} type="button" className={`icon-button sidebar-toggle${sidebarCollapsed ? ' collapsed' : ''}`} onClick={toggleSidebar} aria-label={t(sidebarCollapsed ? 'expandNavigation' : 'collapseNavigation')} title={t(sidebarCollapsed ? 'expandNavigation' : 'collapseNavigation')}>
            <ChevronLeft size={15} />
          </button>
          <div className="breadcrumbs"><span>{t('workspace')}</span><span className="crumb-slash">/</span><strong>{t(activePage)}</strong></div>
          <div className="topbar-actions">
            <label className="search-trigger"><Search size={16} /><input ref={searchInputRef} value={searchText} placeholder={t('search')} aria-label={t('search')} onChange={(event) => { const value = event.target.value; setSearchText(value); if (value.trim()) openSearch(); else closeSearch() }} onKeyDown={(event) => { if (event.key === 'Enter' && searchText.trim()) { event.preventDefault(); openSearch() } }} /><kbd><Command size={11} /> K</kbd></label>
            <span className="topbar-divider" />
            <button className="icon-button auth-logout" type="button" onClick={onLogout} aria-label={language === 'de' ? 'Abmelden' : 'Sign out'} title={language === 'de' ? 'Abmelden' : 'Sign out'}><LogOut size={17} /></button>
            <div ref={notificationWrapRef} className="notification-wrap"><button className="icon-button notification-button" aria-label={t('notifications')} data-hint={notificationData ? `${t('notifications')} · ${numberText(notificationData.incident_count, language)} ${t('newIncidents')} · ${t('newRequestsSince')}: ${dateText(notificationData.request_since_utc, language)}` : t('notifications')} aria-expanded={notificationsOpen && !notificationsClosing} onClick={toggleNotifications}><Bell size={18} />{notificationData && notificationData.request_count + notificationData.burst_count + notificationData.incident_count > 0 && <span className="notification-badge">{numberText(notificationData.request_count + notificationData.burst_count + notificationData.incident_count, language)}</span>}</button>{notificationsOpen && <NotificationPopover data={notificationSnapshot ?? notificationData} t={t} language={language} marking={notificationsMarking} closing={notificationsClosing} onMarkRead={markNotificationsRead} onClose={closeNotifications} onSelect={(item) => { const isIncident = item.type === 'incident'; setSelectedTrafficBucket(isIncident && item.firstSeen && item.lastSeen ? { from: item.firstSeen, to: new Date(new Date(item.lastSeen).getTime() + 1000).toISOString() } : null); setSelectedIncidentId(isIncident ? item.id : null); setSelectedIncident(isIncident ? item.incident ?? null : null); setSelectedBurstId(item.type === 'burst' ? item.id : null); setSelectedBurstExtreme(null); setSelectedStatisticFilter(null); setSelectedActorIp(item.type === 'request' ? item.actorIp : null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); setRequestFilters({ ...defaultRequestFilters }); navigateToPage('requests'); closeNotifications() }} />}</div>
          </div>
        </header>

        <div className="content-wrap">
          {activePage === 'bursts' ? <BurstsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.bursts ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('bursts', size)} sort={burstSort} onSortChange={updateBurstSort} filters={burstFilters} onFiltersChange={updateBurstFilters} onBurstSelect={(id) => { setSelectedTrafficBucket(null); setSelectedBurstId(id); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); navigateToPage('requests') }} /> : activePage === 'actors' ? <ActorsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.actors ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('actors', size)} sort={actorSort} onSortChange={updateActorSort} filters={actorFilters} onFiltersChange={updateActorFilters} onActorSelect={(ip) => { setSelectedTrafficBucket(null); setSelectedActorIp(ip); setSelectedBurstId(null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); navigateToPage('requests') }} /> : activePage === 'hosts' ? <HostsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.hosts ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('hosts', size)} sort={hostSort} onSortChange={updateHostSort} filters={hostFilters} onFiltersChange={updateHostFilters} onHostSelect={(host) => { setSelectedTrafficBucket(null); setSelectedHost(host); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedCategory(null); setSelectedPath(null); navigateToPage('requests') }} /> : activePage === 'categories' ? <CategoriesPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.categories ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('categories', size)} sort={categorySort} onSortChange={updateCategorySort} filters={categoryFilters} onFiltersChange={updateCategoryFilters} onCategorySelect={(category) => { setSelectedTrafficBucket(null); setSelectedCategory(category); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedHost(null); setSelectedPath(null); navigateToPage('requests') }} /> : activePage === 'requests' ? <RequestsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.requests ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('requests', size)} burstId={selectedBurstId} incidentId={selectedIncidentId} incidentContext={selectedIncidentId === selectedIncident?.incident_id ? selectedIncident : null} burstExtreme={selectedBurstExtreme} statisticFilter={selectedStatisticFilter} actorIp={selectedActorIp} host={selectedHost} category={selectedCategory} path={selectedPath} trafficBucket={selectedTrafficBucket} onTrafficBucketClear={() => setSelectedTrafficBucket(null)} onIncidentClear={() => { setSelectedIncidentId(null); setSelectedTrafficBucket(null) }} filters={requestFilters} onFiltersChange={updateRequestFilters} sort={requestSort} onSortChange={updateRequestSort} onBurstClear={() => setSelectedBurstId(null)} onBurstExtremeClear={() => setSelectedBurstExtreme(null)} onStatisticFilterClear={() => setSelectedStatisticFilter(null)} onActorClear={() => setSelectedActorIp(null)} onHostClear={() => setSelectedHost(null)} onCategoryClear={() => setSelectedCategory(null)} onPathClear={() => setSelectedPath(null)} /> : activePage === 'statistics' ? <StatisticsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} section={statisticsSection} onSectionChange={updateStatisticsSection} countryMode={statisticsCountryMode} onCountryModeChange={updateStatisticsCountryMode} honeypotConfigured={liveStatus.data?.honeypot_configured === true} cowrieConfigured={liveStatus.data?.cowrie_configured === true} onBucketSelect={selectTrafficBucketRequests} onBurstSelect={selectBurstRequests} onIncidentSelect={selectIncidentRequests} onBurstExtremeSelect={(extreme) => { setSelectedStatisticFilter(null); setSelectedTrafficBucket(null); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); setSelectedBurstExtreme(extreme); setRequestFilters({ ...defaultRequestFilters }); navigateToPage('requests') }} onDistributionSelect={(kind, value) => { setSelectedTrafficBucket(null); setSelectedBurstExtreme(null); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedPath(null); setRequestFilters({ ...defaultRequestFilters }); if (kind === 'actor') { setSelectedStatisticFilter(null); setSelectedActorIp(value); setSelectedHost(null); setSelectedCategory(null) } else if (kind === 'path') { setSelectedStatisticFilter(null); setSelectedPath(value); setSelectedHost(null); setSelectedCategory(null) } else if (kind === 'host') { setSelectedStatisticFilter(null); setSelectedHost(value); setSelectedCategory(null) } else if (kind === 'category') { setSelectedStatisticFilter(null); setSelectedCategory(value); setSelectedHost(null) } else { setSelectedStatisticFilter({ field: kind, value }); setSelectedHost(null); setSelectedCategory(null) } navigateToPage('requests') }} /> : activePage === 'administration' ? <AdministrationPage t={t} language={language} /> : activePage === 'categoryGuide' ? <CategoryGuidePage t={t} /> : activePage === 'burstGuide' ? <BurstGuidePage t={t} /> : activePage === 'countGuide' ? <CountGuidePage t={t} /> : activePage === 'hostGuide' ? <HostGuidePage t={t} /> : activePage === 'pathsGuide' ? <PathsGuidePage t={t} /> : activePage === 'incidentGuide' ? <IncidentGuidePage t={t} /> : activePage === 'honeypotGuide' && liveStatus.data?.honeypot_configured ? <HoneypotGuidePage t={t} /> : activePage === 'cowrieGuide' && liveStatus.data?.cowrie_configured ? <CowrieGuidePage t={t} /> : activePage === 'honeypot' ? <HoneypotPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} pageSize={tablePageSizes.honeypot ?? defaultTablePageSize} onPageSizeChange={(size) => updateTablePageSize('honeypot', size)} sort={honeypotSort} onSortChange={updateHoneypotSort} filters={honeypotFilters} onFiltersChange={updateHoneypotFilters} onGroupRequestsSelect={selectHoneypotGroupRequests} /> : activePage === 'cowrie' && liveStatus.data?.cowrie_configured ? <CowriePage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} openGroupPanel={cowrieGroupPanel} onGroupPanelChange={updateCowrieGroupPanel} filters={cowrieFilters} onFiltersChange={updateCowrieFilters} /> : activePage === 'logging' ? <LoggingPage t={t} /> : activePage === 'incidents' ? <IncidentsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} onIncidentSelect={selectIncidentRequests} filters={incidentFilters} onFiltersChange={updateIncidentFilters} /> : <DashboardPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} chartMode={dashboardChartMode} onChartModeChange={updateDashboardChartMode} overviewMode={dashboardOverviewMode} onOverviewModeChange={updateDashboardOverviewMode} tableMode={dashboardTableMode} onTableModeChange={updateDashboardTableMode} onBurstSelect={(id) => { setSelectedTrafficBucket(null); setSelectedBurstId(id); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); navigateToPage('requests') }} onBucketSelect={(bucket) => { setSelectedTrafficBucket(bucket); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setSelectedPath(null); navigateToPage('requests') }} onIncidentSelect={selectIncidentRequests} />}

          <footer className="page-footer"><span>INM2 <b>·</b> Internet Noise Monitor</span><div className="footer-controls">{preferencesError && <span className="preferences-error">{t('preferencesError')}</span>}<label><span>{t('theme')}</span><select value={theme} onChange={(event) => updateTheme(event.target.value as Theme)} aria-label={t('theme')}><option value="auto">{t('themeAuto')}</option><option value="cloud">{t('themeCloud')}</option><option value="midnight">{t('themeMidnight')}</option><option value="moss">{t('themeMoss')}</option></select><Sun size={14} /></label><label><span>{t('language')}</span><select value={language} onChange={(event) => updateLanguage(event.target.value as Language)} aria-label={t('language')}><option value="de">DE</option><option value="en">EN</option></select></label><span className="version-label">v{__APP_VERSION__}</span></div></footer>
        </div>
      </main>
      <ApiActivityToast t={t} />
      <AppHints suppress={notificationsClosing} notificationOpen={notificationsOpen} pageKey={activePage} />
      {searchOpen && <GlobalSearchDialog query={searchText} queryRange={range.query} language={language} t={t} closing={searchClosing} onClose={closeSearch} onSelect={(kind, value) => { setSelectedTrafficBucket(null); setSelectedIncidentId(null); setSelectedBurstId(null); setSelectedActorIp(kind === 'actor' ? value : null); setSelectedHost(kind === 'host' ? value : null); setSelectedCategory(kind === 'category' ? value : null); setSelectedPath(kind === 'path' ? value : null); navigateToPage('requests'); closeSearch(); setSearchText('') }} />}
    </div>
  )
}

function GlobalSearchDialog({ query, queryRange, language, t, onClose, onSelect, closing }: { query: string; queryRange: string; language: Language; t: (key: MessageKey) => string; onClose: () => void; onSelect: (kind: 'actor' | 'host' | 'category' | 'path', value: string) => void; closing: boolean }) {
  const [results, setResults] = useState<GlobalSearchResults>({ actors: [], hosts: [], categories: [], paths: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])
  useEffect(() => {
    const term = query.trim()
    const parsed = parseSearchField(term)
    if (!term || (parsed.field && !parsed.term)) { setResults({ actors: [], hosts: [], categories: [], paths: [] }); setLoading(false); setError(false); return }
    setResults({ actors: [], hosts: [], categories: [], paths: [] })
    setLoading(true)
    setError(false)
    const controller = new AbortController()
    let finished = false
    let timer: number | undefined
    const finish = () => { if (!finished) { finished = true; updatePendingApiRequests(-1) } }
    timer = window.setTimeout(() => {
      setLoading(true)
      setError(false)
      updatePendingApiRequests(1)
      const actorFields: SearchField[] = ['ip', 'country', 'city', 'provider', 'asn']
      const requests: { kind: 'actors' | 'hosts' | 'categories' | 'paths'; promise: Promise<Response> }[] = []
      const options = { signal: controller.signal, headers: { Accept: 'application/json' } }
      if (!parsed.field || actorFields.includes(parsed.field)) {
        requests.push({ kind: 'actors', promise: apiFetch(apiUrl('actors', queryRange, { global_search: parsed.field ? `${parsed.field}:${parsed.term}` : term, sort_by: 'request_count', sort_order: 'desc', limit: '100', offset: '0' }), options) })
      }
      if (!parsed.field || parsed.field === 'host') {
        requests.push({ kind: 'hosts', promise: apiFetch(apiUrl('hosts', queryRange, { host: parsed.field ? parsed.term : term, sort_by: 'total_count', sort_order: 'desc' }), options) })
      }
      if (!parsed.field || parsed.field === 'category') {
        requests.push({ kind: 'categories', promise: apiFetch(apiUrl('categories', queryRange, { category: parsed.field ? parsed.term : term, sort_by: 'total_count', sort_order: 'desc' }), options) })
      }
      if (!parsed.field || parsed.field === 'path') {
        requests.push({ kind: 'paths', promise: apiFetch(apiUrl('request_paths', queryRange, { search: parsed.field ? parsed.term : term, limit: '100' }), options) })
      }
      Promise.all(requests.map(async ({ kind, promise }) => {
        const response = await promise
        if (!response.ok) throw new Error('Search request failed')
        const value = await response.json() as { items: GlobalSearchActor[] | GlobalSearchHost[] | GlobalSearchCategory[] | GlobalSearchPath[] }
        return [kind, value.items] as const
      })).then((data) => {
        const byKind = Object.fromEntries(data)
        if (!controller.signal.aborted) setResults({
          actors: (byKind.actors ?? []) as GlobalSearchActor[],
          hosts: (byKind.hosts ?? []) as GlobalSearchHost[],
          categories: (byKind.categories ?? []) as GlobalSearchCategory[],
          paths: (byKind.paths ?? []) as GlobalSearchPath[],
        })
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted && !(reason instanceof DOMException && reason.name === 'AbortError')) setError(true)
      }).finally(() => {
        finish()
        if (!controller.signal.aborted) setLoading(false)
      })
    }, 250)
    return () => { if (timer !== undefined) window.clearTimeout(timer); finish(); controller.abort() }
  }, [query, queryRange])

  const resultCount = results.actors.length + results.hosts.length + results.categories.length + results.paths.length
  return <div className={`global-search-backdrop${closing ? ' search-closing' : ''}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="global-search-dialog" role="dialog" aria-modal="true" aria-label={t('searchPopupTitle')}>
      <header className="global-search-header"><div><h2>{t('searchPopupTitle')}</h2><p>{t('searchPopupHint')}</p></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></header>
      <div className="global-search-results" aria-live="polite">
        {loading && <div className="global-search-message"><span className="loading-spinner" />{t('searchPopupLoading')}</div>}
        {error && <div className="global-search-message">{t('searchPopupError')}</div>}
        {!query.trim() && !loading && <div className="global-search-message">{t('searchPopupHint')}</div>}
        {query.trim() && !loading && !error && resultCount === 0 && <div className="global-search-message">{t('searchPopupEmpty')}</div>}
        {results.actors.length > 0 && <SearchResultGroup title={t('searchActors')} icon={Users}>{results.actors.map((actor) => <SearchResultRow key={`actor-${actor.actor_id}`} primary={actor.ip} secondary={[actor.provider, actor.asn, actor.country, actor.city].map((value) => value || '—').join(' · ')} language={language} country={actor.country} onClick={() => onSelect('actor', actor.ip)} />)}</SearchResultGroup>}
        {results.hosts.length > 0 && <SearchResultGroup title={t('searchHosts')} icon={Globe2}>{results.hosts.map((host) => <SearchResultRow key={`host-${host.host_id}`} primary={host.host} secondary={`${numberText(host.total_count, language)} ${t('requestsLabel')}`} language={language} onClick={() => onSelect('host', host.host)} />)}</SearchResultGroup>}
        {results.categories.length > 0 && <SearchResultGroup title={t('searchCategories')} icon={Blocks}>{results.categories.map((category) => <SearchResultRow key={`category-${category.category_id}`} primary={category.category_name} secondary={`${numberText(category.total_count, language)} ${t('requestsLabel')}`} language={language} onClick={() => onSelect('category', category.category_name)} />)}</SearchResultGroup>}
        {results.paths.length > 0 && <SearchResultGroup title={t('searchPaths')} icon={List}>{results.paths.map((path) => <SearchResultRow key={`path-${path.path}`} primary={path.path} secondary={`${numberText(path.request_count, language)} ${t('requestsLabel')}`} language={language} path onClick={() => onSelect('path', path.path)} />)}</SearchResultGroup>}
      </div>
    </section>
  </div>
}

function SearchResultGroup({ title, icon: Icon, children }: { title: string; icon: typeof Users; children: ReactNode }) {
  return <section className="search-result-group"><h3><Icon size={15} />{title}</h3><div>{children}</div></section>
}

function SearchResultRow({ primary, secondary, detail, country, language, path = false, onClick }: { primary: string; secondary: string; detail?: string; country?: string | null; language: Language; path?: boolean; onClick: () => void }) {
  return <button type="button" className={`search-result-row${path ? ' search-result-path' : ''}`} onClick={onClick}><span className="search-result-copy"><strong>{primary}</strong><small>{country && <span className="country-flag" title={country}>{countryFlag(country)}</span>}{secondary || (language === 'de' ? 'Ohne weitere Angaben' : 'No additional details')}{detail ? ` · ${detail}` : ''}</small></span><ArrowUpRight size={15} /></button>
}

type RangePageProps = { t: (key: MessageKey) => string; language: Language; range: TimeRange; onRangeChange: (range: TimeRange) => void; lastImport: string | null | undefined }
type PaginatedPageProps = RangePageProps & { pageSize: PageSize; onPageSizeChange: (size: PageSize) => void }

type IncidentSortColumn = 'incident_id' | 'incident_type' | 'last_seen' | 'actor_ip' | 'host' | 'indicator_count' | 'request_count' | 'state'
type IncidentSort = { column: IncidentSortColumn; direction: 'asc' | 'desc' }
const defaultIncidentSort: IncidentSort = { column: 'last_seen', direction: 'desc' }
const incidentTypeLabels: Record<IncidentType, MessageKey> = {
  path_scan: 'incidentTypePathScan', failed_login: 'incidentTypeFailedLogin', sensitive_file_access: 'incidentTypeSensitiveFile',
  exploit_response: 'incidentTypeExploitResponse', write_activity: 'incidentTypeWriteActivity',
  http_error_spike: 'incidentTypeErrorSpike', scanner_activity: 'incidentTypeScanner',
  activity_spike: 'incidentTypeActivitySpike', dormant_host_activity: 'incidentTypeDormantHost',
  low_slow_path_scan: 'incidentTypeLowSlowPathScan',
  unknown_host_404_activity: 'incidentTypeUnknownHost404',
}

function incidentTypeText(incident: NotificationIncident, t: (key: MessageKey) => string) {
  const types = incident.incident_types?.length ? incident.incident_types : [incident.incident_type]
  return types.map((type) => t(incidentTypeLabels[type])).join(' · ')
}

function incidentMetricLabels(incident: NotificationIncident, t: (key: MessageKey) => string, language: Language) {
  const value = (key: string) => numberText(incident.summary?.[key], language)
  const types = incident.incident_types?.length ? incident.incident_types : [incident.incident_type]
  const errorCount = incident.summary?.error_count ?? 0
  const nonErrorCount = incident.summary?.non_error_count ?? 0
  const nonErrorShare = errorCount + nonErrorCount ? nonErrorCount * 100 / (errorCount + nonErrorCount) : 0
  const metrics: string[] = []
  if (types.includes('http_error_spike')) metrics.push(
    `${t('incidentErrorCount')}: ${value('error_count')}`,
    `${t('incidentNonErrorShare')}: ${decimalText(nonErrorShare, language)}%`,
  )
  if (types.includes('activity_spike')) metrics.push(
    `${t('incidentAverageRps')}: ${value('average_rps')}`,
    `${t('incidentMaxRps')}: ${value('max_rps')}`,
    `${t('incidentMinRps')}: ${value('min_rps')}`,
  )
  if (metrics.length) return metrics
  return incident.indicators.slice(0, 4)
}

function IncidentsPage({ t, language, range, onRangeChange, lastImport, onIncidentSelect, filters, onFiltersChange }: RangePageProps & { onIncidentSelect: (incident: Incident) => void; filters: IncidentFilters; onFiltersChange: (filters: IncidentFilters) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState<PageSize>(defaultTablePageSize)
  const [draftFilters, setDraftFilters] = useState<IncidentFilters>(filters)
  const [sort, setSort] = useState<IncidentSort>(defaultIncidentSort)
  const [updatingIncident, setUpdatingIncident] = useState<number | null>(null)
  const [deletingIncident, setDeletingIncident] = useState<number | null>(null)
  const [updateError, setUpdateError] = useState<string | null>(null)
  const result = useApiData<ApiResult<Incident>>(apiUrl('incidents', range.query, {
    limit: String(pageSize), offset: String(pageIndex * pageSize),
    ...(filters.search.trim() ? { search: filters.search.trim() } : {}),
    ...(filters.state ? { state: filters.state } : {}),
    ...(filters.incidentType ? { incident_type: filters.incidentType } : {}),
    ...(filters.protectedOnly ? { protected_only: 'true' } : {}),
    sort_by: sort.column,
    sort_order: sort.direction,
  }))
  const items = result.data?.items ?? []
  useEffect(() => setPageIndex(0), [range.query, filters, sort])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange({ ...draftFilters }) }
  const resetFilters = () => { setPageIndex(0); setDraftFilters(defaultIncidentFilters); onFiltersChange(defaultIncidentFilters) }
  const changeSort = (column: IncidentSortColumn) => setSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' }))
  const deleteIncident = async (incidentId: number) => {
    setDeletingIncident(incidentId)
    setUpdateError(null)
    try {
      const response = await apiFetch(apiUrl(`incidents/${incidentId}`), { method: 'DELETE', headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      result.reload()
    } catch (error) {
      setUpdateError(`${t('deleteFailed')}: ${error instanceof Error ? error.message : String(error)}`)
    } finally { setDeletingIncident(null) }
  }
  const updateIncidentState = async (incidentId: number, state: Incident['state']) => {
    setUpdatingIncident(incidentId)
    setUpdateError(null)
    try {
      const response = await apiFetch(apiUrl(`incidents/${incidentId}/state`), {
        method: 'PUT', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ state }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      result.reload()
    } catch (error) {
      setUpdateError(`${t('incidentStateUpdateFailed')}: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      setUpdatingIncident(null)
    }
  }
  return <>
    <PageHeading title={t('incidents')} subtitle={t('incidentsSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <div className="filter-toolbar incident-filters">
      <label className="filter-search incident-free-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('searchIncidents')} aria-label={t('searchIncidents')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label>
      <label className="filter-select"><select aria-label={t('incidentType')} value={draftFilters.incidentType} onChange={(event) => setDraftFilters((value) => ({ ...value, incidentType: event.target.value as IncidentFilters['incidentType'] }))}><option value="">{t('allIncidentTypes')}</option>{(Object.keys(incidentTypeLabels) as IncidentType[]).map((incidentType) => <option key={incidentType} value={incidentType}>{t(incidentTypeLabels[incidentType])}</option>)}</select><span className="filter-select-value">{draftFilters.incidentType ? t(incidentTypeLabels[draftFilters.incidentType]) : t('allIncidentTypes')}</span><ChevronDown size={13} /></label>
      <label className="filter-select"><select aria-label={t('incidentState')} value={draftFilters.state} onChange={(event) => setDraftFilters((value) => ({ ...value, state: event.target.value as IncidentFilters['state'] }))}><option value="">{t('allIncidentStates')}</option><option value="open">{t('incidentOpen')}</option><option value="acknowledged">{t('incidentAcknowledged')}</option><option value="resolved">{t('incidentResolved')}</option></select><span className="filter-select-value">{draftFilters.state ? t(draftFilters.state === 'open' ? 'incidentOpen' : draftFilters.state === 'acknowledged' ? 'incidentAcknowledged' : 'incidentResolved') : t('allIncidentStates')}</span><ChevronDown size={13} /></label>
      <label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.protectedOnly} onChange={(event) => setDraftFilters((value) => ({ ...value, protectedOnly: event.target.checked }))} /><span>{t('protectedIpsOnly')}</span></label>
      <button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button>
    </div>
    {!result.loading && !result.error && result.data && <div className="metric-grid incident-metrics">
      <MetricCard t={t} language={language} label={t('incidents')} value={numberText(result.data.summary?.incident_count ?? result.data.total ?? 0, language)} icon={ShieldAlert} iconClass="amber" />
      <MetricCard t={t} language={language} label={t('incidentOpen')} value={numberText(result.data.summary?.open_count ?? 0, language)} icon={Check} iconClass="green" caption={`${t('incidentAcknowledged')}: ${numberText(result.data.summary?.acknowledged_count ?? 0, language)} · ${t('incidentResolved')}: ${numberText(result.data.summary?.resolved_count ?? 0, language)}`} />
      <MetricCard t={t} language={language} label={t('affectedActors')} value={numberText(result.data.summary?.actor_count ?? 0, language)} icon={Users} iconClass="blue" />
      <MetricCard t={t} language={language} label={t('incidentUniqueRequests')} value={numberText(result.data.summary?.request_count ?? 0, language)} icon={Activity} iconClass="violet" caption={t('incidentUniqueRequestsNote')} />
    </div>}
    {updateError && <div className="incident-update-error" role="alert">{updateError}</div>}
    <PageDataState loading={result.loading} error={result.error} retry={result.reload} t={t} />
    {!result.loading && !result.error && <div className="panel data-list-panel incident-list-panel">
      <div className="burst-list-heading"><div><h2>{t('incidents')}</h2></div></div>
      <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={setPageSize} t={t} language={language} />
      <TableScroller t={t}><table className="incident-table"><thead><tr><SortableHeader column="incident_id" label={t('incidentId')} sort={sort} onSort={changeSort} /><SortableHeader column="actor_ip" label={t('actor')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="incident_type" label={t('incidentType')} sort={sort} onSort={changeSort} filtered={Boolean(filters.incidentType)} filterLabel={t('filteredColumn')} /><SortableHeader column="last_seen" label={t('incidentStart')} sort={sort} onSort={changeSort} filtered filterLabel={t('filteredColumn')} /><SortableHeader column="host" label={t('host')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="indicator_count" label={t('incidentIndicators')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="request_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="state" label={t('incidentState')} sort={sort} onSort={changeSort} filtered={Boolean(filters.state)} filterLabel={t('filteredColumn')} /><th /></tr></thead><tbody>{items.length ? items.map((incident) => <tr key={incident.incident_id}><td><button type="button" className="table-link incident-id-link" title={t('viewIncidentRequests')} onClick={() => onIncidentSelect(incident)}>#{incident.incident_id}</button></td><td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={incident.actor_ip} t={t} /><strong className="primary-cell">{incident.actor_ip}</strong></span><ActorMetadata {...incident} /></span></td><td className="incident-type-cell">{incidentTypeText(incident, t)}</td><td><span className="incident-time-cell"><strong>{requestDateTimeText(incident.first_seen, language)}</strong><small>{incidentDurationText(incident.first_seen, incident.last_seen, language)}</small></span></td><td className="host-cell">{incident.summary?.host_count > 1 ? t('multipleHosts') : incident.host || '—'}</td><td><span className="incident-indicators">{incidentMetricLabels(incident, t, language).map((indicator) => <code key={indicator}>{indicator}</code>)}</span></td><td><span className="request-count">{numberText(incident.request_count, language)}</span></td><td><label className="incident-state-control"><span className={`incident-state incident-state-${incident.state}`}>{t(incident.state === 'open' ? 'incidentOpen' : incident.state === 'acknowledged' ? 'incidentAcknowledged' : 'incidentResolved')}</span><select aria-label={`${t('incidentState')} · ${incident.actor_ip}`} value={incident.state} disabled={updatingIncident === incident.incident_id} onChange={(event) => updateIncidentState(incident.incident_id, event.target.value as Incident['state'])}><option value="open">{t('incidentOpen')}</option><option value="acknowledged">{t('incidentAcknowledged')}</option><option value="resolved">{t('incidentResolved')}</option></select><ChevronDown size={12} /></label></td><td><span className="actor-row-actions"><button type="button" className="icon-button row-more" aria-label={t('viewIncidentRequests')} title={t('viewIncidentRequests')} onClick={() => onIncidentSelect(incident)}><ArrowUpRight size={15} /></button><button type="button" className="icon-button row-more actor-delete-button" aria-label={t('deleteIncident')} title={t('deleteIncident')} disabled={deletingIncident === incident.incident_id} onClick={() => void deleteIncident(incident.incident_id)}><Trash2 size={15} /></button></span></td></tr>) : <EmptyRows t={t} columns={9} />}</tbody></table></TableScroller>
      <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={setPageSize} t={t} language={language} />
    </div>}
  </>
}

function DashboardPage({ t, language, range, onRangeChange, lastImport, onBurstSelect, onBucketSelect, onIncidentSelect, chartMode, onChartModeChange, overviewMode, onOverviewModeChange, tableMode, onTableModeChange }: RangePageProps & { onBurstSelect: (id: number) => void; onBucketSelect: (bucket: TrafficBucket) => void; onIncidentSelect: (incident: NotificationIncident) => void; chartMode: DashboardChartMode; onChartModeChange: (mode: DashboardChartMode) => void; overviewMode: 'bursts' | 'incidents'; onOverviewModeChange: (mode: 'bursts' | 'incidents') => void; tableMode: 'bursts' | 'incidents'; onTableModeChange: (mode: 'bursts' | 'incidents') => void }) {
  const trends = useMetricTrends(range, 'dashboard')
  const [burstHintDelayActive, setBurstHintDelayActive] = useState(true)
  const [openBurstHintKey, setOpenBurstHintKey] = useState<string | null>(null)
  const burstHintOpenTimer = useRef<number | null>(null)
  const burstHintIdleTimer = useRef<number | null>(null)
  const activeBurstHint = useRef<{ key: string; slot: HTMLDivElement } | null>(null)
  const lastBurstHintPointer = useRef<{ x: number; y: number } | null>(null)
  useEffect(() => () => {
    if (burstHintOpenTimer.current !== null) window.clearTimeout(burstHintOpenTimer.current)
    if (burstHintIdleTimer.current !== null) window.clearTimeout(burstHintIdleTimer.current)
  }, [])
  useEffect(() => {
    if (!openBurstHintKey) return
    const handlePointerMove = (event: PointerEvent) => {
      const active = activeBurstHint.current
      if (!active || active.key !== openBurstHintKey) return
      const tooltip = active.slot.querySelector<HTMLElement>('.chart-burst-tooltip')
      const bar = active.slot.querySelector<HTMLElement>('.burst-bar-stack')
      if (!tooltip || !bar) return
      const x = event.clientX
      const y = event.clientY
      const previousPointer = lastBurstHintPointer.current
      const movingDown = previousPointer !== null && y > previousPointer.y
      const movingUp = previousPointer !== null && y < previousPointer.y
      const movingLeft = previousPointer !== null && x < previousPointer.x
      const movingRight = previousPointer !== null && x > previousPointer.x
      lastBurstHintPointer.current = { x, y }
      const distanceToRect = (rect: DOMRect) => {
        const dx = Math.max(rect.left - x, 0, x - rect.right)
        const dy = Math.max(rect.top - y, 0, y - rect.bottom)
        return Math.hypot(dx, dy)
      }
      const inRect = (rect: DOMRect) => x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
      const barRect = bar.getBoundingClientRect()
      const tooltipRect = tooltip.getBoundingClientRect()
      if (inRect(barRect) || inRect(tooltipRect)) return
      const targetSlot = event.target instanceof Element ? event.target.closest('.burst-bar-slot') : null
      if (targetSlot && targetSlot !== active.slot) return
      const movingDownPastBar = movingDown && y >= barRect.top && distanceToRect(tooltipRect) > distanceToRect(barRect)
      const movingAwayAboveHint = movingUp && y < tooltipRect.top
      const movingAwayHorizontally = (movingLeft && x < tooltipRect.left) || (movingRight && x > tooltipRect.right)
      if (movingDownPastBar || movingAwayAboveHint || movingAwayHorizontally) {
        setOpenBurstHintKey(null)
        activeBurstHint.current = null
        lastBurstHintPointer.current = null
        if (burstHintIdleTimer.current !== null) window.clearTimeout(burstHintIdleTimer.current)
        burstHintIdleTimer.current = window.setTimeout(() => {
          burstHintIdleTimer.current = null
          setBurstHintDelayActive(true)
        }, 2000)
      }
    }
    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    return () => window.removeEventListener('pointermove', handlePointerMove)
  }, [openBurstHintKey])
  const [burstSort, setBurstSort] = useState<BurstSort>({ column: 'requests', direction: 'desc' })
  const counts = useApiData<ApiResult<CountItem>>(apiUrl('request_counts', range.query, trafficBucketOptions(range)))
  const burstChart = useApiData<BurstChartResponse>(chartMode === 'bursts' ? apiUrl('burst_counts', range.query, trafficBucketOptions(range)) : null)
  const incidentChart = useApiData<IncidentStatistics>(chartMode === 'incidents' ? apiUrl('incident_statistics', range.query, { include_incidents: 'true' }) : null)
  const bursts = useApiData<BurstResponse>(apiUrl('bursts', range.query, { limit: '6', offset: '0', sort_by: burstSort.column, sort_order: burstSort.direction }))
  const dashboardIncidents = useApiData<PagedResponse<Incident> & { summary?: { incident_count: number; actor_count: number; request_count: number; open_count: number; acknowledged_count: number; resolved_count: number } }>(apiUrl('incidents', range.query, { limit: '6', offset: '0', sort_by: 'last_seen', sort_order: 'desc' }))
  const actors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0' }))
  const newActors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0', new_only: 'true' }))
  const hosts = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query))
  const status = useApiData<StatusData>(apiUrl('status'), false)
  const requestRows = counts.data?.items ?? []
  const burstChartRows = burstChart.data?.items ?? []
  const incidentChartRows = incidentChart.data?.timeline ?? []
  const chartRange = chartMode !== 'incidents' && requestRows.length && requestRows[0].from
    ? { ...range, from: new Date(requestRows[0].from) }
    : range
  const requestsTotal = counts.data?.total_count ?? requestRows.reduce((sum, item) => sum + item.read_count + item.write_count + item.other_count, 0)
  const readTotal = requestRows.reduce((sum, item) => sum + item.read_count, 0)
  const writeTotal = requestRows.reduce((sum, item) => sum + item.write_count, 0)
  const otherTotal = requestRows.reduce((sum, item) => sum + item.other_count, 0)
  const busy = counts.loading || bursts.loading || dashboardIncidents.loading || actors.loading || newActors.loading || hosts.loading || (status.loading && !status.data)
  const error = counts.error ?? bursts.error ?? dashboardIncidents.error ?? actors.error ?? newActors.error ?? hosts.error ?? (status.data ? null : status.error)
  const chartError = chartMode === 'bursts' ? burstChart.error : chartMode === 'incidents' ? incidentChart.error : null
  const retry = () => { counts.reload(); if (chartMode === 'bursts') burstChart.reload(); if (chartMode === 'incidents') incidentChart.reload(); bursts.reload(); dashboardIncidents.reload(); actors.reload(); newActors.reload(); hosts.reload(); status.reload() }
  const beginBurstHintHover = (key: string, slot: HTMLDivElement) => {
    if (burstHintIdleTimer.current !== null) {
      window.clearTimeout(burstHintIdleTimer.current)
      burstHintIdleTimer.current = null
    }
    activeBurstHint.current = { key, slot }
    lastBurstHintPointer.current = null
    if (!burstHintDelayActive) {
      setOpenBurstHintKey(key)
      return
    }
    if (burstHintOpenTimer.current !== null) return
    burstHintOpenTimer.current = window.setTimeout(() => {
      burstHintOpenTimer.current = null
      setOpenBurstHintKey(key)
      setBurstHintDelayActive(false)
    }, 250)
  }
  const cancelBurstHintHover = (key: string) => {
    if (activeBurstHint.current?.key !== key) return
    if (burstHintOpenTimer.current !== null) {
      window.clearTimeout(burstHintOpenTimer.current)
      burstHintOpenTimer.current = null
    }
  }
  const changeBurstSort = (column: BurstSortColumn) => setBurstSort({ column, direction: burstSort.column === column && burstSort.direction === 'asc' ? 'desc' : 'asc' })
  const maxBucket = Math.max(1, ...(chartMode === 'requests' ? requestRows.map((item) => item.read_count + item.write_count + item.other_count) : chartMode === 'bursts' ? burstChartRows.map((item) => item.burst_count) : incidentChartRows.map((item) => item.incident_count)))
  const chartTotal = chartMode === 'requests' ? requestsTotal : chartMode === 'bursts' ? burstChartRows.reduce((sum, item) => sum + item.burst_count, 0) : incidentChart.data?.incident_count ?? 0
  const burstRead = bursts.data?.summary.read_count ?? 0
  const burstWrite = bursts.data?.summary.write_count ?? 0
  const burstOther = bursts.data?.summary.other_count ?? 0
  const burstTotal = burstRead + burstWrite + burstOther
  const burstReadEnd = burstTotal ? burstRead / burstTotal * 100 : 100 / 3
  const burstWriteEnd = burstTotal ? (burstRead + burstWrite) / burstTotal * 100 : 200 / 3
  const burstOtherEnd = 100
  const burstRingStyle = { background: `conic-gradient(var(--blue) 0 ${burstReadEnd}%, var(--green) ${burstReadEnd}% ${burstWriteEnd}%, var(--amber) ${burstWriteEnd}% ${burstOtherEnd}%)` }
  const incidentSummary = dashboardIncidents.data?.summary
  const incidentTotal = incidentSummary?.incident_count ?? 0
  const incidentOpen = incidentSummary?.open_count ?? 0
  const incidentAcknowledged = incidentSummary?.acknowledged_count ?? 0
  const incidentResolved = incidentSummary?.resolved_count ?? 0
  const incidentRingEndOpen = incidentTotal ? incidentOpen / incidentTotal * 100 : 100 / 3
  const incidentRingEndAcknowledged = incidentTotal ? (incidentOpen + incidentAcknowledged) / incidentTotal * 100 : 200 / 3
  const incidentRingStyle = { background: `conic-gradient(var(--amber) 0 ${incidentRingEndOpen}%, var(--blue) ${incidentRingEndOpen}% ${incidentRingEndAcknowledged}%, var(--green) ${incidentRingEndAcknowledged}% 100%)` }
  const chartBars = chartMode === 'requests'
    ? requestRows.map((item, index) => {
      const total = item.read_count + item.write_count + item.other_count
      const height = total === 0 ? 1 : Math.max(2, total / maxBucket * 100)
      const hint = `${t('startDate')}: ${dateText(item.from, language)}\n${t('endDate')}: ${dateText(item.to, language)}\n${t('totalRequests')}: ${numberText(total, language)}\n${t('read')}: ${numberText(item.read_count, language)} (${shareText(item.read_count, total, language)})\n${t('write')}: ${numberText(item.write_count, language)} (${shareText(item.write_count, total, language)})\n${t('other')}: ${numberText(item.other_count, language)} (${shareText(item.other_count, total, language)})`
      const currentBucket = range.preset === 'today' && index === requestRows.length - 1
      return <div className={`bar-slot${currentBucket ? ' current-bucket' : ''}`} key={item.from ?? index} data-tooltip={hint} style={{ '--bar-height': `${height}%` } as CSSProperties}>
        <button type="button" className="chart-bar-hit" aria-label={hint} onClick={() => item.from && item.to && onBucketSelect({ from: item.from, to: item.to })}>
          <div className={`bar-stack${total === 0 ? ' zero-bar' : ''}`} style={{ height: `${height}%` }}><i className="bar-read" style={{ height: `${total ? item.read_count / total * 100 : 0}%` }} /><i className="bar-write" style={{ height: `${total ? item.write_count / total * 100 : 0}%` }} /><i className="bar-other" style={{ height: `${total ? item.other_count / total * 100 : 0}%` }} /></div>
        </button>
      </div>
    })
    : chartMode === 'bursts' ? burstChartRows.map((bucket, index) => {
      const count = bucket.burst_count
      const height = count === 0 ? 1 : Math.max(2, count / maxBucket * 100)
      const hint = `${t('startDate')}: ${dateText(bucket.from, language)}\n${t('endDate')}: ${dateText(bucket.to, language)}\n${t('bursts')}: ${numberText(count, language)}`
      const currentBucket = range.preset === 'today' && index === burstChartRows.length - 1
      return <div className={`bar-slot burst-bar-slot${currentBucket ? ' current-bucket' : ''}${openBurstHintKey === bucket.from ? ' is-open' : ''}${burstHintDelayActive ? ' initial-hint-delay' : ''}`} key={bucket.from} data-tooltip={hint} style={{ '--bar-height': `${height}%` } as CSSProperties} onMouseEnter={(event) => beginBurstHintHover(bucket.from, event.currentTarget)} onMouseLeave={() => cancelBurstHintHover(bucket.from)}>
        <div className="chart-bar-hit" aria-hidden="true"><div className={`bar-stack burst-bar-stack${count === 0 ? ' zero-bar' : ''}`} style={{ height: `${height}%` }} /></div>
        <div className="chart-burst-tooltip" role="tooltip"><strong>{t('burstsInBucket')} · {numberText(count, language)}</strong><small>{dateText(bucket.from, language)} – {dateText(bucket.to, language)}</small>
          {bucket.bursts.length ? bucket.bursts.map((burst) => {
            const requestCount = burst.read_count + burst.write_count + burst.other_count
            return <button type="button" className="chart-burst-row" key={burst.burst_id} onClick={() => onBurstSelect(burst.burst_id)}>
              <strong>#{burst.burst_id} · {dateText(burst.start_time, language)}</strong>
              <span>{t('actor')}: {burst.actor_ip}</span><ActorMetadata {...burst} />
              <span>{t('host')}: {burst.host || '—'} · {numberText(requestCount, language)} {t('requestsLabel')}</span>
            </button>
          }) : <span className="chart-burst-empty">{t('noBurstsInBucket')}</span>}
        </div>
      </div>
    }) : incidentChartRows.map((bucket) => {
      const count = bucket.incident_count
      const height = count === 0 ? 1 : Math.max(2, count / maxBucket * 100)
      const incidents = bucket.incidents ?? []
      const hint = `${dateText(bucket.from, language)} – ${dateText(bucket.to, language)} · ${numberText(count, language)} ${t('incidents').toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')}`
      return <div className={`bar-slot burst-bar-slot${openBurstHintKey === bucket.from ? ' is-open' : ''}${burstHintDelayActive ? ' initial-hint-delay' : ''}`} key={bucket.from} data-tooltip={hint} style={{ '--bar-height': `${height}%` } as CSSProperties} onMouseEnter={(event) => beginBurstHintHover(bucket.from, event.currentTarget)} onMouseLeave={() => cancelBurstHintHover(bucket.from)}>
        <div className="chart-bar-hit" aria-hidden="true">
          <div className={`bar-stack burst-bar-stack incident-bar-stack${count === 0 ? ' zero-bar' : ''}`} style={{ height: `${height}%` }} />
        </div>
        <div className="chart-burst-tooltip" role="tooltip"><strong>{t('incidentsInBucket')} · {numberText(count, language)}</strong><small>{dateText(bucket.from, language)} – {dateText(bucket.to, language)}</small>
          {incidents.length ? incidents.map((incident) => <button type="button" className="chart-burst-row" key={incident.incident_id} onClick={() => onIncidentSelect(incident)}>
            <strong>#{incident.incident_id} · {incidentTypeText(incident, t)} · {dateText(incident.first_seen, language)}</strong>
            <span>{t('actor')}: {incident.actor_ip}</span><ActorMetadata {...incident} />
            <span>{t('host')}: {incident.summary?.host_count > 1 ? t('multipleHosts') : incident.host || '—'} · {numberText(incident.request_count, language)} {t('requestsLabel')}</span>
          </button>) : <span className="chart-burst-empty">{t('noIncidentsInBucket')}</span>}
        </div>
      </div>
    })

  return <>
    <PageHeading title={t('overview')} subtitle={t('subtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    {busy || error ? <PageDataState loading={busy} error={error} retry={retry} t={t} /> : <>
      <section className="metric-grid" aria-label={t('trafficSummary')}>
        <MetricCard t={t} language={language} label={t('totalRequests')} value={numberText(requestsTotal, language)} icon={Activity} iconClass="blue" trend={trends.data?.metrics.request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} />
        <div className="panel metric-card dashboard-dual-card"><div className="metric-top"><span>{t('burstsAndIncidents')}</span><span className="metric-icon amber"><ShieldAlert size={17} /></span></div><div className="dashboard-dual-values"><div><span>{t('bursts')}</span><strong>{numberText(bursts.data?.summary.burst_count, language)}</strong><div className={`metric-trend ${trends.data?.metrics.burst_count?.direction ?? 'steady'}${trends.loading ? ' loading' : ''}`}>{trends.loading ? <span>{t('trendLoading')}</span> : trends.data?.metrics.burst_count && <><TrendDirectionIcon direction={trends.data.metrics.burst_count.direction} /><span>{trendPercentText(trends.data.metrics.burst_count)}</span></>}</div></div><div><span>{t('incidents')}</span><strong>{numberText(incidentTotal, language)}</strong><div className={`metric-trend ${trends.data?.metrics.incident_count?.direction ?? 'steady'}${trends.loading ? ' loading' : ''}`}>{trends.loading ? <span>{t('trendLoading')}</span> : trends.data?.metrics.incident_count && <><TrendDirectionIcon direction={trends.data.metrics.incident_count.direction} /><span>{trendPercentText(trends.data.metrics.incident_count)}</span></>}</div></div></div></div>
        <MetricCard t={t} language={language} label={t('uniqueActors')} value={numberText(actors.data?.total, language)} icon={Users} iconClass="violet" caption={`${numberText(newActors.data?.total, language)} ${t('newActors')}`} trend={trends.data?.metrics.actor_count} trendLoading={trends.loading} trendAbsoluteUnit={t('actors')} />
        <MetricCard t={t} language={language} label={t('detectedHosts')} value={numberText(hosts.data?.items.length, language)} icon={Network} iconClass="green" caption={`${t('knownHosts')}: ${numberText(hosts.data?.known_count, language)}`} trend={trends.data?.metrics.host_count} trendLoading={trends.loading} trendAbsoluteUnit={t('hosts')} />
      </section>
      <section className="primary-grid">
        <div className="panel traffic-panel">
          <div className="panel-header chart-heading"><div><h2>{t('trafficActivity')}</h2><p>{t(chartMode === 'requests' ? 'trafficDescription' : chartMode === 'bursts' ? 'burstTrafficDescription' : 'incidentTrafficDescription')}</p></div><div className="chart-mode-switch" role="group" aria-label={t('trafficActivity')}><button type="button" aria-pressed={chartMode === 'requests'} className={chartMode === 'requests' ? 'active' : ''} onClick={() => onChartModeChange('requests')}>{t('chartModeRequests')}</button><button type="button" aria-pressed={chartMode === 'bursts'} className={chartMode === 'bursts' ? 'active' : ''} onClick={() => onChartModeChange('bursts')}>{t('chartModeBursts')}</button><button type="button" aria-pressed={chartMode === 'incidents'} className={chartMode === 'incidents' ? 'active' : ''} onClick={() => onChartModeChange('incidents')}>{t('chartModeIncidents')}</button></div></div>
          <div className="chart-summary"><div><strong>{(chartMode === 'bursts' && burstChart.loading) || (chartMode === 'incidents' && incidentChart.loading) ? t('loadingData') : numberText(chartTotal, language)}</strong><span>{t(chartMode === 'requests' ? 'requestsLabel' : chartMode === 'bursts' ? 'bursts' : 'incidents')}</span></div></div>
          <div className="chart-wrap" role="group" aria-label={t('trafficActivity')}>
            {chartError && <div className="chart-inline-error" role="alert"><span>{t('apiUnavailable')}</span><button type="button" onClick={() => chartMode === 'bursts' ? burstChart.reload() : incidentChart.reload()}>{t('retry')}</button></div>}
            <div className="y-labels"><span>{numberText(maxBucket, language)}</span><span>{numberText(Math.round(maxBucket * .75), language)}</span><span>{numberText(Math.round(maxBucket * .5), language)}</span><span>{numberText(Math.round(maxBucket * .25), language)}</span><span>0</span></div>
            <div className="chart-main"><div className="grid-lines"><i /><i /><i /><i /><i /></div><div className="bars">{chartBars}</div><div className="x-labels"><span>{rangeTick(chartRange, 0, language, range.preset === 'last24h')}</span><span>{rangeTick(chartRange, .25, language, range.preset === 'last24h')}</span><span>{rangeTick(chartRange, .5, language, range.preset === 'last24h')}</span><span>{rangeTick(chartRange, .75, language, range.preset === 'last24h')}</span><span>{rangeTick(chartRange, 1, language, range.preset === 'last24h')}</span></div></div>
          </div>
          <div className="chart-legend">{chartMode === 'requests' ? <><span><i className="legend-dot read-dot" />{t('read')} · {numberText(readTotal, language)}</span><span><i className="legend-dot write-dot" />{t('write')} · {numberText(writeTotal, language)}</span><span><i className="legend-dot other-dot" />{t('other')} · {numberText(otherTotal, language)}</span>{range.preset === 'today' && <span><i className="legend-dot current-hour-dot" />{t('currentHour')}</span>}</> : <span><i className={`legend-dot ${chartMode === 'incidents' ? 'incident-dot' : 'burst-dot'}`} />{t(chartMode === 'incidents' ? 'incidents' : 'bursts')} · {numberText(chartTotal, language)}</span>}</div>
        </div>
        <div className="panel burst-panel">
          <div className="panel-header"><div><h2>{t(overviewMode === 'bursts' ? 'burstOverview' : 'incidentOverview')}</h2><p>{t(overviewMode === 'bursts' ? 'burstDescription' : 'incidentOverviewDescription')}</p></div><div className="chart-mode-switch" role="group" aria-label={t('burstsAndIncidents')}><button type="button" aria-pressed={overviewMode === 'bursts'} className={overviewMode === 'bursts' ? 'active' : ''} onClick={() => onOverviewModeChange('bursts')}>{t('bursts')}</button><button type="button" aria-pressed={overviewMode === 'incidents'} className={overviewMode === 'incidents' ? 'active' : ''} onClick={() => onOverviewModeChange('incidents')}>{t('incidents')}</button></div></div>
          {overviewMode === 'bursts' ? <><div className="burst-highlight"><div className="burst-ring" style={burstRingStyle}><div><strong>{numberText(bursts.data?.summary.burst_count, language)}</strong><span>{t('bursts').toLocaleUpperCase(language === 'de' ? 'de-DE' : 'en-US')}</span></div></div><div className="burst-stats"><div className="burst-stats-total"><span>{t('totalRequests')}</span><strong>{numberText(burstTotal, language)}</strong></div><div><span><i className="legend-dot read-dot" />{t('read')} · {shareText(burstRead, burstTotal, language)}</span><strong className="burst-stats-count">{numberText(burstRead, language)}</strong></div><div><span><i className="legend-dot write-dot" />{t('write')} · {shareText(burstWrite, burstTotal, language)}</span><strong className="burst-stats-count">{numberText(burstWrite, language)}</strong></div><div><span><i className="legend-dot other-dot" />{t('other')} · {shareText(burstOther, burstTotal, language)}</span><strong className="burst-stats-count">{numberText(burstOther, language)}</strong></div></div></div><div className="burst-footer"><span>{numberText(bursts.data?.summary.avg_requests_per_second, language)} {t('avgPerSecond')}</span><span>{rangeLabel(range, t, language)}</span></div></> : <><div className="burst-highlight"><div className="burst-ring" style={incidentRingStyle}><div><strong>{numberText(incidentTotal, language)}</strong><span>{t('incidents').toLocaleUpperCase(language === 'de' ? 'de-DE' : 'en-US')}</span></div></div><div className="burst-stats"><div><span><i className="legend-dot other-dot" />{t('incidentOpen')}</span><strong>{numberText(incidentOpen, language)}</strong></div><div><span><i className="legend-dot read-dot" />{t('incidentAcknowledged')}</span><strong>{numberText(incidentAcknowledged, language)}</strong></div><div><span><i className="legend-dot write-dot" />{t('incidentResolved')}</span><strong>{numberText(incidentResolved, language)}</strong></div></div></div><div className="burst-footer"><span>{numberText(incidentSummary?.request_count, language)} {t('requestsLabel')}</span><span>{rangeLabel(range, t, language)}</span></div></>}
        </div>
      </section>
      <section className="lower-grid">
        <div className="panel table-panel dashboard-table-panel"><div className="panel-header"><div><h2>{t(tableMode === 'bursts' ? 'burstsInPeriod' : 'incidentsInPeriod')}</h2></div><div className="chart-mode-switch" role="group" aria-label={t('burstsAndIncidents')}><button type="button" aria-pressed={tableMode === 'bursts'} className={tableMode === 'bursts' ? 'active' : ''} onClick={() => onTableModeChange('bursts')}>{t('bursts')}</button><button type="button" aria-pressed={tableMode === 'incidents'} className={tableMode === 'incidents' ? 'active' : ''} onClick={() => onTableModeChange('incidents')}>{t('incidents')}</button></div></div>
          {tableMode === 'bursts' ? <TableScroller t={t} className="dashboard-burst-scroll"><table><thead><tr><SortableHeader column="start_time" label={t('startTime')} sort={burstSort} onSort={changeBurstSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="actor_ip" label={t('actor')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="host" label={t('host')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="country" label={t('country')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="duration" label={t('duration')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="requests" label={t('requestsLabel')} sort={burstSort} onSort={changeBurstSort} /><th /></tr></thead><tbody>{bursts.data?.items.length ? bursts.data.items.map((burst) => <tr key={burst.burst_id}><td>{dateText(burst.start_time, language)}</td><td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={burst.actor_ip} t={t} /><button type="button" className="table-link primary-cell" onClick={() => onBurstSelect(burst.burst_id)}>{burst.actor_ip}</button></span><small>{burst.provider || '—'} · {burst.asn || '—'}</small></span></td><td className={`host-cell${burst.known ? ' known-host-name' : ''}`}>{burst.host || '—'}</td><td><span className="country-cell"><span className="country-flag" title={burst.country || ''}>{countryFlag(burst.country)}</span>{burst.country || '—'} · {burst.city || '—'}</span></td><td>{secondsText((new Date(burst.end_time).getTime() - new Date(burst.start_time).getTime()) / 1000, language)}</td><td><span className="request-count">{numberText(burst.read_count + burst.write_count + burst.other_count, language)}</span></td><td><button className="icon-button row-more" aria-label={t('viewBurstRequests')} title={t('viewBurstRequests')} onClick={() => onBurstSelect(burst.burst_id)}><ArrowUpRight size={15} /></button></td></tr>) : <EmptyRows t={t} columns={8} />}</tbody></table></TableScroller> : <TableScroller t={t} className="dashboard-incident-scroll"><table className="incident-dashboard-table"><thead><tr><th>{t('id')}</th><th>{t('incidentType')}</th><th>{t('incidentStart')}</th><th>{t('actor')}</th><th /></tr></thead><tbody>{dashboardIncidents.data?.items.length ? dashboardIncidents.data.items.map((incident) => <tr key={incident.incident_id} data-hint={`${t('host')}: ${incident.summary?.host_count > 1 ? t('multipleHosts') : incident.host || '—'}\n${t('requestsLabel')}: ${numberText(incident.request_count, language)}`}><td><button type="button" className="table-link" onClick={() => onIncidentSelect(incident)}>#{incident.incident_id}</button></td><td className="incident-type-cell">{incidentTypeText(incident, t)}</td><td><span className="incident-time-cell"><strong>{requestDateTimeText(incident.first_seen, language)}</strong><small>{incidentDurationText(incident.first_seen, incident.last_seen, language)}</small></span></td><td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={incident.actor_ip} t={t} /><strong>{incident.actor_ip}</strong></span><ActorMetadata {...incident} /></span></td><td><button className="icon-button row-more" aria-label={t('viewIncidentRequests')} title={t('viewIncidentRequests')} onClick={() => onIncidentSelect(incident)}><ArrowUpRight size={15} /></button></td></tr>) : <EmptyRows t={t} columns={5} />}</tbody></table></TableScroller>}
        </div>
        <div className="panel system-panel"><div className="panel-header"><div><h2>{t('status')}</h2><p>{t('infrastructure')}</p></div><span className={`health-pill ${status.data?.status === 'ok' ? '' : 'health-degraded'}`}><i />{status.data?.status === 'ok' ? t('allSystems') : t('degraded')}</span></div>
          <div className="system-list"><SystemRow icon={Activity} label={t('collector')} detail={activityText(status.data?.collector_status.activity, t)} healthy={status.data?.collector_status.available === true} /><SystemRow icon={Globe2} label={t('api')} detail={status.data?.status === 'ok' ? t('connected') : t('degraded')} healthy={status.data?.status === 'ok'} /><SystemRow icon={Database} label={t('database')} detail={status.data?.database === 'ok' ? t('operational') : t('degraded')} healthy={status.data?.database === 'ok'} />{status.data?.honeypot_configured && <SystemRow icon={Bug} label={t('honeypot')} detail={status.data.honeypot_available ? t('connected') : t('honeypotNotRunning')} healthy={status.data.honeypot_available === true} />}{status.data?.cowrie_configured && <SystemRow icon={Network} label={t('cowrie')} detail={status.data.cowrie_available ? t('cowrieLogAvailable') : t('cowrieLogUnavailable')} healthy={status.data.cowrie_available} />}</div>
          <div className="system-updated"><span className="status-pulse" />{t('lastImport')}: {dateText(status.data?.collector_status.last_import, language)}</div>
        </div>
      </section>
    </>}
  </>
}

function StatisticsPage({ t, language, range, onRangeChange, lastImport, section, onSectionChange, countryMode, onCountryModeChange, honeypotConfigured, cowrieConfigured, onBurstExtremeSelect, onBucketSelect, onBurstSelect, onIncidentSelect, onDistributionSelect }: RangePageProps & { section: StatisticsSection; onSectionChange: (section: StatisticsSection) => void; countryMode: 'events' | 'groups'; onCountryModeChange: (mode: 'events' | 'groups') => void; honeypotConfigured: boolean; cowrieConfigured: boolean; onBurstExtremeSelect: (extreme: BurstExtreme) => void; onBucketSelect: (bucket: TrafficBucket) => void; onBurstSelect: (id: number) => void; onIncidentSelect: (incident: NotificationIncident) => void; onDistributionSelect: (kind: 'provider' | 'country' | 'host' | 'category' | 'actor' | 'path', value: string) => void }) {
  useEffect(() => { if (!honeypotConfigured && section === 'honeypot') onSectionChange('overview') }, [honeypotConfigured, section, onSectionChange])
  useEffect(() => { if (!cowrieConfigured && section === 'ssh') onSectionChange('overview') }, [cowrieConfigured, section, onSectionChange])
  const result = useApiData<StatisticsResponse>(apiUrl('statistics', range.query))
  const traffic = useApiData<ApiResult<CountItem>>(apiUrl('request_counts', range.query, trafficBucketOptions(range)))
  const burstTraffic = useApiData<BurstChartResponse>(section === 'traffic' ? apiUrl('burst_counts', range.query, trafficBucketOptions(range)) : null)
  const insightQuery = section === 'insights' || section === 'hostsActors' ? apiUrl('statistics/insights', range.query, { timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' }) : null
  const insights = useApiData<StatisticsInsights>(insightQuery)
  const incidentStats = useApiData<IncidentStatistics>(section === 'incidents' || section === 'traffic' ? apiUrl('incident_statistics', range.query, { include_incidents: 'true' }) : null)
  const honeypotStats = useApiData<HoneypotStatistics>(honeypotConfigured && (section === 'traffic' || section === 'honeypot') ? apiUrl('honeypot/statistics', range.query) : null)
  const cowrieStats = useApiData<CowrieStatistics>(cowrieConfigured && (section === 'traffic' || section === 'ssh') ? apiUrl('cowrie/statistics', range.query) : null)
  const retry = () => { result.reload(); if (section === 'traffic') { traffic.reload(); burstTraffic.reload(); incidentStats.reload(); if (honeypotConfigured) honeypotStats.reload(); if (cowrieConfigured) cowrieStats.reload() } if (insightQuery) insights.reload(); if (section === 'incidents') incidentStats.reload(); if (section === 'honeypot') honeypotStats.reload(); if (section === 'ssh') cowrieStats.reload() }
  const requestsText = (count: number | null) => `${numberText(count, language)} ${count === 1 ? t('requestSingular') : t('requestsLabel')}`
  const optionalRequestsText = (count: number | null) => count == null ? '—' : requestsText(count)
  const optionalSecondsText = (seconds: number | null) => seconds == null ? '—' : preciseSecondsText(seconds, language)
  return <>
    <PageHeading title={t('statistics')} subtitle={t('statisticsSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading} error={result.error} retry={retry} t={t} />
    <nav className="statistics-tabs" aria-label={t('statisticsSections')}>
      {(['overview', 'traffic', 'patterns', 'incidents', 'hostsActors', 'insights', ...(honeypotConfigured ? ['honeypot' as const] : []), ...(cowrieConfigured ? ['ssh' as const] : [])] as const).map((key) => <button type="button" key={key} className={section === key ? 'active' : ''} aria-current={section === key ? 'page' : undefined} onClick={() => onSectionChange(key)}>{t(key === 'overview' ? 'statisticsOverview' : key === 'traffic' ? 'statisticsTimeSeries' : key === 'patterns' ? 'statisticsPatterns' : key === 'hostsActors' ? 'statisticsActorsHosts' : key === 'insights' ? 'statisticsInsights' : key === 'honeypot' ? 'honeypotStatistics' : key === 'ssh' ? 'cowrieStatistics' : 'incidentStatistics')}</button>)}
    </nav>
    {section === 'incidents' && <IncidentStatisticsView data={incidentStats.data} loading={incidentStats.loading} error={Boolean(incidentStats.error)} language={language} range={range} t={t} onIncidentSelect={onIncidentSelect} />}
    {section === 'traffic' && <section className="statistics-grid statistics-time-series-grid">
      <TrafficTimeline items={traffic.data?.items ?? []} loading={traffic.loading} language={language} range={range} t={t} onBucketSelect={onBucketSelect} />
      <BurstTimeline items={burstTraffic.data?.items ?? []} loading={burstTraffic.loading} language={language} range={range} t={t} onBurstSelect={onBurstSelect} />
      <IncidentTimeline items={incidentStats.data?.timeline ?? []} loading={incidentStats.loading} error={Boolean(incidentStats.error)} language={language} range={range} t={t} onIncidentSelect={onIncidentSelect} />
      {honeypotConfigured && <HoneypotTimeline items={honeypotStats.data?.timeline ?? []} loading={honeypotStats.loading} language={language} range={range} t={t} />}
      {cowrieConfigured && <CowrieTimeline items={cowrieStats.data?.timeline ?? []} loading={cowrieStats.loading} error={Boolean(cowrieStats.error)} language={language} range={range} t={t} />}
    </section>}
    {section === 'honeypot' && honeypotConfigured && <>
      <p className="incident-statistics-subtitle">{honeypotStats.error ? t('apiUnavailable') : honeypotStats.loading && !honeypotStats.data ? t('statisticsLoading') : t('honeypotIncidentMatchNote')}</p>
      <section className="statistics-burst-metrics">
        <MetricCard t={t} language={language} label={t('honeypotAccesses')} value={numberText(honeypotStats.data?.access_count ?? 0, language)} icon={Bug} iconClass="violet" caption={t('honeypotAccessesNote')} />
        <MetricCard t={t} language={language} label={t('honeypotIncidentMatches')} value={numberText(honeypotStats.data?.matched_access_count ?? 0, language)} icon={ShieldAlert} iconClass="blue" caption={`${numberText(honeypotStats.data?.matched_incident_count ?? 0, language)} ${t('incidentStatistics')}`} />
        <MetricCard t={t} language={language} label={t('honeypotUnmatchedAccesses')} value={numberText(honeypotStats.data?.unmatched_access_count ?? 0, language)} icon={Activity} iconClass="green" caption={t('honeypotUnmatchedNote')} />
      </section>
      <section className="statistics-grid">
        <HoneypotTimeline items={honeypotStats.data?.timeline ?? []} loading={honeypotStats.loading} language={language} range={range} t={t} />
        <StatisticsBarsPanel title={t('honeypotAccessTypes')} description={t('honeypotAccessTypesNote')} items={honeypotStats.data?.by_method ?? null} loading={honeypotStats.loading && !honeypotStats.data} error={Boolean(honeypotStats.error)} t={t} language={language} />
        <StatisticsBarsPanel title={t('honeypotAccessRules')} description={t('honeypotAccessRulesNote')} items={honeypotStats.data?.by_rule ?? null} loading={honeypotStats.loading && !honeypotStats.data} error={Boolean(honeypotStats.error)} t={t} language={language} />
        <CountryStatisticsPanel mode={countryMode} onModeChange={onCountryModeChange} items={honeypotStats.data?.countries ?? null} loading={honeypotStats.loading && !honeypotStats.data} error={Boolean(honeypotStats.error)} t={t} language={language} />
      </section>
    </>}
    {section === 'ssh' && cowrieConfigured && <>
      <p className="incident-statistics-subtitle">{cowrieStats.error ? t('apiUnavailable') : cowrieStats.loading && !cowrieStats.data ? t('statisticsLoading') : t('cowrieEventsNote')}</p>
      <section className="statistics-burst-metrics statistics-ssh-metrics">
        <MetricCard t={t} language={language} label={t('cowrieEvents')} value={numberText(cowrieStats.data?.event_count ?? 0, language)} icon={Activity} iconClass="violet" />
        <MetricCard t={t} language={language} label={t('cowrieFailedLogins')} value={numberText(cowrieStats.data?.failed_login_count ?? 0, language)} icon={ShieldAlert} iconClass="amber" />
        <MetricCard t={t} language={language} label={t('cowrieCommands')} value={numberText(cowrieStats.data?.command_count ?? 0, language)} icon={FileText} iconClass="blue" />
      </section>
      <section className="statistics-grid">
        <StatisticsBarsPanel title={t('cowrieEventTypes')} description={t('cowrieEventTypesNote')} items={cowrieStats.data?.by_type.map((item) => ({ name: cowrieEventLabel(item.name), request_count: item.event_count, share_percent: item.share_percent })) ?? null} loading={cowrieStats.loading && !cowrieStats.data} error={Boolean(cowrieStats.error)} t={t} language={language} />
        <CountryStatisticsPanel mode={countryMode} onModeChange={onCountryModeChange} items={cowrieStats.data?.countries ?? null} loading={cowrieStats.loading && !cowrieStats.data} error={Boolean(cowrieStats.error)} t={t} language={language} />
      </section>
    </>}
    {section === 'patterns' && <section className="statistics-grid statistics-patterns-grid">
      <StatisticsBarsPanel title={t('statisticsStatusCodes')} description={t('statisticsStatusCodesNote')} items={result.data?.status_codes ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} />
      <StatisticsBarsPanel title={t('statisticsTopPaths')} description={t('statisticsTopPathsNote')} items={result.data?.paths ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} />
      <StatisticsBarsPanel title={t('statisticsBurstSizes')} description={t('statisticsBurstSizesNote')} items={result.data?.burst_sizes ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} />
      <StatisticsBarsPanel title={t('statisticsRequestGaps')} description={t('statisticsRequestGapsNote')} items={result.data?.request_gaps ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} />
      <StatisticsBarsPanel title={t('statisticsMethods')} description={t('statisticsMethodsNote')} items={result.data?.methods ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} />
    </section>}
    {section === 'hostsActors' && <section className="statistics-grid">
      <DualSeriesTimeline title={t('statisticsHostTrafficTimeline')} description={t('statisticsHostTrafficNote')} items={result.data?.host_traffic ?? []} loading={result.loading && !result.data} t={t} language={language} range={range} series={[{ key: 'known_count', label: t('knownHosts'), color: 'known' }, { key: 'other_count', label: t('foreignHosts'), color: 'unknown' }]} />
      <DualSeriesTimeline title={t('statisticsNewActorsHosts')} description={t('statisticsNewActorsHostsNote')} items={result.data?.new_entities ?? []} loading={result.loading && !result.data} t={t} language={language} range={range} series={[{ key: 'actor_count', label: t('actors'), color: 'actors' }, { key: 'host_count', label: t('hosts'), color: 'hosts' }]} />
      <DistributionPanel title={t('statisticsActiveActors')} description={t('statisticsActiveActorsNote')} items={insights.data?.active_actors ?? null} loading={insights.loading && !insights.data} error={Boolean(insights.error)} t={t} language={language} actorDetails onItemSelect={(value) => onDistributionSelect('actor', value)} />
    </section>}
    {section === 'insights' && <section className="statistics-grid statistics-insights-grid">
      <DistributionPanel title={t('statisticsErrorHosts')} description={t('statisticsErrorHostsNote')} countLabel={t('statisticsErrorRequests')} items={insights.data?.error_hosts ?? null} loading={insights.loading && !insights.data} error={Boolean(insights.error)} t={t} language={language} onItemSelect={(value) => onDistributionSelect('host', value)} />
      <DistributionPanel title={t('statisticsErrorPaths')} description={t('statisticsErrorPathsNote')} countLabel={t('statisticsErrorRequests')} items={insights.data?.error_paths ?? null} loading={insights.loading && !insights.data} error={Boolean(insights.error)} t={t} language={language} onItemSelect={(value) => onDistributionSelect('path', value)} />
      <WeekdayHourHeatmap items={insights.data?.weekday_hours ?? []} loading={insights.loading} error={Boolean(insights.error)} language={language} t={t} />
      <StatusTrendTimeline items={insights.data?.status_trend ?? []} loading={insights.loading} error={Boolean(insights.error)} language={language} range={range} t={t} />
    </section>}
    {section === 'overview' && <>
    <section className="statistics-burst-metrics">
      <PairedMetricCard label={t('statisticsAverageRequests')} icon={Activity} iconClass="blue" firstLabel={t('bursts')} firstValue={result.data?.avg_requests_per_burst == null ? '—' : decimalText(result.data.avg_requests_per_burst, language)} firstCaption={result.data ? <><span>{numberText(result.data.burst_count, language)} {t('bursts')} · </span><button type="button" className="statistics-extreme-link" onClick={() => onBurstExtremeSelect('min_requests')} disabled={result.data.min_requests_per_burst == null}>{t('minimumValue')} {result.data.min_requests_per_burst == null ? '—' : requestsText(result.data.min_requests_per_burst)}</button><span> · </span><button type="button" className="statistics-extreme-link" onClick={() => onBurstExtremeSelect('max_requests')} disabled={result.data.max_requests_per_burst == null}>{t('maximumValue')} {result.data.max_requests_per_burst == null ? '—' : requestsText(result.data.max_requests_per_burst)}</button></> : result.error ? t('apiUnavailable') : t('statisticsLoading')} secondLabel={t('incidents')} secondValue={result.data?.avg_requests_per_incident == null ? '—' : decimalText(result.data.avg_requests_per_incident, language)} secondCaption={result.data ? <><span>{numberText(result.data.incident_count, language)} {t('incidents')} · </span><button type="button" className="statistics-extreme-link" onClick={() => result.data?.min_requests_incident && onIncidentSelect(result.data.min_requests_incident)} disabled={!result.data.min_requests_incident}>{t('minimumValue')} {optionalRequestsText(result.data.min_requests_per_incident)}</button><span> · </span><button type="button" className="statistics-extreme-link" onClick={() => result.data?.max_requests_incident && onIncidentSelect(result.data.max_requests_incident)} disabled={!result.data.max_requests_incident}>{t('maximumValue')} {optionalRequestsText(result.data.max_requests_per_incident)}</button></> : result.error ? t('apiUnavailable') : t('statisticsLoading')} />
      <PairedMetricCard label={t('statisticsAverageDuration')} icon={Clock3} iconClass="violet" firstLabel={t('bursts')} firstValue={result.data?.avg_burst_duration_seconds == null ? '—' : preciseSecondsText(result.data.avg_burst_duration_seconds, language)} firstCaption={result.data ? <><button type="button" className="statistics-extreme-link" onClick={() => onBurstExtremeSelect('min_duration')} disabled={result.data.min_burst_duration_seconds == null}>{t('minimumValue')} {result.data.min_burst_duration_seconds == null ? '—' : `${preciseSecondsText(result.data.min_burst_duration_seconds, language)} (${requestsText(result.data.min_duration_request_count)})`}</button><span> · </span><button type="button" className="statistics-extreme-link" onClick={() => onBurstExtremeSelect('max_duration')} disabled={result.data.max_burst_duration_seconds == null}>{t('maximumValue')} {result.data.max_burst_duration_seconds == null ? '—' : `${preciseSecondsText(result.data.max_burst_duration_seconds, language)} (${requestsText(result.data.max_duration_request_count)})`}</button></> : result.error ? t('apiUnavailable') : t('statisticsLoading')} secondLabel={t('incidents')} secondValue={result.data?.avg_incident_duration_seconds == null ? '—' : preciseSecondsText(result.data.avg_incident_duration_seconds, language)} secondCaption={result.data ? <><button type="button" className="statistics-extreme-link" onClick={() => result.data?.min_duration_incident && onIncidentSelect(result.data.min_duration_incident)} disabled={!result.data.min_duration_incident}>{t('minimumValue')} {optionalSecondsText(result.data.min_incident_duration_seconds)}</button><span> · </span><button type="button" className="statistics-extreme-link" onClick={() => result.data?.max_duration_incident && onIncidentSelect(result.data.max_duration_incident)} disabled={!result.data.max_duration_incident}>{t('maximumValue')} {optionalSecondsText(result.data.max_incident_duration_seconds)}</button></> : result.error ? t('apiUnavailable') : t('statisticsLoading')} />
      <PairedMetricCard label={t('statisticsRequestShare')} icon={Activity} iconClass="green" firstLabel={t('bursts')} firstValue={result.data ? `${decimalText(result.data.burst_request_share_percent, language)}%` : '—'} firstCaption={result.data ? <>{numberText(result.data.burst_request_count, language)} {t('statisticsRequests')} · {numberText(result.data.non_burst_request_count, language)} {t('statisticsRequestsWithoutBurst')}</> : result.error ? t('apiUnavailable') : t('statisticsLoading')} secondLabel={t('incidents')} secondValue={result.data ? `${decimalText(result.data.incident_request_share_percent, language)}%` : '—'} secondCaption={result.data ? <>{numberText(result.data.incident_request_count, language)} {t('statisticsRequests')} · {numberText(result.data.non_incident_request_count, language)} {t('statisticsRequestsWithoutIncident')}</> : result.error ? t('apiUnavailable') : t('statisticsLoading')} />
    </section>
    <section className="statistics-grid">
      <DistributionPanel title={t('statisticsProviders')} items={result.data?.providers ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} onItemSelect={(value) => onDistributionSelect('provider', value)} />
      <DistributionPanel title={t('statisticsCountries')} description={t('statisticsCountriesNote')} items={result.data?.countries ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} country onItemSelect={(value) => onDistributionSelect('country', value)} />
      <DistributionPanel title={t('statisticsHosts')} items={result.data?.hosts ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} onItemSelect={(value) => onDistributionSelect('host', value)} />
      <DistributionPanel title={t('statisticsCategories')} items={result.data?.categories ?? null} loading={result.loading && !result.data} error={Boolean(result.error)} t={t} language={language} note={t('statisticsCategoryNote')} onItemSelect={(value) => onDistributionSelect('category', value)} />
    </section>
    </>}
  </>
}

function IncidentStatisticsView({ data, loading, error, language, range, t, onIncidentSelect }: { data: IncidentStatistics | null; loading: boolean; error: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string; onIncidentSelect: (incident: NotificationIncident) => void }) {
  const bars = (rows: StatisticsItem[] | undefined) => (rows ?? []).map((row) => ({
    ...row,
    name: row.name && incidentTypeLabels[row.name as IncidentType] ? t(incidentTypeLabels[row.name as IncidentType]) : row.name,
  }))
  const subtitle = error ? t('apiUnavailable') : loading && !data ? t('statisticsLoading') : t('incidentStatisticsSubtitle')
  const errorShare = data?.error_metrics.non_error_share_percent ?? 0
  const requestRate = data?.request_spike_metrics.average_rps
  return <>
    <p className="incident-statistics-subtitle">{subtitle}</p>
    {error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : <>
      <section className="metric-grid incident-statistics-metrics">
        <MetricCard t={t} language={language} label={t('incidentStatisticsTotal')} value={data ? numberText(data.incident_count, language) : '—'} icon={ShieldAlert} iconClass="violet" caption={data ? `${numberText(data.actor_count, language)} ${t('actors')} · ${numberText(data.host_count, language)} ${t('hosts')}` : t('statisticsLoading')} />
        <MetricCard t={t} language={language} label={t('incidentStatisticsLinkedRequests')} value={data ? numberText(data.linked_request_count, language) : '—'} icon={Activity} iconClass="blue" caption={t('incidentStatisticsLinkedRequestsNote')} />
        <MetricCard t={t} language={language} label={t('statisticsErrorRequests')} value={data ? numberText(data.error_metrics.error_count, language) : '—'} icon={Activity} iconClass="amber" caption={data ? `${decimalText(errorShare, language)}% ${t('incidentNonErrorShare')} · ${numberText(data.error_metrics.non_error_count, language)} ${t('incidentStatisticsNonErrors')}` : t('statisticsLoading')} />
        <MetricCard t={t} language={language} label={t('incidentStatisticsRequestRate')} value={requestRate == null ? '—' : `${decimalText(requestRate, language)} /s`} icon={Activity} iconClass="green" caption={data ? `${t('minimumValue')} ${data.request_spike_metrics.min_rps == null ? '—' : `${numberText(data.request_spike_metrics.min_rps, language)} /s`} · ${t('maximumValue')} ${data.request_spike_metrics.max_rps == null ? '—' : `${numberText(data.request_spike_metrics.max_rps, language)} /s`}` : t('statisticsLoading')} />
      </section>
      <section className="statistics-grid incident-statistics-grid">
        <IncidentTimeline items={data?.timeline ?? []} loading={loading && !data} error={error} language={language} range={range} t={t} onIncidentSelect={onIncidentSelect} />
        <StatisticsBarsPanel title={t('incidentStatisticsByType')} description={t('incidentStatisticsByTypeNote')} items={data ? bars(data.by_type) : null} loading={loading && !data} error={error} t={t} language={language} incidentLabels panelClass="incident-statistics-types" />
        <StatisticsBarsPanel title={t('incidentStatisticsTopActors')} description={t('incidentStatisticsTopActorsNote')} items={data ? data.top_actors : null} loading={loading && !data} error={error} t={t} language={language} actorMetadata panelClass="incident-statistics-hosts" />
        <StatisticsBarsPanel title={t('incidentStatisticsTopHosts')} description={t('incidentStatisticsTopHostsNote')} items={data ? data.top_hosts : null} loading={loading && !data} error={error} t={t} language={language} panelClass="incident-statistics-actors" />
      </section>
    </>}
  </>
}

function IncidentTimeline({ items, loading, error, language, range, t, onIncidentSelect }: { items: IncidentStatistics['timeline']; loading: boolean; error: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string; onIncidentSelect: (incident: NotificationIncident) => void }) {
  const max = Math.max(1, ...items.map((item) => item.incident_count))
  const total = items.reduce((sum, item) => sum + item.incident_count, 0)
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel incident-statistics-timeline">
    <div className="panel-header"><div><h2>{t('incidentStatisticsTimeline')}</h2><p>{t('incidentStatisticsTimelineNote')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : items.length ? <>
      <div className="statistics-chart-total"><span>{t('statisticsGroupTotal')}</span><strong>{numberText(total, language)}</strong></div>
      <div className="statistics-legend statistics-request-legend"><span><i className="incident" />{t('incidents')}</span></div>
      <TimelineChartFrame max={max} language={language}><div className="statistics-timeline statistics-request-timeline statistics-incident-timeline" aria-label={t('incidentStatisticsTimeline')}>
        {items.map((item) => {
          const height = item.incident_count ? Math.max(2, item.incident_count / max * 100) : 1
          const incidents = item.incidents ?? []
          const hint = `${formatter.format(new Date(item.from))}–${formatter.format(new Date(item.to))} · ${numberText(item.incident_count, language)} ${t('incidents').toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')}`
          return <div className="statistics-time-slot statistics-popup-slot statistics-incident-slot burst-bar-slot" key={item.from} tabIndex={0} role="group" aria-label={hint} style={{ '--bar-height': `${height}%`, '--tooltip-offset': `${Math.max(178 * item.incident_count / max + 8, 30)}px` } as CSSProperties}>
            <div className="statistics-time-bar"><i className={item.incident_count ? 'incident' : 'request-zero'} style={{ height: `${height}%` }} /></div>
            <div className="chart-burst-tooltip" role="tooltip"><strong>{t('incidentsInBucket')} · {numberText(item.incident_count, language)}</strong><small>{dateText(item.from, language)} – {dateText(item.to, language)}</small>
              {incidents.length ? incidents.map((incident) => <button type="button" className="chart-burst-row" key={incident.incident_id} onClick={() => onIncidentSelect(incident)}>
                <strong>#{incident.incident_id} · {incidentTypeText(incident, t)} · {dateText(incident.first_seen, language)}</strong>
                <span>{t('actor')}: {incident.actor_ip}</span><ActorMetadata {...incident} />
                <span>{t('host')}: {incident.summary?.host_count > 1 ? t('multipleHosts') : incident.host || '—'} · {numberText(incident.request_count, language)} {t('requestsLabel')}</span>
              </button>) : <span className="chart-burst-empty">{t('noIncidentsInBucket')}</span>}
            </div>
          </div>
        })}
      </div>
      <TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function TrafficTimeline({ items, loading, language, range, t, onBucketSelect }: { items: CountItem[]; loading: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string; onBucketSelect: (bucket: TrafficBucket) => void }) {
  const max = Math.max(1, ...items.map((item) => item.total_count ?? (item.read_count + item.write_count + item.other_count)))
  const total = items.reduce((sum, item) => sum + (item.total_count ?? item.read_count + item.write_count + item.other_count), 0)
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel">
    <div className="panel-header"><div><h2>{t('statisticsRequests')}</h2><p>{t('trafficDescription')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {items.length ? <>
      <div className="statistics-chart-total"><span>{t('statisticsGroupTotal')}</span><strong>{numberText(total, language)}</strong></div>
      <div className="statistics-legend statistics-request-legend"><span><i className="read" />{t('readRequests')}</span><span><i className="write" />{t('writeRequests')}</span><span><i className="other" />{t('otherRequests')}</span></div>
      <TimelineChartFrame max={max} language={language}><div className="statistics-timeline statistics-request-timeline" role="img" aria-label={t('statisticsTimeSeries')}>
        {items.map((item, index) => {
          const read = item.read_count || 0, write = item.write_count || 0, other = item.other_count || 0
          const total = item.total_count ?? read + write + other
          const hasRequests = read + write + other > 0
          const label = item.from ? formatter.format(new Date(item.from)) : String(index + 1)
          return <div className="statistics-time-slot statistics-popup-slot burst-bar-slot" key={`${item.from ?? index}`} tabIndex={0} role="group" aria-label={`${label}–${item.to ? formatter.format(new Date(item.to)) : ''} · ${numberText(total, language)} ${t('statisticsRequests')}`} style={{ '--bar-height': `${hasRequests ? Math.max(2, total / max * 100) : 1}%`, '--tooltip-offset': `${Math.max(178 * total / max + 8, 30)}px` } as CSSProperties}>
            <div className="statistics-time-bar">{hasRequests ? <><i className="read" style={{ height: `${read / max * 100}%` }} /><i className="write" style={{ height: `${write / max * 100}%` }} /><i className="other" style={{ height: `${other / max * 100}%` }} /></> : <i className="request-zero" />}</div>
            <div className="chart-burst-tooltip" role="tooltip"><strong>{numberText(total, language)} {t('statisticsRequests')}</strong><small>{label} – {item.to ? formatter.format(new Date(item.to)) : ''}</small>
              <small>{t('readRequests')}: {numberText(read, language)} · {t('writeRequests')}: {numberText(write, language)} · {t('otherRequests')}: {numberText(other, language)}</small>
              {item.from && item.to && <button type="button" className="chart-burst-row" onClick={() => onBucketSelect({ from: item.from!, to: item.to! })}><strong>{t('viewRequestsInBucket')}</strong></button>}
            </div>
          </div>
        })}
      </div>
      <TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function HoneypotTimeline({ items, loading, language, range, t }: { items: HoneypotStatistics['timeline']; loading: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string }) {
  const max = Math.max(1, ...items.map((item) => item.request_count))
  const total = items.reduce((sum, item) => sum + item.request_count, 0)
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel">
    <div className="panel-header"><div><h2>{t('honeypotAccessFrequency')}</h2><p>{t('honeypotAccessFrequencyNote')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {items.length ? <>
      <div className="statistics-chart-total"><span>{t('statisticsGroupTotal')}</span><strong>{numberText(total, language)}</strong></div>
      <div className="statistics-legend statistics-request-legend"><span><i className="honeypot" />{t('honeypotAccesses')}</span></div>
      <TimelineChartFrame max={max} language={language}><div className="statistics-timeline statistics-request-timeline" aria-label={t('honeypotAccessFrequency')}>
        {items.map((item) => {
          const label = formatter.format(new Date(item.from))
          const height = item.request_count ? Math.max(2, item.request_count / max * 100) : 1
          return <div className="statistics-time-slot" key={item.from} role="img" aria-label={`${label}–${formatter.format(new Date(item.to))} · ${numberText(item.request_count, language)} ${t('honeypotAccesses')}`} title={`${label} – ${formatter.format(new Date(item.to))}: ${numberText(item.request_count, language)} ${t('honeypotAccesses')}`}>
            <div className="statistics-time-bar"><i className={item.request_count ? 'honeypot' : 'request-zero'} style={{ height: `${height}%` }} /></div>
          </div>
        })}
      </div><TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function CowrieTimeline({ items, loading, error, language, range, t }: { items: CowrieStatistics['timeline']; loading: boolean; error: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string }) {
  const max = Math.max(1, ...items.map((item) => item.event_count))
  const total = items.reduce((sum, item) => sum + item.event_count, 0)
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel">
    <div className="panel-header"><div><h2>{t('cowrieAccessFrequency')}</h2><p>{t('cowrieAccessFrequencyNote')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : items.length ? <>
      <div className="statistics-chart-total"><span>{t('statisticsGroupTotal')}</span><strong>{numberText(total, language)}</strong></div>
      <div className="statistics-legend statistics-request-legend"><span><i className="cowrie" />{t('cowrieEvents')}</span></div>
      <TimelineChartFrame max={max} language={language}><div className="statistics-timeline statistics-request-timeline" aria-label={t('cowrieAccessFrequency')}>
        {items.map((item) => {
          const label = formatter.format(new Date(item.from))
          const height = item.event_count ? Math.max(2, item.event_count / max * 100) : 1
          return <div className="statistics-time-slot" key={item.from} role="img" aria-label={`${label}–${formatter.format(new Date(item.to))} · ${numberText(item.event_count, language)} ${t('cowrieEvents')}`} title={`${label} – ${formatter.format(new Date(item.to))}: ${numberText(item.event_count, language)} ${t('cowrieEvents')}`}>
            <div className="statistics-time-bar"><i className={item.event_count ? 'cowrie' : 'request-zero'} style={{ height: `${height}%` }} /></div>
          </div>
        })}
      </div><TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function BurstTimeline({ items, loading, language, range, t, onBurstSelect }: { items: BurstChartBucket[]; loading: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string; onBurstSelect: (id: number) => void }) {
  const max = Math.max(1, ...items.map((item) => item.burst_count))
  const total = items.reduce((sum, item) => sum + item.burst_count, 0)
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel">
    <div className="panel-header"><div><h2>{t('statisticsBursts')}</h2><p>{t('burstTrafficDescription')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {items.length ? <>
      <div className="statistics-chart-total"><span>{t('statisticsGroupTotal')}</span><strong>{numberText(total, language)}</strong></div>
      <div className="statistics-legend statistics-request-legend"><span><i className="burst" />{t('statisticsBursts')}</span></div>
      <TimelineChartFrame max={max} language={language}><div className="statistics-timeline statistics-request-timeline" aria-label={t('statisticsBursts')}>
        {items.map((item) => {
          const label = formatter.format(new Date(item.from))
          const height = item.burst_count ? Math.max(2, item.burst_count / max * 100) : 1
          return <div className="statistics-time-slot statistics-popup-slot burst-bar-slot" key={item.from} tabIndex={0} role="group" aria-label={`${label}–${formatter.format(new Date(item.to))} · ${numberText(item.burst_count, language)} ${t('statisticsBursts')}`} style={{ '--bar-height': `${height}%`, '--tooltip-offset': `${Math.max(178 * item.burst_count / max + 8, 30)}px` } as CSSProperties}>
            <div className="statistics-time-bar"><i className={item.burst_count ? 'burst' : 'burst-zero'} style={{ height: `${height}%` }} /></div>
            <div className="chart-burst-tooltip" role="tooltip"><strong>{numberText(item.burst_count, language)} {t('statisticsBursts')}</strong><small>{dateText(item.from, language)} – {dateText(item.to, language)}</small>
              {item.bursts.length ? item.bursts.map((burst) => <button type="button" className="chart-burst-row" key={burst.burst_id} onClick={() => onBurstSelect(burst.burst_id)}>
                <strong>#{burst.burst_id} · {dateText(burst.start_time, language)}</strong><span>{t('actor')}: {burst.actor_ip}</span><ActorMetadata {...burst} />
                <span>{t('host')}: {burst.host || '—'} · {numberText(burst.read_count + burst.write_count + burst.other_count, language)} {t('requestsLabel')}</span>
              </button>) : <span className="chart-burst-empty">{t('noBurstsInBucket')}</span>}
            </div>
          </div>
        })}
      </div>
      <TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function DualSeriesTimeline({ title, description, items, loading, t, language, range, series }: { title: string; description: string; items: StatisticsBucket[]; loading: boolean; t: (key: MessageKey) => string; language: Language; range: TimeRange; series: { key: 'known_count' | 'other_count' | 'actor_count' | 'host_count'; label: string; color: string }[] }) {
  const max = Math.max(1, ...items.map((item) => series.reduce((sum, entry) => sum + (item[entry.key] ?? 0), 0)))
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from, items[items.length - 1]?.to, language)
  return <section className="panel statistics-timeline-panel statistics-dual-series-panel">
    <div className="panel-header"><div><h2>{title}</h2><p>{description}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {items.length ? <>
      <div className="statistics-legend">{series.map((entry) => <span key={entry.key}><i className={entry.color} />{entry.label}</span>)}</div>
      <TimelineChartFrame max={max} language={language} chartHeight={190} barHeight={148}><div className="statistics-timeline statistics-dual-timeline" role="img" aria-label={title}>
        {items.map((item) => {
          const values = series.map((entry) => ({ ...entry, count: item[entry.key] ?? 0 }))
          const total = values.reduce((sum, entry) => sum + entry.count, 0)
          const label = formatter.format(new Date(item.from))
          return <div className="statistics-time-slot" key={item.from} title={`${label}–${formatter.format(new Date(item.to))} · ${values.map((entry) => `${entry.label}: ${numberText(entry.count, language)}`).join(' · ')}`}>
            <div className="statistics-time-bar">{total > 0 ? values.map((entry) => <i key={entry.key} className={entry.color} style={{ height: `${entry.count / max * 100}%` }} />) : <i className="dual-zero" />}</div>
            <span className="statistics-sr-only">{numberText(total, language)}</span>
          </div>
        })}
      </div>
      <TimelineAxis labels={axisLabels} /></TimelineChartFrame>
    </> : <p className="statistics-empty">{t('statisticsNoData')}</p>}
  </section>
}

function WeekdayHourHeatmap({ items, loading, error, language, t }: { items: StatisticsInsights['weekday_hours']; loading: boolean; error: boolean; language: Language; t: (key: MessageKey) => string }) {
  const counts = Array.from({ length: 7 }, () => Array<number>(24).fill(0))
  for (const item of items) counts[item.weekday]?.splice(item.hour, 1, item.request_count)
  const max = Math.max(1, ...items.map((item) => item.request_count))
  const days = Array.from({ length: 7 }, (_, index) => new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { weekday: 'short' }).format(new Date(Date.UTC(2024, 0, 1 + index))))
  return <section className="panel statistics-panel statistics-heatmap-panel">
    <div className="panel-header"><div><h2>{t('statisticsWeekdayHour')}</h2><p>{t('statisticsWeekdayHourNote')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : loading && items.length === 0 ? <div className="statistics-panel-state"><span className="loading-spinner" />{t('statisticsLoading')}</div> : !loading && items.length === 0 ? <p className="statistics-empty">{t('statisticsNoData')}</p> : <div className="statistics-heatmap-scroll"><div className="statistics-heatmap">
      <span className="statistics-heatmap-corner" />{Array.from({ length: 24 }, (_, hour) => <small key={hour}>{hour % 3 === 0 ? String(hour).padStart(2, '0') : ''}</small>)}
      {counts.map((hours, weekday) => <Fragment key={weekday}><strong>{days[weekday]}</strong>{hours.map((count, hour) => <span key={hour} className="statistics-heat-cell" title={`${days[weekday]} ${String(hour).padStart(2, '0')}:00 · ${numberText(count, language)} ${t('statisticsRequests')}`} style={{ opacity: count ? 0.12 + count / max * 0.88 : 0.035 }} />)}</Fragment>)}
    </div></div>}
  </section>
}

function StatusTrendTimeline({ items, loading, error, language, range, t }: { items: StatisticsInsights['status_trend']; loading: boolean; error: boolean; language: Language; range: TimeRange; t: (key: MessageKey) => string }) {
  const keys = ['status_1xx', 'status_2xx', 'status_3xx', 'status_4xx', 'status_5xx'] as const
  const labels = ['status1xx', 'status2xx', 'status3xx', 'status4xx', 'status5xx'] as const
  const colors = ['status-1xx', 'status-2xx', 'status-3xx', 'status-4xx', 'status-5xx'] as const
  const max = Math.max(1, ...items.map((item) => keys.reduce((sum, key) => sum + (item[key] || 0), 0)))
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-US', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  const axisLabels = timelineAxisLabels(range, items[0]?.from_utc, items[items.length - 1]?.to_utc, language)
  return <section className="panel statistics-timeline-panel statistics-status-trend-panel">
    <div className="panel-header"><div><h2>{t('statisticsStatusTrend')}</h2><p>{t('statisticsStatusTrendNote')}</p></div>{loading && <span className="statistics-loading-inline"><span className="loading-spinner" />{t('statisticsLoading')}</span>}</div>
    {error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : items.length ? <><div className="statistics-legend">{keys.map((key, index) => <span key={key}><i className={colors[index]} />{t(labels[index])}</span>)}</div><TimelineChartFrame max={max} language={language} chartHeight={250} barHeight={178}><div className="statistics-timeline statistics-status-trend">
      {items.map((item) => {
        const total = keys.reduce((sum, key) => sum + (item[key] || 0), 0)
        const start = new Date(item.from_utc)
        const end = new Date(item.to_utc)
        return <div className="statistics-time-slot" key={item.bucket_index} title={`${formatter.format(start)} – ${formatter.format(end)} · ${numberText(total, language)} ${t('statisticsRequests')}\n${keys.map((key, i) => `${t(labels[i])}: ${numberText(item[key], language)}`).join(' · ')}`}>
          <div className="statistics-time-bar">{keys.map((key, i) => <i key={key} className={colors[i]} style={{ height: `${(item[key] || 0) / max * 100}%` }} />)}</div>
        </div>
      })}
    </div><TimelineAxis labels={axisLabels} /></TimelineChartFrame></> : <p className="statistics-empty">{loading ? t('statisticsLoading') : t('statisticsNoData')}</p>}
  </section>
}

function TimelineAxis({ labels }: { labels: string[] }) {
  return <div className="statistics-x-axis" aria-hidden="true">{labels.map((label, index) => <span key={index}>{label}</span>)}</div>
}

function TimelineChartFrame({ max, language, chartHeight = 220, barHeight = 178, children }: { max: number; language: Language; chartHeight?: number; barHeight?: number; children: ReactNode }) {
  const labels = [max, Math.round(max * .75), Math.round(max * .5), Math.round(max * .25), 0]
  return <div className="statistics-chart-frame" style={{ '--chart-height': `${chartHeight}px`, '--bar-height': `${barHeight}px` } as CSSProperties}>
    <div className="statistics-y-axis" aria-hidden="true">{labels.map((value, index) => <span key={index}>{numberText(value, language)}</span>)}</div>
    <div className="statistics-chart-plot"><div className="statistics-grid-lines" aria-hidden="true">{labels.map((_, index) => <i key={index} />)}</div>{children}</div>
  </div>
}

function StatisticsBarsPanel({ title, description, items, loading, error, t, language, incidentLabels = false, actorMetadata = false, panelClass = '' }: { title: string; description?: string; items: StatisticsItem[] | null; loading: boolean; error: boolean; t: (key: MessageKey) => string; language: Language; incidentLabels?: boolean; actorMetadata?: boolean; panelClass?: string }) {
  const rows = items ?? []
  const max = Math.max(1, ...rows.map((item) => item.request_count))
  const isStatusPanel = title === t('statisticsStatusCodes')
  const statusDescriptions: Record<number, [string, string]> = {
    100: ['Weiterverarbeitung', 'Continue'], 101: ['Protokollwechsel', 'Switching Protocols'], 102: ['Wird verarbeitet', 'Processing'], 103: ['Frühe Hinweise', 'Early Hints'],
    200: ['Erfolgreich', 'OK'], 201: ['Erstellt', 'Created'], 202: ['Angenommen', 'Accepted'], 204: ['Keine Inhalte', 'No Content'], 206: ['Teilinhalt', 'Partial Content'],
    300: ['Mehrere Möglichkeiten', 'Multiple Choices'], 301: ['Dauerhaft verschoben', 'Moved Permanently'], 302: ['Vorübergehend gefunden', 'Found'], 303: ['Siehe andere Adresse', 'See Other'], 304: ['Unverändert', 'Not Modified'], 307: ['Vorübergehend umgeleitet', 'Temporary Redirect'], 308: ['Dauerhaft umgeleitet', 'Permanent Redirect'],
    400: ['Ungültige Anfrage', 'Bad Request'], 401: ['Anmeldung erforderlich', 'Unauthorized'], 403: ['Zugriff verweigert', 'Forbidden'], 404: ['Nicht gefunden', 'Not Found'], 405: ['Methode nicht erlaubt', 'Method Not Allowed'], 408: ['Zeitüberschreitung', 'Request Timeout'], 409: ['Konflikt', 'Conflict'], 410: ['Nicht mehr verfügbar', 'Gone'], 413: ['Anfrage zu groß', 'Content Too Large'], 418: ['Ungewöhnliche Anfrage', "I'm a Teapot"], 422: ['Inhalt nicht verarbeitbar', 'Unprocessable Content'], 429: ['Zu viele Anfragen', 'Too Many Requests'],
    500: ['Interner Serverfehler', 'Internal Server Error'], 501: ['Nicht implementiert', 'Not Implemented'], 502: ['Ungültige Antwort eines Upstreams', 'Bad Gateway'], 503: ['Dienst nicht verfügbar', 'Service Unavailable'], 504: ['Zeitüberschreitung eines Upstreams', 'Gateway Timeout'],
  }
  const statusClassMeaning = (name: string) => {
    const group = Number(name.slice(0, 1))
    const meanings = language === 'de' ? ['Informativ', 'Erfolgreich', 'Umleitung', 'Clientfehler', 'Serverfehler'] : ['Informational', 'Success', 'Redirection', 'Client error', 'Server error']
    return meanings[group - 1] ?? name
  }
  return <section className={`panel statistics-panel ${panelClass}`.trim()}>
    <div className="panel-header"><div><h2>{title}</h2><p>{description ?? (items ? `${numberText(rows.length, language)} ${t('statisticsEntries')}` : t('statisticsAllEntries'))}</p></div></div>
    {loading ? <div className="statistics-panel-state"><span className="loading-spinner" />{t('statisticsLoading')}</div> : error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : isStatusPanel ? <div className="statistics-status-groups">{[1, 2, 3, 4, 5].map((hundreds) => {
      const className = `${hundreds}xx`
      const groupRows = rows.filter((item) => item.status_class === className)
      const groupTotal = groupRows.reduce((sum, item) => sum + item.request_count, 0)
      return <section className="statistics-status-group" key={className}>
        <h3>{className} <small>{t('statusGroupMeaning')}: {statusClassMeaning(className)}</small></h3>
        {groupRows.length ? groupRows.map((item) => {
          const code = Number(item.name)
          const description = statusDescriptions[code]?.[language === 'de' ? 0 : 1] ?? (language === 'de' ? 'Sonstiger Status' : 'Other status')
          return <div className="statistics-horizontal-row status-code-row" key={code}>
            <span>{code} <small>– {description}</small></span><div className="statistics-horizontal-track"><i style={{ width: `${item.request_count / max * 100}%` }} /></div><strong>{numberText(item.request_count, language)}</strong><small>{decimalText(item.share_percent, language)}%</small>
          </div>
        }) : <p className="statistics-group-empty">{t('noStatusesInGroup')}</p>}
        <span className="statistics-group-total">{t('statisticsGroupTotal')}: {numberText(groupTotal, language)}</span>
      </section>
    })}</div> : rows.length ? <div className={`statistics-horizontal-bars${incidentLabels ? ' incident-statistics-bars' : ''}`}>{rows.map((item) => <div className={`statistics-horizontal-row${actorMetadata ? ' statistics-actor-bar-row' : ''}`} key={item.name}>
      <span className="statistics-horizontal-label"><span className="statistics-label-text">{item.name}</span>{actorMetadata && <ActorMetadata {...item} />}</span><div className="statistics-horizontal-track"><i style={{ width: `${item.request_count / max * 100}%` }} /></div><strong>{numberText(item.request_count, language)}</strong><small>{decimalText(item.share_percent, language)}%</small>
    </div>)}</div> : <p className="statistics-empty">{t('statisticsNoData')}</p>}
  </section>
}

function CountryStatisticsPanel({ items, loading, error, t, language, mode, onModeChange }: { items: CountryStatisticsItem[] | null; loading: boolean; error: boolean; t: (key: MessageKey) => string; language: Language; mode: 'events' | 'groups'; onModeChange: (mode: 'events' | 'groups') => void }) {
  const showingGroups = mode === 'groups'
  const displayItems: StatisticsItem[] | null = items?.map((item) => ({
    name: item.name,
    request_count: showingGroups ? item.group_count : item.event_count,
    share_percent: showingGroups ? item.group_share_percent : item.event_share_percent,
  })).sort((left, right) => right.request_count - left.request_count || (left.name ?? '').localeCompare(right.name ?? '', language === 'de' ? 'de-DE' : 'en-US')) ?? null
  const toggle = <div className="statistics-mode-toggle" role="group" aria-label={t('statisticsCountryCountMode')}>
    <button type="button" className={!showingGroups ? 'active' : ''} aria-pressed={!showingGroups} onClick={() => onModeChange('events')}>{t('statisticsEvents')}</button>
    <button type="button" className={showingGroups ? 'active' : ''} aria-pressed={showingGroups} onClick={() => onModeChange('groups')}>{t('statisticsGroups')}</button>
  </div>
  return <DistributionPanel title={t('statisticsCountries')} description={t(showingGroups ? 'statisticsCountriesGroupsNote' : 'statisticsCountriesEventsNote')} countLabel={t(showingGroups ? 'statisticsGroups' : 'statisticsEvents')} items={displayItems} loading={loading} error={error} t={t} language={language} country headerControl={toggle} />
}

function DistributionPanel({ title, description, countLabel, items, loading, error, t, language, country = false, actorDetails = false, note, onItemSelect, headerControl }: { title: string; description?: string; countLabel?: string; items: StatisticsItem[] | null; loading: boolean; error: boolean; t: (key: MessageKey) => string; language: Language; country?: boolean; actorDetails?: boolean; note?: string; onItemSelect?: (value: string) => void; headerControl?: ReactNode }) {
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const pageSize = 10
  const rows = items ?? []
  const normalizedSearch = search.trim().toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')
  const filteredRows = normalizedSearch ? rows.filter((item) => Object.values(item).some((value) => value != null && String(value).toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US').includes(normalizedSearch))) : rows
  const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize))
  const visibleRows = filteredRows.slice(Math.min(page, pageCount - 1) * pageSize, (Math.min(page, pageCount - 1) + 1) * pageSize)
  useEffect(() => setPage(0), [normalizedSearch])
  return <section className="panel statistics-panel">
    <div className="panel-header"><div><h2>{title}</h2><p>{description ?? (items ? `${numberText(filteredRows.length, language)} ${t('statisticsEntries')}` : t('statisticsAllEntries'))}</p></div>{headerControl}</div>
    <label className="statistics-search"><Search size={14} /><input type="search" value={search} placeholder={t('statisticsSearch')} aria-label={`${t('statisticsSearch')} · ${title}`} onChange={(event) => setSearch(event.target.value)} /></label>
    {loading ? <div className="statistics-panel-state"><span className="loading-spinner" />{t('statisticsLoading')}</div> : error ? <p className="statistics-empty">{t('apiUnavailable')}</p> : rows.length ? <div className="statistics-list">
      <div className="statistics-label-row"><span /><span /><span>{countLabel ?? t('statisticsRequests')}</span><span>{t('statisticsShare')}</span></div>
      {visibleRows.map((item, index) => <div className="statistics-row" key={`${item.name ?? 'unknown'}-${index + page * pageSize}`}>
        <span className="statistics-rank">{page * pageSize + index + 1}</span>
        <div className="statistics-name-cell">{item.name ? onItemSelect ? <button type="button" className={`statistics-name table-link${item.known ? ' known-host-name' : ''}`} onClick={() => onItemSelect(item.name!)}>{country && <span className="country-flag" title={item.name}>{countryFlag(item.name)}</span>}{item.name}</button> : <span className="statistics-name">{country && <span className="country-flag" title={item.name}>{countryFlag(item.name)}</span>}{item.name}</span> : <span className="statistics-name">{t('unknown')}</span>}{actorDetails && <ActorMetadata {...(item as StatisticsInsights['active_actors'][number])} className="statistics-actor-details" />}<span className="statistics-share-track"><i style={{ width: `${Math.min(item.share_percent, 100)}%` }} /></span></div>
        <strong>{numberText(item.request_count, language)}</strong>
        <span className="statistics-percent">{decimalText(item.share_percent, language)}%</span>
      </div>)}
    </div> : <p className="statistics-empty">{normalizedSearch ? t('noResults') : t('statisticsNoData')}</p>}
    {items && pageCount > 1 && <div className="statistics-pagination"><span>{numberText(page + 1, language)} / {numberText(pageCount, language)}</span><div><button type="button" aria-label={t('previousPage')} title={t('previousPage')} disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ChevronLeft size={14} /></button><button type="button" aria-label={t('nextPage')} title={t('nextPage')} disabled={page >= pageCount - 1} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}><ChevronRight size={14} /></button></div></div>}
    {note && <p className="statistics-note">{note}</p>}
  </section>
}

function TrendDirectionIcon({ direction }: { direction: MetricTrend['direction'] }) {
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : ArrowRight
  return <Icon size={13} />
}

function trendPercentText(trend: MetricTrend) {
  const percent = Math.round(trend.change_percent)
  return `${percent > 0 ? '+' : percent < 0 ? '−' : ''}${Math.abs(percent)}%`
}

function MetricCard({ t, language, label, value, icon: Icon, iconClass, caption, trend, trendLoading = false, trendAbsoluteUnit, trendAbsoluteDecimals = 0 }: { t: (key: MessageKey) => string; language: Language; label: string; value: string; icon: typeof ArrowUpRight; iconClass: string; caption?: ReactNode; trend?: MetricTrend; trendLoading?: boolean; trendAbsoluteUnit?: string; trendAbsoluteDecimals?: number }) {
  const percent = trend ? Math.round(trend.change_percent) : 0
  const percentText = `${percent > 0 ? '+' : percent < 0 ? '−' : ''}${Math.abs(percent)}%`
  const showCountChange = Boolean(trend && trendAbsoluteUnit && Math.abs(percent) >= 1000)
  const countChange = (trend?.current ?? 0) - (trend?.previous ?? 0)
  const formatAbsolute = (value: number | undefined) => new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: trendAbsoluteDecimals }).format(value ?? 0)
  const countChangeText = `${countChange > 0 ? '+' : countChange < 0 ? '−' : ''}${formatAbsolute(Math.abs(countChange))} ${trendAbsoluteUnit ?? ''} · ${t('previousValue')} ${formatAbsolute(trend?.previous)}`
  const TrendIcon = trend?.direction === 'up' ? ArrowUpRight : trend?.direction === 'down' ? ArrowDownRight : ArrowRight
  return <div className="panel metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${iconClass}`}><Icon size={17} /></span></div><div className="metric-bottom"><strong className={value.length > 10 ? 'metric-value-compact' : ''}>{value}</strong></div><div className="metric-foot"><div className="metric-caption">{caption ?? ''}</div><div className={`metric-trend ${trend?.direction ?? 'steady'}${trendLoading ? ' loading' : ''}${showCountChange ? ' metric-trend-detail' : ''}`} aria-live="polite">{trendLoading ? <span>{t('trendLoading')}</span> : trend ? showCountChange ? <span>{countChangeText}</span> : <><TrendIcon size={13} /><span>{percentText}</span></> : null}</div></div></div>
}

function PairedMetricCard({ label, icon: Icon, iconClass, firstLabel, firstValue, firstCaption, secondLabel, secondValue, secondCaption }: { label: string; icon: typeof ArrowUpRight; iconClass: string; firstLabel: string; firstValue: string; firstCaption: ReactNode; secondLabel: string; secondValue: string; secondCaption: ReactNode }) {
  return <div className="panel metric-card statistics-paired-card">
    <div className="metric-top"><span>{label}</span><span className={`metric-icon ${iconClass}`}><Icon size={17} /></span></div>
    <div className="statistics-paired-values">
      <div><span>{firstLabel}</span><strong>{firstValue}</strong><small>{firstCaption}</small></div>
      <div><span>{secondLabel}</span><strong>{secondValue}</strong><small>{secondCaption}</small></div>
    </div>
  </div>
}

function SystemRow({ icon: Icon, label, detail, healthy, neutral = false }: { icon: typeof Activity; label: string; detail: string; healthy: boolean; neutral?: boolean }) {
  return <div className="system-row"><div className="system-icon"><Icon size={16} /></div><div className="system-copy"><strong>{label}</strong><span>{detail}</span></div><span className={`system-check ${neutral ? 'system-check-neutral' : healthy ? '' : 'system-check-error'}`}>{neutral ? '–' : healthy ? '✓' : '!'}</span></div>
}

function BurstsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onBurstSelect, pageSize, onPageSizeChange }: PaginatedPageProps & { sort: BurstSort; onSortChange: (sort: BurstSort) => void; filters: BurstFilters; onFiltersChange: (filters: BurstFilters) => void; onBurstSelect: (id: number) => void }) {
  const trends = useMetricTrends(range, 'bursts', { search: filters.search.trim(), host: filters.host, host_exact: filters.host ? 'true' : '', known: filters.known, country: filters.country, country_exact: filters.country ? 'true' : '', protected_only: filters.protectedOnly ? 'true' : '' })
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState<BurstFilters>(filters)
  const hostOptions = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query, { sort_by: 'host', sort_order: 'asc' }))
  const countryOptions = useApiData<ApiResult<{ country: string }>>(apiUrl('countries', range.query))
  const burstFilterParams = Object.fromEntries(Object.entries({ search: filters.search.trim(), host: filters.host, host_exact: filters.host ? 'true' : '', known: filters.known, country: filters.country, country_exact: filters.country ? 'true' : '', protected_only: filters.protectedOnly ? 'true' : '' }).filter(([, value]) => value))
  const result = useApiData<BurstResponse>(apiUrl('bursts', range.query, { limit: String(pageSize), offset: String(pageIndex * pageSize), sort_by: sort.column, sort_order: sort.direction, ...burstFilterParams }))
  const summary = result.data?.summary
  const items = result.data?.items ?? []
  const [deletingBurst, setDeletingBurst] = useState<number | null>(null)
  const deleteBurst = async (burstId: number) => {
    setDeletingBurst(burstId)
    try {
      const response = await apiFetch(apiUrl(`bursts/${burstId}`), { method: 'DELETE', headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      result.reload()
    } catch (error) { window.alert(`${t('deleteFailed')}: ${error instanceof Error ? error.message : String(error)}`) }
    finally { setDeletingBurst(null) }
  }
  const retry = () => { result.reload(); hostOptions.reload(); countryOptions.reload() }
  const changeSort = (column: BurstSortColumn) => {
    setPageIndex(0)
    onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' })
  }
  useEffect(() => setPageIndex(0), [range.query, filters.search, filters.host, filters.known, filters.country, filters.protectedOnly])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { const empty = { ...defaultBurstFilters }; setDraftFilters(empty); setPageIndex(0); onFiltersChange(empty) }
  return <>
    <PageHeading title={t('burstAnalysis')} subtitle={t('burstPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading} error={result.error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('burstSearchPlaceholder')} aria-label={t('burstSearchPlaceholder')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select"><Globe2 size={15} /><select aria-label={t('filterHost')} value={draftFilters.known === 'own' ? '__known__' : draftFilters.known === 'foreign' ? '__unknown__' : draftFilters.host} onChange={(event) => { const value = event.target.value; setDraftFilters((current) => value === '__known__' || value === '__unknown__' ? { ...current, host: '', known: value === '__known__' ? 'own' : 'foreign' } : { ...current, host: value, known: '' }) }}><option value="">{t('allHosts')}</option><option disabled value="__separator_all__">──────────</option><option value="__known__">{t('knownHostsOnly')}</option><option value="__unknown__">{t('unknownHostsOnly')}</option><option disabled>──────────</option>{hostOptions.data?.items.map((item) => <option key={item.host_id} value={item.host}>{item.host}</option>)}</select><span className="filter-select-value">{draftFilters.known === 'own' ? t('knownHostsOnly') : draftFilters.known === 'foreign' ? t('unknownHostsOnly') : draftFilters.host || t('allHosts')}</span><ChevronDown size={13} /></label><label className="filter-select country-filter"><select aria-label={t('filterCountry')} value={draftFilters.country} onChange={(event) => setDraftFilters((value) => ({ ...value, country: event.target.value }))}><option value="">{t('allCountries')}</option>{countryOptions.data?.items.map((item) => <option key={item.country} value={item.country}>{countryFlag(item.country)} {item.country}</option>)}</select><span className="filter-select-value">{draftFilters.country && <span className="country-flag">{countryFlag(draftFilters.country)}</span>}{draftFilters.country || t('allCountries')}</span><ChevronDown size={13} /></label><label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.protectedOnly} onChange={(event) => setDraftFilters((value) => ({ ...value, protectedOnly: event.target.checked }))} /><span>{t('protectedIpsOnly')}</span></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !result.error && <>
      <section className="burst-metrics">
        <MetricCard t={t} language={language} label={t('burstsInPeriod')} value={numberText(summary?.burst_count, language)} icon={Activity} iconClass="blue" trend={trends.data?.metrics.burst_count} trendLoading={trends.loading} trendAbsoluteUnit={t('bursts')} />
        <MetricCard t={t} language={language} label={t('affectedActors')} value={numberText(summary?.actor_count, language)} icon={Users} iconClass="violet" caption={`${numberText(summary?.new_actor_count, language)} ${t('newActorsWithBursts')}`} trend={trends.data?.metrics.burst_actor_count} trendLoading={trends.loading} trendAbsoluteUnit={t('actors')} />
        <MetricCard t={t} language={language} label={t('requestsInBursts')} value={numberText(summary?.request_count, language)} icon={Network} iconClass="green" caption={`${decimalText(summary?.avg_requests_per_burst, language)} ${t('avgRequestsPerBurst')}`} trend={trends.data?.metrics.burst_request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} />
        <MetricCard t={t} language={language} label={t('avgBurstDuration')} value={secondsText(summary?.avg_duration_seconds, language)} icon={Clock3} iconClass="amber" caption={`${t('maximumDuration')}: ${secondsText(summary?.max_duration_seconds, language)}`} trend={trends.data?.metrics.avg_burst_duration} trendLoading={trends.loading} trendAbsoluteUnit={t('secondsUnit')} trendAbsoluteDecimals={1} />
      </section>
      <section className="panel burst-composition">
        <div className="composition-copy"><div><h2>{t('requestTypes')}</h2><p>{t('burstRequestTypeHint')}</p></div><strong>{numberText(summary?.request_count, language)} <span>{t('requestsLabel')}</span></strong></div>
        <div className="composition-bar"><i className="bar-read" style={{ width: `${summary?.request_count ? (summary.read_count ?? 0) / summary.request_count * 100 : 0}%` }} /><i className="bar-write" style={{ width: `${summary?.request_count ? (summary.write_count ?? 0) / summary.request_count * 100 : 0}%` }} /><i className="bar-other" style={{ width: `${summary?.request_count ? (summary.other_count ?? 0) / summary.request_count * 100 : 0}%` }} /></div>
        <div className="composition-legend"><span><i className="legend-dot read-dot" />{t('read')} <b>{numberText(summary?.read_count, language)}</b></span><span><i className="legend-dot write-dot" />{t('write')} <b>{numberText(summary?.write_count, language)}</b></span><span><i className="legend-dot other-dot" />{t('other')} <b>{numberText(summary?.other_count, language)}</b></span></div>
      </section>
      <section className="panel burst-list-panel">
        <div className="burst-list-heading"><div><h2>{t('burstEvents')}</h2></div></div>
        
        <Paginator total={summary?.burst_count ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
        <TableScroller className="burst-table-scroll" t={t}><table className="burst-table"><thead><tr><SortableHeader column="burst_id" label={t('id')} sort={sort} onSort={changeSort} filtered={Boolean(/^\d+$/.test(filters.search.trim()))} filterLabel={t('filteredColumn')} /><SortableHeader column="start_time" label={t('startTime')} sort={sort} onSort={changeSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="actor_ip" label={t('actor')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="host" label={t('host')} sort={sort} onSort={changeSort} filtered={Boolean(filters.host || filters.known)} filterLabel={t('filteredColumn')} /><SortableHeader column="country" label={t('country')} sort={sort} onSort={changeSort} filtered={Boolean(filters.country)} filterLabel={t('filteredColumn')} /><SortableHeader column="duration" label={t('duration')} sort={sort} onSort={changeSort} /><SortableHeader column="requests" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="avg_count" label={t('avgPerSecond')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>
          {items.length ? items.map((burst) => <tr key={burst.burst_id}><td><button type="button" className="table-link primary-cell" onClick={() => onBurstSelect(burst.burst_id)} aria-label={`${t('viewBurstRequests')} #${burst.burst_id}`}>#{burst.burst_id}</button></td><td><span className="incident-time-cell"><strong>{requestDateTimeText(burst.start_time, language)}</strong><small>{incidentDurationText(burst.start_time, burst.end_time, language)}</small></span></td><td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={burst.actor_ip} t={t} /><strong className="primary-cell">{burst.actor_ip}</strong></span><small>{burst.provider || '—'} · {burst.asn || '—'}</small></span></td><td className={`host-cell${burst.known ? ' known-host-name' : ''}`}>{burst.host || '—'}</td><td><span className="actor-detail"><span className="country-cell"><span className="country-flag" title={burst.country || ''}>{countryFlag(burst.country)}</span>{burst.country || '—'}</span><small>{burst.city || '—'}</small></span></td><td>{secondsText((new Date(burst.end_time).getTime() - new Date(burst.start_time).getTime()) / 1000, language)}</td><td><span className="request-count">{numberText(burst.read_count + burst.write_count + burst.other_count, language)}</span></td><td><span className="rate-value">{numberText(burst.avg_count, language)}<small> {t('requestsPerSecond')}</small></span></td><td><span className="actor-row-actions"><button type="button" className="icon-button row-more" aria-label={t('viewBurstRequests')} title={t('viewBurstRequests')} onClick={() => onBurstSelect(burst.burst_id)}><ArrowUpRight size={15} /></button><button type="button" className="icon-button row-more actor-delete-button" aria-label={t('deleteBurst')} title={t('deleteBurst')} disabled={deletingBurst === burst.burst_id} onClick={() => void deleteBurst(burst.burst_id)}><Trash2 size={15} /></button></span></td></tr>) : <EmptyRows t={t} columns={9} />}
        </tbody></table></TableScroller>
        <Paginator total={summary?.burst_count ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
      </section>
    </>}
  </>
}

function ActorsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onActorSelect, pageSize, onPageSizeChange }: PaginatedPageProps & { sort: ActorSort; onSortChange: (sort: ActorSort) => void; filters: ActorFilters; onFiltersChange: (filters: ActorFilters) => void; onActorSelect: (ip: string) => void }) {
  const trends = useMetricTrends(range, 'actors', { search: filters.search.trim(), country: filters.country, country_exact: filters.country ? 'true' : '', protected_only: filters.protectedOnly ? 'true' : '' })
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState<ActorFilters>(filters)
  const [actorToDelete, setActorToDelete] = useState<ActorItem | null>(null)
  const [deletingActor, setDeletingActor] = useState(false)
  const [deleteActorError, setDeleteActorError] = useState('')
  const countryOptions = useApiData<ApiResult<{ country: string }>>(apiUrl('countries', range.query))
  const actorParams = Object.fromEntries(Object.entries({ search: filters.search.trim(), country: filters.country, country_exact: filters.country ? 'true' : '', protected_only: filters.protectedOnly ? 'true' : '', sort_by: sort.column, sort_order: sort.direction, limit: String(pageSize), offset: String(pageIndex * pageSize) }).filter(([, value]) => value))
  const result = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, actorParams))
  const newActors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { ...actorParams, limit: '1', offset: '0', new_only: 'true' }))
  const actors = result.data?.items ?? []
  const totalRequests = actors.reduce((sum, actor) => sum + actor.request_count, 0)
  const countries = new Set(actors.map((actor) => actor.country).filter(Boolean)).size
  const retry = () => { result.reload(); newActors.reload(); countryOptions.reload() }
  useEffect(() => setPageIndex(0), [range.query, filters.search, filters.country, filters.protectedOnly, sort])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { const empty = { ...defaultActorFilters }; setDraftFilters(empty); setPageIndex(0); onFiltersChange(empty) }
  const changeSort = (column: ActorSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  const deleteSelectedActor = async () => {
    if (!actorToDelete) return
    setDeletingActor(true)
    setDeleteActorError('')
    try {
      const response = await apiFetch(apiUrl(`actors/${actorToDelete.actor_id}`), { method: 'DELETE', headers: { Accept: 'application/json' } })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setActorToDelete(null)
      if (actors.length === 1 && pageIndex > 0) setPageIndex((value) => Math.max(0, value - 1))
      else result.reload()
      newActors.reload()
      countryOptions.reload()
      trends.reload()
    } catch (error) {
      console.error('Could not delete actor', error)
      setDeleteActorError(t('deleteActorFailed'))
    } finally {
      setDeletingActor(false)
    }
  }
  return <>
    <PageHeading title={t('actors')} subtitle={t('actorPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading || newActors.loading} error={result.error ?? newActors.error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls actor-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('actorSearchPlaceholder')} aria-label={t('actorSearchPlaceholder')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select country-filter"><Globe2 size={15} /><select aria-label={t('filterCountry')} value={draftFilters.country} onChange={(event) => setDraftFilters((value) => ({ ...value, country: event.target.value }))}><option value="">{t('allCountries')}</option>{countryOptions.data?.items.map((item) => <option key={item.country} value={item.country}>{countryFlag(item.country)} {item.country}</option>)}</select><span className="filter-select-value">{draftFilters.country && <span className="country-flag">{countryFlag(draftFilters.country)}</span>}{draftFilters.country || t('allCountries')}</span><ChevronDown size={13} /></label><label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.protectedOnly} onChange={(event) => setDraftFilters((value) => ({ ...value, protectedOnly: event.target.checked }))} /><span>{t('protectedIpsOnly')}</span></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !newActors.loading && !result.error && !newActors.error && <>
      <div className="metric-grid"><MetricCard t={t} language={language} label={t('uniqueActors')} value={numberText(result.data?.total, language)} icon={Users} iconClass="violet" trend={trends.data?.metrics.actor_count} trendLoading={trends.loading} trendAbsoluteUnit={t('actors')} /><MetricCard t={t} language={language} label={t('newActors')} value={numberText(newActors.data?.total, language)} icon={ArrowUpRight} iconClass="blue" trend={trends.data?.metrics.new_actor_count} trendLoading={trends.loading} trendAbsoluteUnit={t('actors')} /><MetricCard t={t} language={language} label={t('countriesSeen')} value={numberText(trends.data?.metrics.country_count?.current ?? countries, language)} icon={Globe2} iconClass="green" trend={trends.data?.metrics.country_count} trendLoading={trends.loading} trendAbsoluteUnit={t('countries')} /><MetricCard t={t} language={language} label={t('avgRequestsActor')} value={numberText(trends.data?.metrics.avg_requests_per_actor?.current ?? (actors.length ? totalRequests / actors.length : 0), language)} icon={Activity} iconClass="amber" trend={trends.data?.metrics.avg_requests_per_actor} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsPerActor')} trendAbsoluteDecimals={1} /></div>
      <div className="panel data-list-panel"><ListHeading title={t('actors')} />
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
        <TableScroller t={t}><table className="actor-table"><thead><tr><SortableHeader column="ip" label={t('ipAddress')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="country" label={t('location')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.country)} filterLabel={t('filteredColumn')} /><SortableHeader column="first_time" label={t('firstSeen')} sort={sort} onSort={changeSort} /><SortableHeader column="last_time" label={t('lastSeen')} sort={sort} onSort={changeSort} /><SortableHeader column="request_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{actors.length ? actors.map((actor) => <tr key={actor.actor_id}><td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={actor.ip} t={t} /><button type="button" className="table-link primary-cell" onClick={() => onActorSelect(actor.ip)}>{actor.ip}</button></span></span></td><td><ActorMetadata {...actor} /></td><td>{dateText(actor.first_time, language)}</td><td>{dateText(actor.last_time, language)}</td><td><span className="request-count">{numberText(actor.request_count, language)}</span></td><td><span className="actor-row-actions"><button type="button" className="icon-button row-more" aria-label={t('viewActorRequests')} title={t('viewActorRequests')} onClick={() => onActorSelect(actor.ip)}><ArrowUpRight size={15} /></button><button type="button" className="icon-button row-more actor-delete-button" aria-label={t('deleteActor')} title={t('deleteActor')} onClick={() => { setDeleteActorError(''); setActorToDelete(actor) }}><Trash2 size={15} /></button></span></td></tr>) : <EmptyRows t={t} columns={6} />}</tbody></table></TableScroller>
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
      </div>
    </>}
    {actorToDelete && <div className="actor-delete-backdrop"><section className="actor-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="actor-delete-title"><h2 id="actor-delete-title">{t('deleteActor')}</h2><p>{t('confirmDeleteActor').replace('{ip}', actorToDelete.ip).replace('{requests}', numberText(actorToDelete.total_request_count, language)).replace('{bursts}', numberText(actorToDelete.burst_count, language))}</p><dl className="actor-delete-details"><div><dt>{t('provider')}</dt><dd>{actorToDelete.provider || '—'}</dd></div><div><dt>{t('asn')}</dt><dd>{actorToDelete.asn || '—'}</dd></div><div><dt>{t('city')}</dt><dd>{actorToDelete.city || '—'}</dd></div><div><dt>{t('country')}</dt><dd><span className="country-flag" title={actorToDelete.country || ''}>{countryFlag(actorToDelete.country)}</span>{actorToDelete.country || '—'}</dd></div></dl><p className="actor-delete-warning">{t('deleteActorIrreversible')}</p>{deleteActorError && <p className="actor-delete-error" role="alert">{deleteActorError}</p>}<div className="actor-delete-actions"><button type="button" className="filter-button" disabled={deletingActor} onClick={() => setActorToDelete(null)}>{t('cancel')}</button><button type="button" className="primary-button actor-delete-confirm" disabled={deletingActor} onClick={deleteSelectedActor}><Trash2 size={15} />{deletingActor ? t('deletingActor') : t('deleteActor')}</button></div></section></div>}
  </>
}

function HostsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onHostSelect, pageSize, onPageSizeChange }: PaginatedPageProps & { sort: HostSort; onSortChange: (sort: HostSort) => void; filters: HostFilters; onFiltersChange: (filters: HostFilters) => void; onHostSelect: (host: string) => void }) {
  const trends = useMetricTrends(range, 'hosts', { search: filters.search.trim(), known: filters.known })
  const [pageIndex, setPageIndex] = useState(0)
  const [draftSearch, setDraftSearch] = useState(filters.search)
  const hostParams = Object.fromEntries(Object.entries({ host: filters.search.trim(), known: filters.known, sort_by: sort.column, sort_order: sort.direction }).filter(([, value]) => value))
  const result = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query, hostParams))
  const hosts = result.data?.items ?? []
  const visibleHosts = hosts.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
  const total = hosts.reduce((sum, host) => sum + host.total_count, 0)
  const https = hosts.reduce((sum, host) => sum + host.https_count, 0)
  const httpsShare = total ? https / total * 100 : 0
  const topHost = [...hosts].sort((a, b) => b.total_count - a.total_count)[0]
  useEffect(() => setPageIndex(0), [range.query, filters.search, filters.known, sort])
  useEffect(() => setDraftSearch(filters.search), [filters.search])
  const [draftKnown, setDraftKnown] = useState<HostFilters['known']>(filters.known)
  useEffect(() => setDraftKnown(filters.known), [filters.known])
  const applyFilter = () => { setPageIndex(0); onFiltersChange({ search: draftSearch, known: draftKnown }) }
  const resetFilter = () => { setDraftSearch(''); setDraftKnown(''); setPageIndex(0); onFiltersChange({ ...defaultHostFilters }) }
  const changeSort = (column: HostSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('hosts')} subtitle={t('hostPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading} error={result.error} retry={result.reload} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftSearch} placeholder={t('filterHost')} aria-label={t('filterHost')} onChange={(event) => setDraftSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applyFilter() }} /></label><label className="filter-select"><Globe2 size={15} /><select aria-label={t('hostOwnership')} value={draftKnown} onChange={(event) => setDraftKnown(event.target.value as HostFilters['known'])}><option value="">{t('allHosts')}</option><option value="own">{t('ownHosts')}</option><option value="foreign">{t('foreignHosts')}</option></select><span className="filter-select-value">{draftKnown === 'own' ? t('ownHosts') : draftKnown === 'foreign' ? t('foreignHosts') : t('allHosts')}</span><ChevronDown size={13} /></label><button type="button" className="filter-button" onClick={resetFilter}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilter}>{t('applyFilters')}</button></div>
    {!result.loading && !result.error && <>
      <div className="metric-grid"><MetricCard t={t} language={language} label={t('totalHosts')} value={numberText(hosts.length, language)} icon={Globe2} iconClass="blue" trend={trends.data?.metrics.host_count} trendLoading={trends.loading} trendAbsoluteUnit={t('hosts')} /><MetricCard t={t} language={language} label={t('totalRequests')} value={numberText(total, language)} icon={Network} iconClass="green" trend={trends.data?.metrics.request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} /><MetricCard t={t} language={language} label={t('httpsShare')} value={`${new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(httpsShare)}%`} icon={ShieldAlert} iconClass="violet" trend={trends.data?.metrics.https_share} trendLoading={trends.loading} trendAbsoluteUnit={t('percentagePoints')} trendAbsoluteDecimals={1} /><MetricCard t={t} language={language} label={t('topHost')} value={topHost?.host ?? '—'} icon={Activity} iconClass="amber" caption={t('trafficShare')} trend={trends.data?.metrics.top_host_request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} /></div>
      <div className="panel data-list-panel"><ListHeading title={t('hosts')} />
        <Paginator total={hosts.length} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
        <TableScroller t={t}><table className="host-table"><thead><tr><SortableHeader column="host" label={t('hostName')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.known)} filterLabel={t('filteredColumn')} /><SortableHeader column="total_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="read_count" label={t('read')} sort={sort} onSort={changeSort} /><SortableHeader column="write_count" label={t('write')} sort={sort} onSort={changeSort} /><SortableHeader column="other_count" label={t('other')} sort={sort} onSort={changeSort} /><SortableHeader column="https_count" label={t('schemeSplit')} sort={sort} onSort={changeSort} /><SortableHeader column="https_share" label={t('httpsShare')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{visibleHosts.length ? visibleHosts.map((host) => { const hostTotal = host.total_count || 0; const share = hostTotal ? host.https_count / hostTotal * 100 : 0; return <tr key={host.host_id}><td><button type="button" className={`table-link primary-cell${host.known ? ' known-host-name' : ''}`} onClick={() => onHostSelect(host.host)}>{host.host}</button></td><td><span className="request-count">{numberText(host.total_count, language)}</span></td><td>{numberText(host.read_count, language)}</td><td>{numberText(host.write_count, language)}</td><td>{numberText(host.other_count, language)}</td><td><span className="scheme-chips"><i>HTTPS {numberText(host.https_count, language)}</i><i>HTTP {numberText(host.http_count, language)}</i></span></td><td><span className="share-cell"><span><i style={{ width: `${share}%` }} /></span>{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 0 }).format(share)}%</span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewHostRequests')} title={t('viewHostRequests')} onClick={() => onHostSelect(host.host)}><ArrowUpRight size={15} /></button></td></tr> }) : <EmptyRows t={t} columns={8} />}</tbody></table></TableScroller>
        <Paginator total={hosts.length} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
      </div>
    </>}
  </>
}

function CategoriesPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onCategorySelect, pageSize, onPageSizeChange }: PaginatedPageProps & { sort: CategorySort; onSortChange: (sort: CategorySort) => void; filters: CategoryFilters; onFiltersChange: (filters: CategoryFilters) => void; onCategorySelect: (category: string) => void }) {
  const trends = useMetricTrends(range, 'categories', { search: filters.search.trim() })
  const [pageIndex, setPageIndex] = useState(0)
  const [draftSearch, setDraftSearch] = useState(filters.search)
  const params = Object.fromEntries(Object.entries({ category: filters.search.trim(), sort_by: sort.column, sort_order: sort.direction }).filter(([, value]) => value))
  const result = useApiData<ApiResult<CategoryItem>>(apiUrl('categories', range.query, params))
  const categories = result.data?.items ?? []
  const total = result.data?.summary?.request_count ?? 0
  const https = result.data?.summary?.https_count ?? 0
  const top = [...categories].sort((a, b) => b.total_count - a.total_count)[0]
  const visibleCategories = categories.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize)
  useEffect(() => setPageIndex(0), [range.query, filters.search, sort])
  useEffect(() => setDraftSearch(filters.search), [filters.search])
  const applyFilter = () => { setPageIndex(0); onFiltersChange({ search: draftSearch }) }
  const resetFilter = () => { setDraftSearch(''); setPageIndex(0); onFiltersChange({ ...defaultCategoryFilters }) }
  const changeSort = (column: CategorySortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('categories')} subtitle={t('categoryPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading} error={result.error} retry={result.reload} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftSearch} placeholder={t('filterCategory')} aria-label={t('filterCategory')} onChange={(event) => setDraftSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applyFilter() }} /></label><button type="button" className="filter-button" onClick={resetFilter}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilter}>{t('applyFilters')}</button></div>
    {!result.loading && !result.error && <>
      <div className="metric-grid"><MetricCard t={t} language={language} label={t('activeCategories')} value={numberText(categories.length, language)} icon={Blocks} iconClass="blue" trend={trends.data?.metrics.category_count} trendLoading={trends.loading} trendAbsoluteUnit={t('categories')} /><MetricCard t={t} language={language} label={t('totalRequests')} value={numberText(total, language)} icon={Activity} iconClass="green" trend={trends.data?.metrics.request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} /><MetricCard t={t} language={language} label={t('topCategory')} value={top?.category_name ?? '—'} icon={ShieldAlert} iconClass="amber" caption={top ? `${numberText(top.total_count, language)} ${t('requestsLabel')}` : t('noResults')} trend={trends.data?.metrics.top_category_request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} /><MetricCard t={t} language={language} label={t('httpsShare')} value={`${new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(total ? https / total * 100 : 0)}%`} icon={Globe2} iconClass="violet" trend={trends.data?.metrics.https_share} trendLoading={trends.loading} trendAbsoluteUnit={t('percentagePoints')} trendAbsoluteDecimals={1} /></div>
      <div className="panel data-list-panel"><ListHeading title={t('categories')} />
        <Paginator total={categories.length} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
        <TableScroller t={t}><table className="category-table"><thead><tr><SortableHeader column="category_name" label={t('categoryName')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="total_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="read_count" label={t('read')} sort={sort} onSort={changeSort} /><SortableHeader column="write_count" label={t('write')} sort={sort} onSort={changeSort} /><SortableHeader column="other_count" label={t('other')} sort={sort} onSort={changeSort} /><SortableHeader column="traffic_share" label={t('trafficShare')} sort={sort} onSort={changeSort} /><SortableHeader column="https_share" label={t('schemeSplit')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{visibleCategories.length ? visibleCategories.map((category) => { const share = total ? category.total_count / total * 100 : 0; const schemeTotal = category.http_count + category.https_count + category.other_scheme_count; const secure = schemeTotal ? category.https_count / schemeTotal * 100 : 0; return <tr key={category.category_id}><td><button type="button" className="table-link primary-cell" onClick={() => onCategorySelect(category.category_name)}>{category.category_name}</button></td><td><span className="request-count">{numberText(category.total_count, language)}</span></td><td>{numberText(category.read_count, language)}</td><td>{numberText(category.write_count, language)}</td><td>{numberText(category.other_count, language)}</td><td><span className="share-cell"><span><i style={{ width: `${share}%` }} /></span>{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(share)}%</span></td><td><span className="https-text">HTTPS</span> <span className="scheme-muted">{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 0 }).format(secure)}%</span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewCategoryRequests')} title={t('viewCategoryRequests')} onClick={() => onCategorySelect(category.category_name)}><ArrowUpRight size={15} /></button></td></tr> }) : <EmptyRows t={t} columns={8} />}</tbody></table></TableScroller>
        <Paginator total={categories.length} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
      </div>
    </>}
  </>
}

function RequestsPage({ t, language, range, onRangeChange, lastImport, burstId, incidentId, incidentContext, burstExtreme, statisticFilter, actorIp, host, category, path, trafficBucket, onTrafficBucketClear, onIncidentClear, filters, onFiltersChange, sort, onSortChange, onBurstClear, onBurstExtremeClear, onStatisticFilterClear, onActorClear, onHostClear, onCategoryClear, onPathClear, pageSize, onPageSizeChange }: PaginatedPageProps & { burstId: number | null; incidentId: number | null; incidentContext: NotificationIncident | null; burstExtreme: BurstExtreme | null; statisticFilter: StatisticRequestFilter | null; onStatisticFilterClear: () => void; actorIp: string | null; host: string | null; category: string | null; path: string | null; trafficBucket: TrafficBucket | null; onTrafficBucketClear: () => void; onIncidentClear: () => void; filters: RequestFilters; onFiltersChange: (filters: RequestFilters) => void; sort: RequestSort; onSortChange: (sort: RequestSort) => void; onBurstClear: () => void; onBurstExtremeClear: () => void; onActorClear: () => void; onHostClear: () => void; onCategoryClear: () => void; onPathClear: () => void }) {
  const requestRange: TimeRange = trafficBucket ? { from: new Date(trafficBucket.from), to: new Date(trafficBucket.to), preset: 'custom', query: new URLSearchParams({ from: trafficBucket.from, to: trafficBucket.to }).toString() } : range
  const burstDetails = useApiData<BurstItem>(burstId == null ? null : apiUrl(`bursts/${burstId}`), false)
  const activeBurst = burstDetails.data?.burst_id === burstId ? burstDetails.data : null
  const actorDetails = useApiData<PagedResponse<ActorItem>>(actorIp == null ? null : apiUrl('actors', requestRange.query, { ip: actorIp, ip_exact: 'true', limit: '1', offset: '0' }), false)
  const activeActor = actorDetails.data?.items.find((item) => item.ip === actorIp) ?? null
  const trends = useMetricTrends(requestRange, 'requests', { incident_id: incidentId == null ? '' : String(incidentId), search: filters.search.trim(), status_class: filters.status, without_burst: filters.withoutBurst ? 'true' : '', provider: statisticFilter?.field === 'provider' ? statisticFilter.value : '', provider_exact: statisticFilter?.field === 'provider' ? 'true' : '', country: statisticFilter?.field === 'country' ? statisticFilter.value : '', country_exact: statisticFilter?.field === 'country' ? 'true' : '', burst_id: burstId == null ? '' : String(burstId), burst_extreme: burstExtreme ?? '', actor_ip: actorIp ?? '', actor_ip_exact: actorIp ? 'true' : '', host: host ?? '', host_exact: host ? 'true' : '', category: category ?? '', category_exact: category ? 'true' : '', path: path ?? '', path_exact: path ? 'true' : '' })
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState(filters)
  const requestFilter: Record<string, string> = { ...(incidentId == null ? {} : { incident_id: String(incidentId) }), ...(burstId == null ? {} : { burst_id: String(burstId) }), ...(burstExtreme == null ? {} : { burst_extreme: burstExtreme }), ...(statisticFilter?.field === 'provider' ? { provider: statisticFilter.value, provider_exact: 'true' } : {}), ...(statisticFilter?.field === 'country' ? { country: statisticFilter.value, country_exact: 'true' } : {}), ...(actorIp == null ? {} : { actor: actorIp, actor_exact: 'true' }), ...(host == null ? {} : { host, host_exact: 'true' }), ...(category == null ? {} : { category, category_exact: 'true' }), ...(path == null ? {} : { path, path_exact: 'true' }), ...(filters.search.trim() ? { search: filters.search.trim() } : {}), ...(filters.status ? { status_class: filters.status } : {}), ...(filters.withoutBurst ? { without_burst: 'true' } : {}), sort_by: sort.column, sort_order: sort.direction }
  const countFilter: Record<string, string> = { ...(incidentId == null ? {} : { incident_id: String(incidentId) }), ...(burstId == null ? {} : { burst_id: String(burstId) }), ...(burstExtreme == null ? {} : { burst_extreme: burstExtreme }), ...(statisticFilter?.field === 'provider' ? { provider: statisticFilter.value, provider_exact: 'true' } : {}), ...(statisticFilter?.field === 'country' ? { country: statisticFilter.value, country_exact: 'true' } : {}), ...(actorIp == null ? {} : { actor_ip: actorIp, actor_ip_exact: 'true' }), ...(host == null ? {} : { host, host_exact: 'true' }), ...(category == null ? {} : { category, category_exact: 'true' }), ...(path == null ? {} : { path, path_exact: 'true' }), ...(filters.search.trim() ? { search: filters.search.trim() } : {}), ...(filters.status ? { status_class: filters.status } : {}), ...(filters.withoutBurst ? { without_burst: 'true' } : {}) }
  const result = useApiData<RequestPageResponse>(apiUrl('requests', requestRange.query, { limit: String(pageSize), offset: String(pageIndex * pageSize), ...requestFilter }))
  const counts = useApiData<ApiResult<CountItem>>(apiUrl('request_counts', requestRange.query, { bars: '1', ...countFilter }))
  const requests = result.data?.items ?? []
  const countRow = counts.data?.items[0]
  const total = countRow ? countRow.read_count + countRow.write_count + countRow.other_count : 0
  const hideActorColumn = burstId != null || actorIp != null || incidentId != null
  const hideHostColumn = burstId != null || host != null
  const requestTableClass = `requests-table${burstId != null ? ' has-burst-filter' : ''}${actorIp != null ? ' has-actor-filter' : ''}${host != null ? ' has-host-filter' : ''}`
  const errorCount = requests.filter((request) => request.downstream_status >= 400).length
  const retry = () => { result.reload(); counts.reload(); if (burstId != null) burstDetails.reload(); if (actorIp != null) actorDetails.reload() }
  useEffect(() => setPageIndex(0), [requestRange.query, burstId, incidentId, burstExtreme, statisticFilter, actorIp, host, category, path, filters, sort])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { setDraftFilters({ ...defaultRequestFilters }); setPageIndex(0); onFiltersChange({ ...defaultRequestFilters }); if (incidentId != null) onIncidentClear() }
  const changeSort = (column: RequestSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('requests')} subtitle={t('requestPageSubtitle')} t={t} language={language} range={requestRange} onRangeChange={(nextRange) => { if (incidentId != null) onIncidentClear(); onRangeChange(nextRange) }} lastImport={lastImport} />
    <PageDataState loading={result.loading || counts.loading || (burstId != null && burstDetails.loading) || (actorIp != null && actorDetails.loading)} error={result.error ?? counts.error ?? burstDetails.error ?? actorDetails.error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls request-filter-controls"><div className="request-filter-notices">{incidentId != null && <div className="burst-filter-notice request-burst-notice"><div className="request-burst-info"><strong className="request-burst-title">{t('filteredByIncident')} #{incidentId}</strong>{incidentContext && <div className="request-burst-details"><span>{t('incidentType')}: <strong>{incidentTypeText(incidentContext, t)}</strong></span><span>{t('incidentStart')}: <strong>{requestDateTimeText(incidentContext.first_seen, language)}</strong></span><span>{t('duration')}: <strong>{incidentDurationText(incidentContext.first_seen, incidentContext.last_seen, language)}</strong></span><span>{t('ipAddress')}: <strong>{incidentContext.actor_ip}</strong></span><ActorMetadata {...incidentContext} /><span>{t('host')}: <strong>{incidentContext.summary?.host_count > 1 ? t('multipleHosts') : incidentContext.host || '—'}</strong></span></div>}</div><button type="button" onClick={onIncidentClear}>{t('clearFilter')}</button></div>}{trafficBucket != null && incidentId == null && <div className="burst-filter-notice"><span>{t('filteredByTrafficBucket')} <strong>{dateText(trafficBucket.from, language)} – {dateText(trafficBucket.to, language)}</strong></span><button type="button" onClick={onTrafficBucketClear}>{t('clearFilter')}</button></div>}{trafficBucket?.source === 'honeypot-group' && <div className="burst-filter-notice honeypot-request-filter-note">{t('honeypotRequestFilterNote')}</div>}{burstId != null && <div className="burst-filter-notice request-burst-notice"><div className="request-burst-info"><strong className="request-burst-title">{t('filteredByBurst')} #{burstId}</strong>{activeBurst && <div className="request-burst-details"><span>{t('ipAddress')}: <strong>{activeBurst.actor_ip}</strong></span><ActorMetadata {...activeBurst} /><span>{t('host')}: <strong>{activeBurst.host || '—'}</strong></span></div>}</div><button type="button" onClick={onBurstClear}>{t('clearFilter')}</button></div>}{burstExtreme != null && <div className="burst-filter-notice"><span>{t('filteredByBurstExtreme')} <strong>{t(burstExtreme === 'min_requests' ? 'minimumRequestsPerBurst' : burstExtreme === 'max_requests' ? 'maximumRequestsPerBurst' : burstExtreme === 'min_duration' ? 'minimumBurstDuration' : 'maximumBurstDuration')}</strong>{result.data?.burst_extreme_value != null && <small> · {burstExtreme.endsWith('requests') ? `${numberText(result.data.burst_extreme_value, language)} ${t('requestsPerBurstUnit')}` : preciseSecondsText(result.data.burst_extreme_value, language)}</small>}{result.data?.matching_burst_count != null && <small> · {numberText(result.data.matching_burst_count, language)} {t('matchingBursts')}</small>}</span><button type="button" onClick={onBurstExtremeClear}>{t('clearFilter')}</button></div>}{statisticFilter != null && <div className="burst-filter-notice"><span>{t('filteredByStatistic')} <strong>{t(statisticFilter.field)}: </strong>{statisticFilter.field === 'country' && <span className="country-flag" title={statisticFilter.value}>{countryFlag(statisticFilter.value)}</span>}<strong>{statisticFilter.value}</strong></span><button type="button" onClick={onStatisticFilterClear}>{t('clearFilter')}</button></div>}{actorIp != null && incidentId == null && <div className="burst-filter-notice request-burst-notice"><div className="request-burst-info"><strong className="request-burst-title">{t('filteredByActor')}</strong><div className="request-burst-details"><span>{t('ipAddress')}: <strong>{activeActor?.ip ?? actorIp}</strong></span><ActorMetadata provider={activeActor?.provider} asn={activeActor?.asn} country={activeActor?.country} city={activeActor?.city} /></div></div><button type="button" onClick={onActorClear}>{t('clearFilter')}</button></div>}{host != null && <div className="burst-filter-notice"><span>{t('filteredByHost')} <strong>{host}</strong></span><button type="button" onClick={onHostClear}>{t('clearFilter')}</button></div>}{category != null && <div className="burst-filter-notice"><span>{t('filteredByCategory')} <strong>{category}</strong></span><button type="button" onClick={onCategoryClear}>{t('clearFilter')}</button></div>}{path != null && <div className="burst-filter-notice"><span>{t('filteredByPath')} <strong>{path}</strong></span><button type="button" onClick={onPathClear}>{t('clearFilter')}</button></div>}</div><label className="filter-search request-search"><Search size={15} /><input type="search" name="request-filter-query" autoComplete="off" autoCapitalize="none" autoCorrect="off" spellCheck={false} value={draftFilters.search} placeholder={t('searchRequests')} aria-label={t('searchRequests')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select"><select aria-label={t('responseStatus')} value={draftFilters.status} onChange={(event) => setDraftFilters((value) => ({ ...value, status: event.target.value as RequestFilters['status'] }))}><option value="">{t('allStatuses')}</option><option value="2xx">2xx · {t('statusSuccess')}</option><option value="3xx">3xx · {t('statusRedirect')}</option><option value="4xx">4xx · {t('statusClientError')}</option><option value="5xx">5xx · {t('statusServerError')}</option></select><span className="filter-select-value">{draftFilters.status ? `${draftFilters.status} · ${draftFilters.status === '2xx' ? t('statusSuccess') : draftFilters.status === '3xx' ? t('statusRedirect') : draftFilters.status === '4xx' ? t('statusClientError') : t('statusServerError')}` : t('allStatuses')}</span><ChevronDown size={13} /></label><label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.withoutBurst} onChange={(event) => setDraftFilters((value) => ({ ...value, withoutBurst: event.target.checked }))} /><span>{t('onlyRequestsWithoutBurst')}</span></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !counts.loading && !result.error && !counts.error && <>
      <div className={`metric-grid request-metrics${burstId != null ? ' has-burst' : ''}`}><MetricCard t={t} language={language} label={t('totalRequests')} value={numberText(result.data?.total ?? total, language)} icon={Activity} iconClass="blue" trend={trends.data?.metrics.request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('requestsLabel')} /><MetricCard t={t} language={language} label={t('errorResponses')} value={numberText(trends.data?.metrics.error_request_count?.current ?? errorCount, language)} icon={ShieldAlert} iconClass="amber" trend={trends.data?.metrics.error_request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('errorResponses')} /><MetricCard t={t} language={language} label={t('writeRequests')} value={numberText(countRow?.write_count, language)} icon={ArrowUpRight} iconClass="violet" trend={trends.data?.metrics.write_request_count} trendLoading={trends.loading} trendAbsoluteUnit={t('writeRequests')} />{burstId != null && <div className="panel metric-card burst-context-card"><div className="metric-top"><span>{t('burstDetails')} · #{burstId}</span><span className="metric-icon amber"><Activity size={17} /></span></div><div className="metric-bottom"><strong className="metric-value-compact">{activeBurst ? dateText(activeBurst.start_time, language) : '…'}</strong></div><div className="metric-foot"><div className="metric-caption">{t('duration')}: {activeBurst ? preciseSecondsText((new Date(activeBurst.end_time).getTime() - new Date(activeBurst.start_time).getTime()) / 1000, language) : '…'}</div><div className="metric-trend steady"><Activity size={13} /><span>{activeBurst ? `${decimalText(activeBurst.avg_count, language)} ${t('requestsPerSecond')}` : '…'}</span></div></div></div>}</div>
      <div className="panel data-list-panel requests-list-panel"><ListHeading title={t('requests')} />
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
        <TableScroller t={t}><table className={requestTableClass}><thead><tr><SortableHeader column="start_utc" label={t('startTime')} sort={sort} onSort={changeSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="request_method" label={t('method')} sort={sort} onSort={changeSort} /><SortableHeader column="request_path" label={t('requestPath')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || category != null || path != null)} filterLabel={t('filteredColumn')} /><SortableHeader column="host" label={t('host')} sort={sort} onSort={changeSort} className="request-host-col" filtered={Boolean(filters.search.trim() || host != null)} filterLabel={t('filteredColumn')} hidden={hideHostColumn} /><SortableHeader column="downstream_status" label={t('responseStatus')} sort={sort} onSort={changeSort} className="request-status-col" filtered={Boolean(filters.status)} filterLabel={t('filteredColumn')} />{!hideActorColumn && <SortableHeader column="actor_ip" label={t('actor')} sort={sort} onSort={changeSort} className="request-actor-col" filtered={Boolean(filters.search.trim() || actorIp != null)} filterLabel={t('filteredColumn')} />}<SortableHeader column="user_agent" label={t('userAgent')} sort={sort} onSort={changeSort} className="request-user-agent-col" /><SortableHeader column="duration" label={t('durationShort')} sort={sort} onSort={changeSort} /><SortableHeader column="downstream_content_size" label={t('responseSize')} sort={sort} onSort={changeSort} /><SortableHeader column="request_content_size" label={t('requestBodySize')} sort={sort} onSort={changeSort} /></tr></thead><tbody>{requests.length ? requests.map((request) => <tr key={request.request_id}><td><span className="incident-time-cell"><strong>{requestDateTimeText(request.start_utc, language)} . {timestampMillisText(request.start_utc, language)}</strong><small>{elapsedDurationText(request.duration / 1_000_000, language)}</small></span></td><td><span className="method-cell">{request.request_scheme.toLowerCase() === 'https' && <span className="https-lock" title="HTTPS" aria-label="HTTPS"><LockKeyhole size={13} /></span>}{request.request_scheme.toLowerCase() === 'http' && <span className="http-lock" title="HTTP" aria-label="HTTP"><LockOpen size={13} /></span>}<span className={`method-badge ${request.request_method.toLowerCase()}`}>{request.request_method}</span></span></td><td><span className="request-path-detail"><code className="path-cell">{request.request_path}</code>{category == null && request.categories && <small>{request.categories}</small>}</span></td>{!hideHostColumn && <td className={`host-cell request-host-col${request.host_known ? ' known-host-name' : ''}`}>{request.host || '—'}</td>}<td className="request-status-col"><span className={`response-code ${request.downstream_status < 400 ? 'response-success' : ''}`}>{request.downstream_status}</span></td>{!hideActorColumn && <td className="request-actor-col"><span className="actor-detail"><strong className="primary-cell">{request.actor_ip}</strong><ActorMetadata {...request} /></span></td>}<td className="request-user-agent-col"><span className="user-agent-cell">{request.user_agent || '—'}</span></td><td>{numberText(request.duration / 1_000_000, language)} ms</td><td>{numberText(request.downstream_content_size, language)} B</td><td>{request.request_content_size == null ? '—' : `${numberText(request.request_content_size, language)} B`}</td></tr>) : <EmptyRows t={t} columns={10 - Number(hideActorColumn) - Number(hideHostColumn)} />}</tbody></table></TableScroller>
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={setPageIndex} onPageSizeChange={onPageSizeChange} t={t} language={language} />
      </div>
    </>}
  </>
}

function PageHeading({ title, subtitle, t, range, onRangeChange, language, lastImport }: { title: string; subtitle: string; t: (key: MessageKey) => string; range: TimeRange; onRangeChange: (range: TimeRange) => void; language: Language; lastImport: string | null | undefined }) {
  return <div className="page-heading"><div>{range.preset === 'last24h' && <div className="live-monitoring"><i />{t('liveMonitoring')} · {t('lastImport')}: {timeText(lastImport, language)}</div>}<h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions"><DateRangePicker range={range} onChange={onRangeChange} t={t} language={language} /></div></div>
}

function DateRangePicker({ range, onChange, t, language }: { range: TimeRange; onChange: (range: TimeRange) => void; t: (key: MessageKey) => string; language: Language }) {
  const [open, setOpen] = useState(false)
  const [start, setStart] = useState(() => localDateTimeInput(range.from))
  const [end, setEnd] = useState(() => localDateTimeInput(range.to))
  const container = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => { if (!container.current?.contains(event.target as Node)) setOpen(false) }
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => { document.removeEventListener('pointerdown', onPointerDown); document.removeEventListener('keydown', onKeyDown) }
  }, [open])
  useEffect(() => {
    setStart(localDateTimeInput(range.from))
    setEnd(localDateTimeInput(range.to))
  }, [range])
  const presets: [RangePreset, MessageKey][] = [['last24h', 'last24h'], ['today', 'todayRange'], ['yesterday', 'yesterdayRange'], ['last6h', 'last6h'], ['last7d', 'last7d'], ['last30d', 'last30d'], ['last90d', 'last90d']]
  const commitPreset = (preset: RangePreset) => { onChange(makeRange(preset)); setOpen(false) }
  const applyCustom = () => {
    if (!start || !end || start >= end) return
    onChange(makeRange('custom', start, end))
    setOpen(false)
  }
  return <div className="date-range-picker" ref={container}>
    <button type="button" className="select-button date-range-trigger" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((value) => !value)}><CalendarDays size={16} /><span>{rangeLabel(range, t, language)}</span><ChevronDown size={14} /></button>
    {open && <div className="date-range-popover" role="dialog" aria-label={t('dateRange')}>
      <div className="range-presets">{presets.map(([preset, label]) => <button type="button" key={preset} className="range-preset" onClick={() => commitPreset(preset)}>{t(label)}</button>)}</div>
      <div className="range-custom"><strong>{t('customRange')}</strong><label>{t('startDate')}<input type="datetime-local" step="60" value={start} max={end || undefined} onChange={(event) => setStart(event.target.value)} /></label><label>{t('endDate')}<input type="datetime-local" step="60" value={end} min={start || undefined} onChange={(event) => setEnd(event.target.value)} /></label><button type="button" className="primary-button range-apply" disabled={!start || !end || start >= end} onClick={applyCustom}>{t('applyRange')}</button></div>
    </div>}
  </div>
}

function ListHeading({ title }: { title: string }) {
  return <div className="burst-list-heading"><div><h2>{title}</h2></div></div>
}

function TableScroller({ children, className = '', t }: { children: ReactNode; className?: string; t: (key: MessageKey) => string }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const leftCueRef = useRef<HTMLButtonElement>(null)
  const rightCueRef = useRef<HTMLButtonElement>(null)
  const cuesPinnedRef = useRef(false)
  useLayoutEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const update = (reflow = false) => {
      const frame = element.parentElement
      if (!frame) return
      const frameRect = frame.getBoundingClientRect()
      const headerRow = element.querySelector('thead tr')
      const headerRect = headerRow?.getBoundingClientRect()
      const buttonRadius = window.matchMedia('(max-width: 560px)').matches ? 10 : 11
      const minTop = Math.max(frameRect.top + buttonRadius, buttonRadius + 4)
      const maxTop = Math.min(frameRect.bottom - buttonRadius, window.innerHeight - buttonRadius - 4)
      const visible = frameRect.bottom > 0 && frameRect.top < window.innerHeight && minTop <= maxTop
      const headerBottom = headerRect?.bottom ?? frameRect.top + buttonRadius
      if (headerRect) {
        if (cuesPinnedRef.current ? headerRect.top >= 4 : headerRect.top <= 0) cuesPinnedRef.current = !cuesPinnedRef.current
      }
      const pinned = cuesPinnedRef.current
      const top = Math.max(minTop, Math.min(maxTop, headerBottom))
      const absoluteTop = headerBottom - frameRect.top
      const canScrollLeft = element.scrollLeft > 1
      const canScrollRight = element.scrollLeft + element.clientWidth < element.scrollWidth - 1
      const leftCue = leftCueRef.current
      const rightCue = rightCueRef.current
      if (leftCue) {
        leftCue.style.position = pinned ? 'fixed' : 'absolute'
        if (pinned) {
          leftCue.style.top = `${top}px`
          leftCue.style.left = `${Math.max(4, frameRect.left + 3)}px`
        } else {
          leftCue.style.removeProperty('left')
          if (headerRect && (reflow || leftCue.dataset.position !== 'absolute')) leftCue.style.top = `${absoluteTop}px`
        }
        leftCue.style.display = visible && canScrollLeft ? 'grid' : 'none'
        leftCue.dataset.position = pinned ? 'fixed' : 'absolute'
      }
      if (rightCue) {
        rightCue.style.position = pinned ? 'fixed' : 'absolute'
        if (pinned) {
          rightCue.style.top = `${top}px`
          rightCue.style.right = `${Math.max(4, window.innerWidth - frameRect.right + 3)}px`
        } else {
          rightCue.style.removeProperty('right')
          if (headerRect && (reflow || rightCue.dataset.position !== 'absolute')) rightCue.style.top = `${absoluteTop}px`
        }
        rightCue.style.display = visible && canScrollRight ? 'grid' : 'none'
        rightCue.dataset.position = pinned ? 'fixed' : 'absolute'
      }
    }
    update(true)
    const onScroll = () => update()
    element.addEventListener('scroll', onScroll, { passive: true })
    const onResize = () => update(true)
    window.addEventListener('resize', onResize)
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onResize)
    observer?.observe(element)
    if (element.firstElementChild) observer?.observe(element.firstElementChild)
    return () => {
      element.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('scroll', onScroll, true)
      observer?.disconnect()
    }
  }, [children])
  const scroll = (direction: -1 | 1) => {
    const element = scrollRef.current
    if (element) element.scrollBy({ left: direction * element.clientWidth * .75, behavior: 'smooth' })
  }
  return <div className={`table-scroll-frame${className ? ` ${className}-frame` : ''}`}>
    <button ref={leftCueRef} type="button" className="table-scroll-cue left" aria-label={t('tableScrollLeft')} title={t('tableScrollLeft')} onClick={() => scroll(-1)}><ChevronLeft size={15} /></button>
    <div ref={scrollRef} className={`table-scroll ${className}`}>{children}</div>
    <button ref={rightCueRef} type="button" className="table-scroll-cue right" aria-label={t('tableScrollRight')} title={t('tableScrollRight')} onClick={() => scroll(1)}><ChevronRight size={15} /></button>
  </div>
}

function SortableHeader<T extends string>({ column, label, sort, onSort, filtered = false, filterLabel, className, hidden = false, busy = false }: { column: T; label: string; sort: { column: T; direction: 'asc' | 'desc' }; onSort: (column: T, event?: MouseEvent<HTMLButtonElement>) => void; filtered?: boolean; filterLabel?: string; className?: string; hidden?: boolean; busy?: boolean }) {
  const active = sort.column === column
  if (hidden) return null
  return <th className={className} aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}><button type="button" className={`sort-header${busy ? ' is-sort-pending' : ''}`} aria-busy={busy || undefined} title={filtered ? `${label} · ${filterLabel ?? ''}` : undefined} aria-label={filtered ? `${label} · ${filterLabel ?? ''}` : label} onClick={(event) => onSort(column, event)}><span>{label}</span>{active && (sort.direction === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}{filtered && <Filter size={11} className="column-filter-marker" aria-hidden="true" />}</button></th>
}

function Paginator({ total, pageIndex, pageSize, onPageChange, onPageSizeChange, pageSizes = allowedPageSizes, t, language }: { total: number; pageIndex: number; pageSize: PageSize; onPageChange: (page: number) => void; onPageSizeChange: (size: PageSize) => void; pageSizes?: PageSize[]; t: (key: MessageKey) => string; language: Language }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const page = Math.min(pageIndex, pageCount - 1)
  const from = total ? page * pageSize + 1 : 0
  const to = Math.min((page + 1) * pageSize, total)
  const [pageInput, setPageInput] = useState(String(page + 1))
  useEffect(() => setPageInput(String(page + 1)), [page, pageCount])
  const jump = (nextPage: number) => onPageChange(Math.max(0, Math.min(pageCount - 1, nextPage)))
  const button = (Icon: typeof ChevronLeft, label: MessageKey, target: number) => <button type="button" className="page-button" aria-label={t(label)} title={t(label)} disabled={page === Math.max(0, Math.min(pageCount - 1, target))} onClick={() => jump(target)}><Icon size={15} /></button>
  const jumpFromInput = () => {
    const requested = Number(pageInput)
    if (!Number.isInteger(requested) || requested < 1) {
      setPageInput(String(page + 1))
      return
    }
    jump(requested - 1)
  }
  return <div className="table-pagination"><div className="pagination-meta"><span>{t('showing')} {numberText(from, language)}–{numberText(to, language)} {t('of')} {numberText(total, language)}</span></div><div className="pagination-controls"><label className="page-size-control"><span>{t('rowsPerPage')}</span><select aria-label={t('rowsPerPage')} value={pageSize} onChange={(event) => { onPageSizeChange(Number(event.target.value) as PageSize); onPageChange(0) }}>{pageSizes.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>{button(SkipBack, 'firstPage', 0)}{button(ChevronsLeft, 'previousTenPages', page - 10)}{button(ChevronLeft, 'previousPage', page - 1)}{pageCount > 150 ? <label className="page-jump"><input type="number" min={1} max={pageCount} aria-label={t('selectPage')} value={pageInput} onChange={(event) => setPageInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') jumpFromInput() }} /><small>{t('maxPage')} {numberText(pageCount, language)}</small></label> : <select aria-label={t('selectPage')} value={page} onChange={(event) => jump(Number(event.target.value))}>{Array.from({ length: pageCount }, (_, index) => <option key={index} value={index}>{index + 1}</option>)}</select>}{button(ChevronRight, 'nextPage', page + 1)}{button(ChevronsRight, 'nextTenPages', page + 10)}{button(SkipForward, 'lastPage', pageCount - 1)}</div></div>
}

function CategoryGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: { title: MessageKey; description: MessageKey; example: string }[] = [
    { title: 'guideSensitiveFiles', description: 'guideSensitiveFilesDescription', example: 'GET /.env  ·  GET /backup.sql' },
    { title: 'guideWebshell', description: 'guideWebshellDescription', example: 'GET /php.php?cmd=id  ·  GET /c99.php' },
    { title: 'guideCms', description: 'guideCmsDescription', example: 'GET /wp-login.php  ·  GET /xmlrpc.php' },
    { title: 'guideAdmin', description: 'guideAdminDescription', example: 'GET /admin  ·  GET /login' },
    { title: 'guideApi', description: 'guideApiDescription', example: 'GET /api/v1/users  ·  GET /swagger' },
    { title: 'guideInfoLeaks', description: 'guideInfoLeaksDescription', example: 'GET /phpinfo.php  ·  GET /.git/config' },
    { title: 'guideVulnerabilitySearch', description: 'guideVulnerabilitySearchDescription', example: 'GET /vendor/phpunit  ·  GET /HNAP1' },
    { title: 'guideScanner', description: 'guideScannerDescription', example: 'User-Agent: Nuclei  ·  User-Agent: WPScan' },
    { title: 'guideDatabase', description: 'guideDatabaseDescription', example: 'GET /phpmyadmin  ·  GET /adminer.php' },
    { title: 'guideMonitoring', description: 'guideMonitoringDescription', example: 'GET /metrics  ·  GET /grafana' },
    { title: 'guideContainer', description: 'guideContainerDescription', example: 'GET /portainer  ·  GET /docker' },
    { title: 'guideOtherServices', description: 'guideOtherServicesDescription', example: 'GET /unknown-path  ·  Port 9000' },
    { title: 'guideLegacyOther', description: 'guideLegacyOtherDescription', example: 'Kategorie: andere' },
  ]

  return <InfoGuidePage t={t} title="categoryGuideTitle" subtitle="categoryGuideSubtitle" entries={entries} note="guideMultipleCategories" />
}


function IncidentGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'incidentGuideRuleTitle', description: 'incidentGuideRuleBody', exampleKey: 'incidentGuideRuleExample' },
    { title: 'incidentGuideEvidenceTitle', description: 'incidentGuideEvidenceBody', exampleKey: 'incidentGuideEvidenceExample' },
    { title: 'incidentGuideInterpretTitle', description: 'incidentGuideInterpretBody', exampleKey: 'incidentGuideInterpretExample' },
    { title: 'incidentGuideWorkflowTitle', description: 'incidentGuideWorkflowBody', exampleKey: 'incidentGuideWorkflowExample' },
  ]
  return <InfoGuidePage t={t} title="incidentGuideTitle" subtitle="incidentGuideSubtitle" entries={entries} note="incidentGuideCaveat" />
}

function BurstGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'burstGuideGroupingTitle', description: 'burstGuideGroupingBody', exampleKey: 'burstGuideGroupingExample' },
    { title: 'burstGuideRuleTitle', description: 'burstGuideRuleBody', exampleKey: 'burstGuideRuleExample' },
    { title: 'burstGuideMeaningTitle', description: 'burstGuideMeaningBody', exampleKey: 'burstGuideMeaningExample' },
    { title: 'burstGuideLimitsTitle', description: 'burstGuideLimitsBody', exampleKey: 'burstGuideLimitsExample' },
  ]
  return <InfoGuidePage t={t} title="burstGuideTitle" subtitle="burstGuideSubtitle" entries={entries} note="burstGuideCaveat" />
}

type GuideEntry = { title: MessageKey; description: MessageKey; example?: string; exampleKey?: MessageKey }
function InfoGuidePage({ t, title, subtitle, entries, note }: { t: (key: MessageKey) => string; title: MessageKey; subtitle: MessageKey; entries: GuideEntry[]; note: MessageKey }) {
  return <>
    <div className="page-heading"><div><h1>{t(title)}</h1><p>{t(subtitle)}</p></div></div>
    <div className="category-guide-grid">
      {entries.map((entry) => <article className="panel category-guide-card" key={entry.title}>
        <h2>{t(entry.title)}</h2>
        <p>{t(entry.description)}</p>
        {(entry.example || entry.exampleKey) && <div className="category-guide-example"><strong>{t('guideExamples')}</strong><code>{entry.exampleKey ? t(entry.exampleKey) : entry.example}</code></div>}
      </article>)}
    </div>
    <div className="category-guide-note"><CircleHelp size={16} /><span>{t(note)}</span></div>
  </>
}

function CountGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'countGuideTimeTitle', description: 'countGuideTimeBody', exampleKey: 'countGuideTimeExample' },
    { title: 'countGuideRequestsTitle', description: 'countGuideRequestsBody', exampleKey: 'countGuideRequestsExample' },
    { title: 'countGuideActorsTitle', description: 'countGuideActorsBody', exampleKey: 'countGuideActorsExample' },
    { title: 'countGuideBurstsTitle', description: 'countGuideBurstsBody', exampleKey: 'countGuideBurstsExample' },
    { title: 'countGuideCategoriesTitle', description: 'countGuideCategoriesBody', exampleKey: 'countGuideCategoriesExample' },
    { title: 'countGuideTrendsTitle', description: 'countGuideTrendsBody', exampleKey: 'countGuideTrendsExample' },
  ]
  return <InfoGuidePage t={t} title="countGuideTitle" subtitle="countGuideSubtitle" entries={entries} note="countGuideCaveat" />
}

function HostGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'hostGuideKnownTitle', description: 'hostGuideKnownBody', exampleKey: 'hostGuideKnownExample' },
    { title: 'hostGuideMatchingTitle', description: 'hostGuideMatchingBody', exampleKey: 'hostGuideMatchingExample' },
    { title: 'hostGuideBurstTitle', description: 'hostGuideBurstBody', exampleKey: 'hostGuideBurstExample' },
  ]
  return <InfoGuidePage t={t} title="hostGuideTitle" subtitle="hostGuideSubtitle" entries={entries} note="hostGuideCaveat" />
}

function PathsGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'pathsGuideSensitiveTitle', description: 'pathsGuideSensitiveBody', exampleKey: 'pathsGuideSensitiveExample' },
    { title: 'pathsGuideAdminTitle', description: 'pathsGuideAdminBody', exampleKey: 'pathsGuideAdminExample' },
    { title: 'pathsGuideCmsTitle', description: 'pathsGuideCmsBody', exampleKey: 'pathsGuideCmsExample' },
    { title: 'pathsGuideVulnerabilityTitle', description: 'pathsGuideVulnerabilityBody', exampleKey: 'pathsGuideVulnerabilityExample' },
    { title: 'pathsGuideDiagnosticsTitle', description: 'pathsGuideDiagnosticsBody', exampleKey: 'pathsGuideDiagnosticsExample' },
    { title: 'pathsGuideShellTitle', description: 'pathsGuideShellBody', exampleKey: 'pathsGuideShellExample' },
    { title: 'pathsGuideDatabaseTitle', description: 'pathsGuideDatabaseBody', exampleKey: 'pathsGuideDatabaseExample' },
    { title: 'pathsGuideApiTitle', description: 'pathsGuideApiBody', exampleKey: 'pathsGuideApiExample' },
  ]
  return <InfoGuidePage t={t} title="pathsGuideTitle" subtitle="pathsGuideSubtitle" entries={entries} note="pathsGuideCaveat" />
}

function HoneypotGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'honeypotGuideCaptureTitle', description: 'honeypotGuideCaptureBody' },
    { title: 'honeypotGuideGroupsTitle', description: 'honeypotGuideGroupsBody' },
    { title: 'honeypotGuidePostsTitle', description: 'honeypotGuidePostsBody' },
    { title: 'honeypotGuideRequestsTitle', description: 'honeypotGuideRequestsBody' },
  ]
  return <InfoGuidePage t={t} title="honeypotGuideTitle" subtitle="honeypotGuideSubtitle" entries={entries} note="honeypotGuideCaveat" />
}

function CowrieGuidePage({ t }: { t: (key: MessageKey) => string }) {
  const entries: GuideEntry[] = [
    { title: 'cowrieGuidePurposeTitle', description: 'cowrieGuidePurposeBody' },
    { title: 'cowrieGuideGroupsTitle', description: 'cowrieGuideGroupsBody' },
    { title: 'cowrieGuideIndicatorsTitle', description: 'cowrieGuideIndicatorsBody' },
    { title: 'cowrieGuideSessionsTitle', description: 'cowrieGuideSessionsBody' },
    { title: 'cowrieGuideLimitsTitle', description: 'cowrieGuideLimitsBody' },
  ]
  return <InfoGuidePage t={t} title="cowrieGuideTitle" subtitle="cowrieGuideSubtitle" entries={entries} note="cowrieGuideCaveat" />
}

function cowrieEventLabel(eventType: string): string {
  return eventType.replace(/^cowrie\./, '')
}

function CowrieDifference({ value, other }: { value: string; other: string }) {
  if (value === other) return <>{value}</>
  let prefix = 0
  while (prefix < value.length && prefix < other.length && value[prefix] === other[prefix]) prefix += 1
  let suffix = 0
  while (suffix < value.length - prefix && suffix < other.length - prefix && value[value.length - 1 - suffix] === other[other.length - 1 - suffix]) suffix += 1
  return <>{value.slice(0, prefix)}<mark className="cowrie-diff">{value.slice(prefix, value.length - suffix)}</mark>{suffix ? value.slice(-suffix) : null}</>
}

type CowrieGroupPanel = 'commands' | 'ssh'
type CowrieDetailSortColumn = 'time' | 'event_type'
type CowrieGroupSortColumn = 'last_time' | 'src_ip' | 'event_count' | 'failed_login_count' | 'command_count'
type CowrieCommandSortColumn = 'category' | 'command' | 'occurrences' | 'session_count'
type CowrieSequenceSortColumn = 'commands' | 'session_count' | 'first_time'

function CowrieGroupAnalysisView({ analysis, loading, error, retry, t, language }: {
  analysis: CowrieGroupAnalysis | null; loading: boolean; error: string | null; retry: () => void;
  t: (key: MessageKey) => string; language: Language
}) {
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [commandSort, setCommandSort] = useState<{ column: CowrieCommandSortColumn; direction: 'asc' | 'desc' }>({ column: 'occurrences', direction: 'desc' })
  const [sequenceSort, setSequenceSort] = useState<{ column: CowrieSequenceSortColumn; direction: 'asc' | 'desc' }>({ column: 'session_count', direction: 'desc' })
  const categoryLabels = {
    discovery: 'cowrieCommandDiscovery', credential_access: 'cowrieCommandCredentialAccess', download: 'cowrieCommandDownload',
    persistence: 'cowrieCommandPersistence', execution: 'cowrieCommandExecution', destructive: 'cowrieCommandDestructive', other: 'cowrieCommandOther',
  } as const
  const locale = language === 'de' ? 'de-DE' : 'en-GB'
  const normalizedSearch = search.trim().toLocaleLowerCase(locale)
  const filteredCommands = (analysis?.commands ?? []).filter((command) => !normalizedSearch || `${command.command} ${command.normalized_command} ${t(categoryLabels[command.category])}`.toLocaleLowerCase(locale).includes(normalizedSearch)).sort((left, right) => {
    let comparison = 0
    if (commandSort.column === 'category') comparison = t(categoryLabels[left.category]).localeCompare(t(categoryLabels[right.category]), locale)
    else if (commandSort.column === 'command') comparison = left.command.localeCompare(right.command, locale)
    else if (commandSort.column === 'occurrences') comparison = left.occurrences - right.occurrences
    else comparison = left.session_count - right.session_count
    return commandSort.direction === 'asc' ? comparison : -comparison
  })
  const filteredSequences = (analysis?.command_sequences ?? []).filter((sequence) => !normalizedSearch || sequence.commands.join(' ').toLocaleLowerCase(locale).includes(normalizedSearch)).sort((left, right) => {
    let comparison = 0
    if (sequenceSort.column === 'commands') comparison = left.commands.join(' ').localeCompare(right.commands.join(' '), locale)
    else if (sequenceSort.column === 'session_count') comparison = left.session_count - right.session_count
    else comparison = Date.parse(left.first_time) - Date.parse(right.first_time)
    return sequenceSort.direction === 'asc' ? comparison : -comparison
  })
  const changeCommandSort = (column: CowrieCommandSortColumn) => setCommandSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' }))
  const changeSequenceSort = (column: CowrieSequenceSortColumn) => setSequenceSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' }))
  const applySearch = () => setSearch(searchDraft.trim())
  return <div className="cowrie-command-analysis">
    <PageDataState loading={loading && !analysis} error={error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters cowrie-analysis-filter-toolbar"><label className="filter-search"><Search size={15} /><input type="search" value={searchDraft} placeholder={t('cowrieAnalysisSearch')} aria-label={t('cowrieAnalysisSearch')} title={t('cowrieAnalysisSearchHint')} onChange={(event) => setSearchDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applySearch() }} /></label><button type="button" className="filter-button" onClick={() => { setSearchDraft(''); setSearch('') }}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applySearch}>{t('applyFilters')}</button></div>
    {analysis && <><div className="cowrie-analysis-table-scroll"><table><thead><tr><SortableHeader<CowrieCommandSortColumn> column="category" label={t('cowrieCommandCategory')} sort={commandSort} onSort={changeCommandSort} filtered={Boolean(normalizedSearch)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieCommandSortColumn> column="command" label={t('cowrieCommand')} sort={commandSort} onSort={changeCommandSort} filtered={Boolean(normalizedSearch)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieCommandSortColumn> column="occurrences" label={t('cowrieCommandOccurrences')} sort={commandSort} onSort={changeCommandSort} /><SortableHeader<CowrieCommandSortColumn> column="session_count" label={t('cowrieSessions')} sort={commandSort} onSort={changeCommandSort} /></tr></thead><tbody>
      {filteredCommands.map((command) => <tr key={command.normalized_command}><td><span className="cowrie-command-category">{t(categoryLabels[command.category])}</span></td><td className="cowrie-analysis-detail"><code>{command.command}</code><small>{requestDateTimeText(command.first_time, language)} · {incidentDurationText(command.first_time, command.last_time, language)}</small></td><td>{numberText(command.occurrences, language)}</td><td>{numberText(command.session_count, language)}</td></tr>)}
      {filteredCommands.length === 0 && <EmptyRows t={t} columns={4} />}
    </tbody></table></div></>}
    {analysis && <><h4 className="cowrie-command-sequences-title">{t('cowrieCommandSequences')}</h4><div className="cowrie-analysis-table-scroll"><table><thead><tr><SortableHeader<CowrieSequenceSortColumn> column="commands" label={t('cowrieCommandSequence')} sort={sequenceSort} onSort={changeSequenceSort} filtered={Boolean(normalizedSearch)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieSequenceSortColumn> column="session_count" label={t('cowrieSessions')} sort={sequenceSort} onSort={changeSequenceSort} /><SortableHeader<CowrieSequenceSortColumn> column="first_time" label={t('dateTime')} sort={sequenceSort} onSort={changeSequenceSort} /></tr></thead><tbody>
      {filteredSequences.map((sequence, index) => <tr key={`${sequence.commands.join('\u001f')}-${index}`}><td className="cowrie-analysis-detail cowrie-command-sequence">{sequence.commands.map((command, commandIndex) => <Fragment key={`${commandIndex}-${command}`}><code>{command}</code>{commandIndex < sequence.commands.length - 1 && <span> → </span>}</Fragment>)}</td><td>{numberText(sequence.session_count, language)}</td><td className="cowrie-analysis-detail"><small>{requestDateTimeText(sequence.first_time, language)} · {incidentDurationText(sequence.first_time, sequence.last_time, language)}</small></td></tr>)}
      {filteredSequences.length === 0 && <EmptyRows t={t} columns={3} />}
    </tbody></table></div>{analysis.command_sequences_truncated && <p className="cowrie-analysis-footnote">{t('cowrieCommandSequencesTruncated')}</p>}</>}
  </div>
}

function CowriePage({ t, language, range, onRangeChange, lastImport, openGroupPanel, onGroupPanelChange, filters, onFiltersChange }: RangePageProps & { openGroupPanel: CowrieGroupPanel; onGroupPanelChange: (panel: CowrieGroupPanel) => void; filters: CowrieFilters; onFiltersChange: (filters: CowrieFilters) => void }) {
  const [isGroupPanelRendering, startGroupPanelRender] = useTransition()
  const [pendingGroupPanel, setPendingGroupPanel] = useState<CowrieGroupPanel | null>(null)
  const [searchDraft, setSearchDraft] = useState(filters.search)
  const [search, setSearch] = useState(filters.search)
  const [eventType, setEventType] = useState(filters.eventType)
  const [draftEventType, setDraftEventType] = useState(filters.eventType)
  const [protectedOnly, setProtectedOnly] = useState(filters.protectedOnly)
  const [draftProtectedOnly, setDraftProtectedOnly] = useState(filters.protectedOnly)
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState<PageSize>(25)
  const [groupSort, setGroupSort] = useState<{ column: CowrieGroupSortColumn; direction: 'asc' | 'desc' }>({ column: 'last_time', direction: 'desc' })
  const [expandedGroup, setExpandedGroup] = useState<CowrieGroup | null>(null)
  const [detailSearchDraft, setDetailSearchDraft] = useState(filters.detailSearch)
  const [detailSearch, setDetailSearch] = useState(filters.detailSearch)
  const [payloadView, setPayloadView] = useState<PayloadView>('formatted')
  const [detailSort, setDetailSort] = useState<{ column: CowrieDetailSortColumn; direction: 'asc' | 'desc' }>({ column: 'time', direction: 'desc' })
  const detailTableRef = useRef<HTMLDivElement>(null)
  const detailSortFrames = useRef<number[]>([])
  const [selectedEvent, setSelectedEvent] = useState<CowrieEvent | null>(null)
  const [selectedTtyGroup, setSelectedTtyGroup] = useState<CowrieGroup | null>(null)
  const [ttyPage, setTtyPage] = useState(0)
  const [ttyPageSize, setTtyPageSize] = useState<PageSize>(25)
  const [ttyDistinct, setTtyDistinct] = useState(false)
  const [ttySwitching, setTtySwitching] = useState(false)
  const ttyRecording = useApiData<{ items: { event_id: string; session?: string; occurrences: number; complete: boolean; bytes_read: number; chunks: { kind: 'input' | 'output' | 'command'; text: string }[] }[]; total: number; limit: number; offset: number; distinct: boolean }>(selectedTtyGroup ? apiUrl('cowrie/groups/tty', undefined, { src_ip: selectedTtyGroup.src_ip ?? '', from: selectedTtyGroup.first_time, to: selectedTtyGroup.last_time, limit: String(ttyPageSize), offset: String(ttyPage * ttyPageSize), ...(ttyDistinct ? { distinct: 'true' } : {}) }) : null)
  const ttyDataBeforeSwitch = useRef(ttyRecording.data)
  const [deletingGroup, setDeletingGroup] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const summary = useApiData<CowrieSummary>(apiUrl('cowrie/summary', range.query))
  const groups = useApiData<{ items: CowrieGroup[]; total: number }>(apiUrl('cowrie/groups', range.query, {
    limit: String(pageSize), offset: String(pageIndex * pageSize), ...(search ? { search } : {}), ...(eventType ? { event_type: eventType } : {}), ...(protectedOnly ? { protected_only: 'true' } : {}), sort_by: groupSort.column, sort_order: groupSort.direction,
  }))
  const groupEvents = useApiData<{ items: CowrieEvent[]; total: number }>(expandedGroup ? apiUrl('cowrie/group-events', undefined, {
    src_ip: expandedGroup.src_ip ?? '', from: expandedGroup.first_time, to: expandedGroup.last_time, ...(search ? { search } : {}), ...(eventType ? { event_type: eventType } : {}),
  }) : null)
  const groupAnalysis = useApiData<CowrieGroupAnalysis>(expandedGroup?.src_ip ? apiUrl('cowrie/group-commands', undefined, {
    src_ip: expandedGroup.src_ip, from: expandedGroup.first_time, to: expandedGroup.last_time,
  }) : null)
  const currentGroupAnalysis = expandedGroup?.src_ip && groupAnalysis.data?.src_ip === expandedGroup.src_ip && Date.parse(groupAnalysis.data.from) === Date.parse(expandedGroup.first_time) && Date.parse(groupAnalysis.data.to) === Date.parse(expandedGroup.last_time) ? groupAnalysis.data : null
  const selectedGroupTabLoading = openGroupPanel === 'commands'
    ? groupAnalysis.loading || Boolean(expandedGroup?.src_ip && !currentGroupAnalysis && !groupAnalysis.error)
    : groupEvents.loading
  const groupPanelBusy = selectedGroupTabLoading || isGroupPanelRendering
  const cowrieDetailItems = groupEvents.data?.items ?? []
  const normalizedDetailSearch = detailSearch.trim().toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-GB')
  const filteredCowrieDetailItems = useMemo(() => cowrieDetailItems.filter((item) => !normalizedDetailSearch || [item.src_ip, item.session, item.event_type, item.username, item.password, item.input, item.message, item.sensor, item.extra_json].some((value) => value?.toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-GB').includes(normalizedDetailSearch))).sort((left, right) => {
    let order = 0
    if (detailSort.column === 'time') order = Date.parse(left.time) - Date.parse(right.time)
    else order = cowrieEventLabel(left.event_type).localeCompare(cowrieEventLabel(right.event_type), language === 'de' ? 'de-DE' : 'en-GB')
    return detailSort.direction === 'asc' ? order : -order
  }), [cowrieDetailItems, detailSort, language, normalizedDetailSearch])
  const cowrieDetailIndex = selectedEvent ? cowrieDetailItems.findIndex((item) => item.event_id === selectedEvent.event_id) : -1
  const moveCowrieDetail = (offset: number) => { const item = cowrieDetailItems[cowrieDetailIndex + offset]; if (item) setSelectedEvent(item) }
  const sortCowrieDetails = (column: CowrieDetailSortColumn, event?: MouseEvent<HTMLButtonElement>) => {
    detailSortFrames.current.forEach((frame) => window.cancelAnimationFrame(frame))
    detailSortFrames.current = []
    const table = detailTableRef.current
    table?.querySelectorAll('.sort-header.is-sort-pending').forEach((button) => button.classList.remove('is-sort-pending'))
    const button = event?.currentTarget
    button?.classList.add('is-sort-pending')
    table?.setAttribute('aria-busy', 'true')
    const firstFrame = window.requestAnimationFrame(() => {
      const secondFrame = window.requestAnimationFrame(() => {
        detailSortFrames.current = []
        setDetailSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' }))
      })
      detailSortFrames.current = [secondFrame]
    })
    detailSortFrames.current = [firstFrame]
  }
  useEffect(() => {
    const table = detailTableRef.current
    table?.querySelectorAll('.sort-header.is-sort-pending').forEach((button) => button.classList.remove('is-sort-pending'))
    table?.removeAttribute('aria-busy')
    detailSortFrames.current.forEach((frame) => window.cancelAnimationFrame(frame))
    detailSortFrames.current = []
  }, [detailSort])
  useEffect(() => () => detailSortFrames.current.forEach((frame) => window.cancelAnimationFrame(frame)), [])
  const applyDetailSearch = () => { const value = detailSearchDraft.trim(); setDetailSearch(value); onFiltersChange({ ...filters, detailSearch: value }) }
  const showGroupPanel = (panel: CowrieGroupPanel) => {
    if (panel === openGroupPanel) return
    setPendingGroupPanel(panel)
    startGroupPanelRender(() => onGroupPanelChange(panel))
  }
  useEffect(() => {
    if (!isGroupPanelRendering && pendingGroupPanel && openGroupPanel === pendingGroupPanel) setPendingGroupPanel(null)
  }, [isGroupPanelRendering, openGroupPanel, pendingGroupPanel])
  useEffect(() => { setSearchDraft(filters.search); setSearch(filters.search); setDraftEventType(filters.eventType); setEventType(filters.eventType); setDraftProtectedOnly(filters.protectedOnly); setProtectedOnly(filters.protectedOnly); setDetailSearchDraft(filters.detailSearch); setDetailSearch(filters.detailSearch) }, [filters])
  const applySearch = () => { const next = { ...filters, search: searchDraft.trim(), eventType: draftEventType, protectedOnly: draftProtectedOnly }; setPageIndex(0); setSearch(next.search); setEventType(next.eventType); setProtectedOnly(next.protectedOnly); setExpandedGroup(null); onFiltersChange(next) }
  const changeGroupSort = (column: CowrieGroupSortColumn) => { setPageIndex(0); setExpandedGroup(null); setGroupSort((current) => ({ column, direction: current.column === column && current.direction === 'asc' ? 'desc' : 'asc' })) }
  const resetFilters = () => { setSearchDraft(''); setSearch(''); setEventType(''); setDraftEventType(''); setProtectedOnly(false); setDraftProtectedOnly(false); setDetailSearchDraft(''); setDetailSearch(''); setPageIndex(0); setExpandedGroup(null); onFiltersChange(defaultCowrieFilters) }
  const deleteGroup = async (group: CowrieGroup) => {
    if (!group.src_ip) return
    const confirmation = t('confirmCowrieDeleteGroup')
      .replace('{ip}', group.src_ip)
      .replace('{events}', numberText(group.event_count, language))
    if (!window.confirm(confirmation)) return
    const key = `${group.src_ip}-${group.first_time}`
    setDeletingGroup(key)
    setActionError('')
    try {
      const response = await apiFetch(apiUrl('cowrie/groups', undefined, {
        src_ip: group.src_ip, from: group.first_time, to: group.last_time,
      }), { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (expandedGroup?.src_ip === group.src_ip && expandedGroup.first_time === group.first_time) setExpandedGroup(null)
      groups.reload()
      summary.reload()
    } catch {
      setActionError(t('cowrieDeleteGroupFailed'))
    } finally {
      setDeletingGroup(null)
    }
  }
  useEffect(() => {
    if (!selectedEvent && !selectedTtyGroup) return
    const root = document.documentElement
    const body = document.body
    const previousRootOverflow = root.style.overflow
    const previousBodyOverflow = body.style.overflow
    root.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setSelectedEvent(null); setSelectedTtyGroup(null) } }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      root.style.overflow = previousRootOverflow
      body.style.overflow = previousBodyOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [selectedEvent, selectedTtyGroup])
  useEffect(() => {
    if (ttySwitching && (ttyRecording.data !== ttyDataBeforeSwitch.current || ttyRecording.error)) setTtySwitching(false)
  }, [ttyRecording.data, ttyRecording.error, ttySwitching])
  return <>
    <PageHeading title={t('cowrie')} subtitle={t('cowrieSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <section className="metric-grid honeypot-period-metrics">
      <MetricCard t={t} language={language} label={t('cowrieEvents')} value={numberText(summary.data?.event_count ?? 0, language)} icon={Activity} iconClass="violet" caption={t('cowrieEventsNote')} />
      <MetricCard t={t} language={language} label={t('honeypotUniqueActors')} value={numberText(summary.data?.actor_count ?? 0, language)} icon={Users} iconClass="blue" caption={t('honeypotUniqueActorsNote')} />
      <MetricCard t={t} language={language} label={t('cowrieFailedLogins')} value={numberText(summary.data?.failed_login_count ?? 0, language)} icon={ShieldAlert} iconClass="amber" caption={t('cowrieFailedLoginsNote')} />
      <MetricCard t={t} language={language} label={t('cowrieCommands')} value={numberText(summary.data?.command_count ?? 0, language)} icon={FileText} iconClass="green" caption={t('cowrieCommandsNote')} />
    </section>
    {actionError && <div className="log-error" role="alert">{actionError}</div>}
    <PageDataState loading={groups.loading} error={groups.error} retry={() => { summary.reload(); groups.reload() }} t={t} />
    <section className="panel table-panel honeypot-panel">
      <div className="filter-toolbar honeypot-toolbar">
        <label className="filter-search"><Search size={15} /><input type="search" value={searchDraft} placeholder={t('cowrieSearch')} aria-label={t('cowrieSearch')} onChange={(event) => setSearchDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applySearch() }} /></label>
        <label className="filter-select"><select aria-label={t('cowrieEventType')} value={draftEventType} onChange={(event) => setDraftEventType(event.target.value)}><option value="">{t('cowrieAllEvents')}</option><option value="cowrie.login.failed">login.failed</option><option value="cowrie.login.success">login.success</option><option value="cowrie.command.input">command.input</option><option value="cowrie.session.connect">session.connect</option></select><span className="filter-select-value">{draftEventType ? cowrieEventLabel(draftEventType) : t('cowrieAllEvents')}</span><ChevronDown size={13} /></label>
        <label className="request-without-burst-filter"><input type="checkbox" checked={draftProtectedOnly} onChange={(event) => setDraftProtectedOnly(event.target.checked)} /><span>{t('protectedIpsOnly')}</span></label>
        <button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button>
        <button type="button" className="primary-button filter-submit" onClick={applySearch}>{t('applyFilters')}</button>
        <span className="honeypot-events-count">{t('cowrieEvents')}: {numberText(groups.data?.total ?? 0, language)}</span>
      </div>
      <Paginator total={groups.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={(page) => { setPageIndex(page); setExpandedGroup(null) }} onPageSizeChange={(size) => { setPageSize(size); setPageIndex(0); setExpandedGroup(null) }} t={t} language={language} />
      <div className="table-scroll"><table className="honeypot-table"><thead><tr><SortableHeader<CowrieGroupSortColumn> column="last_time" label={t('dateTime')} sort={groupSort} onSort={changeGroupSort} filtered filterLabel={t('filteredColumn')} /><SortableHeader<CowrieGroupSortColumn> column="src_ip" label={t('actor')} sort={groupSort} onSort={changeGroupSort} filtered={Boolean(search || protectedOnly)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieGroupSortColumn> column="event_count" label={t('cowrieEvents')} sort={groupSort} onSort={changeGroupSort} filtered={Boolean(search || eventType)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieGroupSortColumn> column="failed_login_count" label={t('cowrieFailedLoginsShort')} sort={groupSort} onSort={changeGroupSort} filtered={Boolean(search || eventType)} filterLabel={t('filteredColumn')} /><SortableHeader<CowrieGroupSortColumn> column="command_count" label={t('cowrieCommands')} sort={groupSort} onSort={changeGroupSort} filtered={Boolean(search || eventType)} filterLabel={t('filteredColumn')} /><th>{t('cowrieTtyLink')}</th></tr></thead><tbody>
        {groups.data?.items.map((group) => {
          const expanded = expandedGroup?.src_ip === group.src_ip && expandedGroup.first_time === group.first_time
          return <Fragment key={`${group.src_ip}-${group.first_time}`}>
            <tr>
              <td><span className="incident-time-cell"><strong>{requestDateTimeText(group.first_time, language)}</strong><small>{incidentDurationText(group.first_time, group.last_time, language)}</small></span></td>
              <td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={group.src_ip} t={t} /><strong className="primary-cell">{group.src_ip || '—'}</strong></span><ActorMetadata provider={group.provider} asn={group.asn} country={group.country} city={group.city} /></span></td>
              <td><span className="honeypot-group-actions"><button type="button" className="table-link honeypot-group-toggle" aria-expanded={expanded} onClick={() => setExpandedGroup(expanded ? null : group)}>{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{numberText(group.event_count, language)}</button><button type="button" className="icon-button honeypot-delete-session actor-delete-button" aria-label={t('cowrieDeleteGroup')} title={t('cowrieDeleteGroup')} disabled={deletingGroup === `${group.src_ip ?? ''}-${group.first_time}`} onClick={() => void deleteGroup(group)}><Trash2 size={14} /></button></span></td>
              <td>{numberText(group.failed_login_count, language)}</td><td title={t('cowrieCommandCountNote')}>{numberText(group.command_count, language)}</td><td>{group.tty_recording_count > 0 ? <button type="button" className="table-link cowrie-tty-open-link" onClick={() => { setTtyPage(0); setSelectedTtyGroup(group) }}><FileText size={13} />{t('cowrieTtyLink')} · {numberText(group.tty_recording_count, language)}</button> : '—'}</td>
            </tr>
            {expanded && <tr className="honeypot-group-expanded"><td colSpan={6}>
              <div className="honeypot-group-events">
                <div className="cowrie-group-tabs">
                  <div className="cowrie-group-tabs-header">
                    <div className="cowrie-group-tablist" role="tablist" aria-label={t('cowrieGroupTabs')}>
                    <button id="cowrie-tab-commands" type="button" role="tab" aria-selected={openGroupPanel === 'commands'} aria-controls="cowrie-tabpanel" tabIndex={openGroupPanel === 'commands' ? 0 : -1} className={`cowrie-group-tab${openGroupPanel === 'commands' ? ' active' : ''}`} onClick={() => showGroupPanel('commands')} onKeyDown={(event) => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); showGroupPanel('ssh'); document.getElementById('cowrie-tab-ssh')?.focus() } }}>{t('cowrieCommandPatterns')}{currentGroupAnalysis && <span className="cowrie-tab-count">{numberText(currentGroupAnalysis.command_total, language)}</span>}{((openGroupPanel === 'commands' && selectedGroupTabLoading) || (isGroupPanelRendering && pendingGroupPanel === 'commands')) && <span className="loading-spinner cowrie-group-tabs-spinner" role="status" aria-label={t('loadingData')} />}</button>
                    <button id="cowrie-tab-ssh" type="button" role="tab" aria-selected={openGroupPanel === 'ssh'} aria-controls="cowrie-tabpanel" tabIndex={openGroupPanel === 'ssh' ? 0 : -1} className={`cowrie-group-tab${openGroupPanel === 'ssh' ? ' active' : ''}`} onClick={() => showGroupPanel('ssh')} onKeyDown={(event) => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); showGroupPanel('commands'); document.getElementById('cowrie-tab-commands')?.focus() } }}>{t('cowrieSshEventDetails')}{groupEvents.data && <span className="cowrie-tab-count">{numberText(groupEvents.data.total, language)}</span>}{((openGroupPanel === 'ssh' && selectedGroupTabLoading) || (isGroupPanelRendering && pendingGroupPanel === 'ssh')) && <span className="loading-spinner cowrie-group-tabs-spinner" role="status" aria-label={t('loadingData')} />}</button>
                    </div>
                  </div>
                  <div className="cowrie-group-tabpanel" id="cowrie-tabpanel" role="tabpanel" aria-busy={groupPanelBusy} aria-labelledby={openGroupPanel === 'commands' ? 'cowrie-tab-commands' : 'cowrie-tab-ssh'}>
                    {openGroupPanel === 'commands' ? <CowrieGroupAnalysisView analysis={currentGroupAnalysis} loading={groupAnalysis.loading || Boolean(expandedGroup?.src_ip && !currentGroupAnalysis && !groupAnalysis.error)} error={groupAnalysis.error} retry={groupAnalysis.reload} t={t} language={language} /> : <>
                      <div className="filter-toolbar burst-filters cowrie-detail-filter-toolbar"><label className="filter-search"><Search size={15} /><input type="search" value={detailSearchDraft} placeholder={t('cowrieDetailSearch')} aria-label={t('cowrieDetailSearch')} title={t('cowrieDetailSearchHint')} onChange={(event) => setDetailSearchDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applyDetailSearch() }} /></label><button type="button" className="filter-button" onClick={() => { setDetailSearchDraft(''); setDetailSearch(''); onFiltersChange({ ...filters, detailSearch: '' }) }}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyDetailSearch}>{t('applyFilters')}</button></div>
                      <PageDataState loading={groupEvents.loading} error={groupEvents.error} retry={groupEvents.reload} t={t} />
                      {groupEvents.data && <><div className="cowrie-session-time"><span><small>{t('startTime')}</small><strong>{requestDateTimeText(expandedGroup?.first_time, language)}</strong></span><span><small>{t('duration')}</small><strong>{expandedGroup ? incidentDurationText(expandedGroup.first_time, expandedGroup.last_time, language) : '—'}</strong></span></div><div ref={detailTableRef} className="table-scroll cowrie-detail-table-scroll"><table><thead><tr><SortableHeader<CowrieDetailSortColumn> column="time" label={t('dateTime')} sort={detailSort} onSort={sortCowrieDetails} /><SortableHeader<CowrieDetailSortColumn> column="event_type" label={t('cowrieEventType')} sort={detailSort} onSort={sortCowrieDetails} filtered={Boolean(normalizedDetailSearch)} filterLabel={t('filteredColumn')} /><th>{t('cowrieCommand')}{normalizedDetailSearch && <Filter size={11} className="column-filter-marker" aria-hidden="true" />}</th><th>{t('honeypotData')}{normalizedDetailSearch && <Filter size={11} className="column-filter-marker" aria-hidden="true" />}</th></tr></thead><tbody>
                        {filteredCowrieDetailItems.map((item) => {
                          const payload = item.input ?? item.message ?? ''
                          const content = item.input ? `${t('cowrieInput')}: ${payload}` : item.message ? `${t('cowrieMessage')}: ${payload}` : ''
                          const truncated = content.length > 100
                          const preview = truncated ? `${content.slice(0, 100)}…` : content
                          const payloadCharacters = Array.from(payload).length
                          return <tr key={item.event_id}>
                            <td><span className="incident-time-cell"><strong>{requestDateTimeText(item.time, language)} . {timestampMillisText(item.time, language)}</strong></span></td>
                            <td><code>{cowrieEventLabel(item.event_type)}</code></td>
                            <td className="honeypot-path"><span className="cowrie-preview-row"><code className="path-cell">{preview || '—'}</code>{truncated && <button type="button" className="cowrie-truncated-badge" aria-label={`${t('cowrieTruncated')} · ${numberText(payloadCharacters, language)} ${t('cowrieCharacters')}`} onClick={() => setSelectedEvent(item)}>{t('cowrieTruncated')}<small>{numberText(payloadCharacters, language)} {t('cowrieCharacters')}</small></button>}</span></td>
                            <td><button type="button" className="table-link honeypot-body-link" onClick={() => setSelectedEvent(item)}><FileText size={13} />{t('honeypotViewData')}</button></td>
                          </tr>
                        })}
                        {!groupEvents.loading && filteredCowrieDetailItems.length === 0 && <EmptyRows t={t} columns={4} />}
                      </tbody></table></div></>}
                    </>}
                  </div>
                </div>
              </div>
            </td></tr>}
          </Fragment>
        })}
        {!groups.loading && groups.data?.items.length === 0 && <EmptyRows t={t} columns={6} />}
      </tbody></table></div>
      <Paginator total={groups.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={(page) => { setPageIndex(page); setExpandedGroup(null) }} onPageSizeChange={(size) => { setPageSize(size); setPageIndex(0); setExpandedGroup(null) }} t={t} language={language} />
    </section>
    {selectedEvent && <div className="honeypot-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedEvent(null) }}><div className="honeypot-dialog-shell"><div className="honeypot-dialog-controls"><button type="button" className="icon-button" onClick={() => setSelectedEvent(null)} aria-label={t('close')} title={t('close')}><X size={16} /></button><button type="button" className="icon-button" onClick={() => moveCowrieDetail(-1)} disabled={cowrieDetailIndex <= 0} aria-label={t('previousRecord')} title={t('previousRecord')}><ChevronUp size={16} /></button><button type="button" className="icon-button" onClick={() => moveCowrieDetail(1)} disabled={cowrieDetailIndex < 0 || cowrieDetailIndex >= cowrieDetailItems.length - 1} aria-label={t('nextRecord')} title={t('nextRecord')}><ChevronDown size={16} /></button></div><section className="panel honeypot-detail honeypot-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="cowrie-event-details-title"><div className="panel-header"><h2 id="cowrie-event-details-title">{t('honeypotDetails')}</h2></div>
      <dl className="honeypot-meta cowrie-event-meta"><dt>{t('dateTime')}</dt><dd>{dateText(selectedEvent.time, language)}</dd><dt>{t('actor')}</dt><dd><span className="actor-detail"><strong className="primary-cell">{selectedEvent.src_ip || '—'}</strong><ActorMetadata provider={selectedEvent.provider} asn={selectedEvent.asn} country={selectedEvent.country} city={selectedEvent.city} /></span></dd><dt>{t('cowrieEventType')}</dt><dd><code>{cowrieEventLabel(selectedEvent.event_type)}</code></dd><dt>{t('honeypotSessionId')}</dt><dd>{selectedEvent.session || '—'}</dd><dt>{t('cowrieUsername')}</dt><dd>{selectedEvent.username || '—'}</dd><dt>{t('cowriePassword')}</dt><dd>{selectedEvent.password || '—'}</dd>
        {selectedEvent.input && selectedEvent.message && <><dt>{t('cowrieDifferences')}</dt><dd><span className="cowrie-comparison-state">{selectedEvent.input.trim() === selectedEvent.message.trim() ? t('cowrieSameContent') : t('cowrieDifferences')}</span></dd></>}
        <dt>{t('payloadView')}</dt><dd><PayloadViewTabs view={payloadView} onChange={setPayloadView} t={t} /></dd>
        <dt className="cowrie-payload-label">{t('cowrieInput')}<CopyPayloadButton text={payloadView === 'raw' ? selectedEvent.input || '—' : formatPayloadText(selectedEvent.input || '—', t).copyText} t={t} /></dt><dd className="cowrie-payload-value"><PayloadText body={selectedEvent.input || '—'} view={payloadView} t={t} rawContent={selectedEvent.input && selectedEvent.message ? <CowrieDifference value={selectedEvent.input} other={selectedEvent.message} /> : selectedEvent.input || '—'} /></dd><dt className="cowrie-payload-label">{t('cowrieMessage')}<CopyPayloadButton text={payloadView === 'raw' ? selectedEvent.message || '—' : formatPayloadText(selectedEvent.message || '—', t).copyText} t={t} /></dt><dd className="cowrie-payload-value"><PayloadText body={selectedEvent.message || '—'} view={payloadView} t={t} rawContent={selectedEvent.input && selectedEvent.message ? <CowrieDifference value={selectedEvent.message} other={selectedEvent.input} /> : selectedEvent.message || '—'} /></dd></dl>
      {selectedEvent.extra_json && (() => { try { const extra = JSON.parse(selectedEvent.extra_json) as Record<string, unknown>; const entries = Object.entries(extra).filter(([, value]) => value !== null && value !== ''); return entries.length ? <><h3>{t('cowrieAdditionalFields')}</h3><dl className="honeypot-meta">{entries.map(([key, value]) => <Fragment key={key}><dt>{key}</dt><dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd></Fragment>)}</dl></> : null } catch { return null } })()}
    </section></div></div>}
    {selectedTtyGroup && <div className="honeypot-modal-backdrop cowrie-tty-modal" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedTtyGroup(null) }}><div className="honeypot-dialog-shell"><div className="honeypot-dialog-controls cowrie-tty-close-controls"><button type="button" className="icon-button" onClick={() => setSelectedTtyGroup(null)} aria-label={t('close')} title={t('close')}><X size={16} /></button></div><section className="panel honeypot-detail honeypot-detail-dialog cowrie-tty-dialog" role="dialog" aria-modal="true" aria-labelledby="cowrie-tty-title">
      <header className="panel-header cowrie-tty-header"><div className="cowrie-tty-heading"><h2 id="cowrie-tty-title">{t('cowrieTtyTitle')}</h2><label className="cowrie-tty-distinct-toggle"><input type="checkbox" checked={ttyDistinct} onChange={(event) => { ttyDataBeforeSwitch.current = ttyRecording.data; setTtySwitching(true); setTtyDistinct(event.target.checked); setTtyPage(0) }} /><span>{t('cowrieTtyDistinct')}</span></label>{(ttyRecording.loading || ttySwitching) && <span className="loading-spinner cowrie-tty-switch-spinner" role="status" aria-label={t('cowrieTtyLoading')} />}</div><span>{numberText(ttyRecording.data?.total ?? selectedTtyGroup.tty_recording_count, language)} · {t('cowrieTtyLink')}</span></header>
      <div className="cowrie-tty-content">{ttyRecording.loading && !ttyRecording.data ? <p className="muted">{t('cowrieTtyLoading')}</p> : ttyRecording.error ? <p className="log-error">{t('cowrieTtyError')}</p> : ttyRecording.data ? <div className="cowrie-tty-recordings">{ttyRecording.data.items.map((recording) => <section className="cowrie-tty-recording" key={recording.event_id}><h3>{ttyDistinct ? t('cowrieTtyDistinct') : <>{t('honeypotSessionId')}: <code>{recording.session}</code></>}</h3><p className="muted">{recording.complete ? t('cowrieTtyComplete') : t('cowrieTtyLive')} · {numberText(recording.bytes_read, language)} {t('cowrieTtyBytes')}{ttyDistinct ? ` · ${t('cowrieTtyIdenticalCount').replace('{count}', numberText(recording.occurrences, language))}` : ''}</p><div className="cowrie-tty-transcript">{recording.chunks.length ? recording.chunks.map((chunk, index) => <div className={`cowrie-tty-line cowrie-tty-${chunk.kind}`} key={`${index}-${chunk.kind}`}><span>{t(chunk.kind === 'output' ? 'cowrieTtyOutput' : chunk.kind === 'input' ? 'cowrieTtyInput' : 'cowrieTtyCommand')}</span><pre>{chunk.text}</pre></div>) : <p>{t('cowrieTtyEmpty')}</p>}</div></section>)}</div> : <p className="muted">{t('cowrieTtyPending')}</p>}</div>
      {ttyRecording.data && <footer className="cowrie-tty-footer"><Paginator total={ttyRecording.data.total} pageIndex={ttyPage} pageSize={ttyPageSize} onPageChange={setTtyPage} onPageSizeChange={setTtyPageSize} pageSizes={[10, 25, 50]} t={t} language={language} /></footer>}
    </section></div></div>}
  </>
}

function HoneypotPage({ t, language, range, onRangeChange, lastImport, pageSize, onPageSizeChange, sort, onSortChange, filters, onFiltersChange, onGroupRequestsSelect }: PaginatedPageProps & { sort: HoneypotSort; onSortChange: (sort: HoneypotSort) => void; filters: HoneypotFilters; onFiltersChange: (filters: HoneypotFilters) => void; onGroupRequestsSelect: (group: HoneypotGroup) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [bodyView, setBodyView] = useState<PayloadView>('formatted')
  const [pendingSortColumn, setPendingSortColumn] = useState<HoneypotSortColumn | null>(null)
  const [sortRequestStarted, setSortRequestStarted] = useState(false)
  const [draftFilters, setDraftFilters] = useState<HoneypotFilters>(filters)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [payloadFrameHeight, setPayloadFrameHeight] = useState(180)
  const payloadAreaRef = useRef<HTMLDivElement>(null)
  const rawPayloadProbeRef = useRef<HTMLPreElement>(null)
  const formattedPayloadProbeRef = useRef<HTMLPreElement>(null)
  const [expandedGroup, setExpandedGroup] = useState<HoneypotGroup | null>(null)
  const [deletingGroup, setDeletingGroup] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const periodSummary = useApiData<HoneypotSummary>(apiUrl('honeypot/summary', range.query))
  const query = Object.fromEntries(Object.entries({
    search: filters.search.trim(), method: filters.postsOnly ? 'POST' : '', protected_only: filters.protectedOnly ? 'true' : '',
    sort_by: sort.column, sort_order: sort.direction,
    limit: String(pageSize), offset: String(pageIndex * pageSize),
  }).filter(([, value]) => value))
  const groups = useApiData<HoneypotGroupsResponse>(apiUrl('honeypot/groups', range.query, query))
  useEffect(() => {
    if (!pendingSortColumn) return
    if (groups.loading) setSortRequestStarted(true)
    else if (sortRequestStarted) {
      setPendingSortColumn(null)
      setSortRequestStarted(false)
    }
  }, [groups.loading, pendingSortColumn, sortRequestStarted])
  const groupEventsQuery = expandedGroup ? {
    ...(expandedGroup.client_ip === null ? {} : { client_ip: expandedGroup.client_ip }),
    from: expandedGroup.first_time, to: expandedGroup.last_time,
    ...(filters.postsOnly ? { method: 'POST' } : {}),
    ...(filters.search.trim() ? { search: filters.search.trim() } : {}),
  } : undefined
  const groupEvents = useApiData<HoneypotEventsResponse>(expandedGroup ? apiUrl('honeypot/group-events', undefined, groupEventsQuery) : null)
  const detail = useApiData<HoneypotEventDetail>(selectedId ? apiUrl(`honeypot/events/${selectedId}`) : null, false)
  useLayoutEffect(() => {
    const measure = () => {
      const raw = rawPayloadProbeRef.current
      const formatted = formattedPayloadProbeRef.current
      if (!raw || !formatted) return
      const height = Math.max(raw.scrollHeight, formatted.scrollHeight)
      setPayloadFrameHeight(Math.min(1440, Math.max(180, Math.ceil(height))))
    }
    measure()
    const area = payloadAreaRef.current
    if (!area || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(area)
    return () => observer.disconnect()
  }, [detail.data?.body_text, detail.data?.content_type, selectedId])
  const honeypotDetailItems = (groupEvents.data?.items ?? []).filter((item) => Boolean(item.has_body))
  const honeypotDetailIndex = selectedId ? honeypotDetailItems.findIndex((item) => item.event_id === selectedId) : -1
  const moveHoneypotDetail = (offset: number) => { const item = honeypotDetailItems[honeypotDetailIndex + offset]; if (item) setSelectedId(item.event_id) }
  useEffect(() => {
    if (!selectedId) return
    const root = document.documentElement
    const body = document.body
    const previousRootOverflow = root.style.overflow
    const previousBodyOverflow = body.style.overflow
    root.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setSelectedId(null) }
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      root.style.overflow = previousRootOverflow
      body.style.overflow = previousBodyOverflow
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [selectedId])
  const submittedFields = detail.data?.body_text && detail.data.content_type?.toLowerCase().includes('application/x-www-form-urlencoded')
    ? Array.from(new URLSearchParams(detail.data.body_text).entries())
    : []
  useEffect(() => { setPageIndex(0); setSelectedId(null); setExpandedGroup(null) }, [range.query, filters.search, filters.postsOnly, filters.protectedOnly, sort, pageSize])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); setSelectedId(null); setExpandedGroup(null); onFiltersChange(draftFilters) }
  const resetFilters = () => { setDraftFilters({ ...defaultHoneypotFilters }); setPageIndex(0); setSelectedId(null); setExpandedGroup(null); onFiltersChange({ ...defaultHoneypotFilters }) }
  const deleteGroup = async (group: HoneypotGroup) => {
    const actor = group.client_ip || '—'
    const confirmation = t('confirmHoneypotDeleteTestSession')
      .replace('{ip}', actor)
      .replace('{requests}', numberText(group.request_count, language))
    if (!window.confirm(confirmation)) return
    const key = `${group.client_ip ?? ''}-${group.first_time}`
    setDeletingGroup(key)
    setActionError('')
    try {
      const response = await apiFetch(apiUrl('honeypot/groups', undefined, {
        client_ip: group.client_ip ?? '', from: group.first_time, to: group.last_time,
      }), { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      if (expandedGroup?.client_ip === group.client_ip && expandedGroup.first_time === group.first_time) setExpandedGroup(null)
      groups.reload()
      periodSummary.reload()
    } catch {
      setActionError(t('honeypotDeleteTestSessionFailed'))
    } finally {
      setDeletingGroup(null)
    }
  }
  const changeSort = (column: HoneypotSortColumn) => {
    setPageIndex(0)
    setPendingSortColumn(column)
    setSortRequestStarted(false)
    onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' })
  }
  return <>
    <PageHeading title={t('honeypot')} subtitle={t('honeypotSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <section className="metric-grid honeypot-period-metrics">
      <MetricCard t={t} language={language} label={t('honeypotRequests')} value={periodSummary.error ? '—' : periodSummary.loading && !periodSummary.data ? '…' : numberText(periodSummary.data?.request_count ?? 0, language)} icon={Bug} iconClass="violet" caption={t('honeypotAccessesNote')} />
      <MetricCard t={t} language={language} label={t('honeypotUniqueActors')} value={periodSummary.error ? '—' : periodSummary.loading && !periodSummary.data ? '…' : numberText(periodSummary.data?.actor_count ?? 0, language)} icon={Users} iconClass="blue" caption={t('honeypotUniqueActorsNote')} />
      <MetricCard t={t} language={language} label={t('honeypotPostsWithData')} value={periodSummary.error ? '—' : periodSummary.loading && !periodSummary.data ? '…' : numberText(periodSummary.data?.post_with_data_count ?? 0, language)} icon={FileText} iconClass="green" caption={t('honeypotPostsWithDataNote')} />
      <MetricCard t={t} language={language} label={t('honeypotExecutionAttempts')} value={periodSummary.error ? '—' : periodSummary.loading && !periodSummary.data ? '…' : numberText(periodSummary.data?.uploaded_execution_attempt_count ?? 0, language)} icon={ShieldAlert} iconClass="amber" caption={t('honeypotExecutionAttemptsNote')} />
    </section>
    <p className="honeypot-grouping-hint">{t('honeypotGroupingHint')}</p>
    {actionError && <div className="log-error" role="alert">{actionError}</div>}
    <PageDataState loading={groups.loading} error={groups.error} retry={groups.reload} t={t} />
    <section className="panel table-panel honeypot-panel">
      <div className="filter-toolbar honeypot-toolbar">
        <label className="filter-search"><Search size={15} /><input type="search" value={draftFilters.search} placeholder={t('honeypotSearch')} aria-label={t('honeypotSearch')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label>
        <label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.postsOnly} onChange={(event) => setDraftFilters((value) => ({ ...value, postsOnly: event.target.checked }))} /><span>{t('honeypotPostsOnly')}</span></label>
        <label className="request-without-burst-filter"><input type="checkbox" checked={draftFilters.protectedOnly} onChange={(event) => setDraftFilters((value) => ({ ...value, protectedOnly: event.target.checked }))} /><span>{t('protectedIpsOnly')}</span></label>
        <button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button>
        <span className="honeypot-events-count">{t('honeypotSessions')}: {numberText(groups.data?.total ?? 0, language)} · {t('honeypotRequests')}: {numberText(groups.data?.total_events ?? 0, language)}</span>
      </div>
      <Paginator total={groups.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={(page) => { setPageIndex(page); setSelectedId(null); setExpandedGroup(null) }} onPageSizeChange={(size) => { onPageSizeChange(size); setPageIndex(0); setSelectedId(null); setExpandedGroup(null) }} t={t} language={language} />
      <div className="table-scroll" aria-busy={groups.loading && Boolean(groups.data)}><table className="honeypot-table"><thead><tr><SortableHeader column="time" label={t('dateTime')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'time' || (groups.loading && Boolean(groups.data) && sort.column === 'time')} /><SortableHeader column="client_ip" label={t('actor')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'client_ip' || (groups.loading && Boolean(groups.data) && sort.column === 'client_ip')} /><SortableHeader column="request_count" label={t('honeypotRequests')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'request_count' || (groups.loading && Boolean(groups.data) && sort.column === 'request_count')} /><SortableHeader column="path_count" label={t('honeypotPaths')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'path_count' || (groups.loading && Boolean(groups.data) && sort.column === 'path_count')} /><SortableHeader column="post_count" label={t('honeypotPostCount')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'post_count' || (groups.loading && Boolean(groups.data) && sort.column === 'post_count')} /><SortableHeader column="body_bytes" label={t('honeypotSize')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.postsOnly)} filterLabel={t('filteredColumn')} busy={pendingSortColumn === 'body_bytes' || (groups.loading && Boolean(groups.data) && sort.column === 'body_bytes')} /></tr></thead><tbody>
        {groups.data?.items.map((group) => {
          const expanded = expandedGroup?.client_ip === group.client_ip && expandedGroup.first_time === group.first_time
          return <Fragment key={`${group.client_ip}-${group.first_time}`}>
            <tr>
              <td><button type="button" className="table-link honeypot-time-link" aria-label={`${t('honeypotOpenRequests')}: ${requestDateTimeText(group.first_time, language)}`} onClick={() => onGroupRequestsSelect(group)}><span className="incident-time-cell"><strong>{requestDateTimeText(group.first_time, language)}</strong><small>{incidentDurationText(group.first_time, group.last_time, language)}</small></span></button></td>
              <td><span className="actor-detail"><span className="actor-ip-line"><MaintenanceExclusionToggle ip={group.client_ip} t={t} /><strong className="primary-cell">{group.client_ip || '—'}</strong></span><ActorMetadata provider={group.provider} asn={group.asn} country={group.country} city={group.city} /></span></td>
              <td><span className="honeypot-group-actions"><button type="button" className="table-link honeypot-group-toggle" aria-label={expanded ? t('honeypotCollapseGroup') : t('honeypotExpandGroup')} onClick={() => setExpandedGroup(expanded ? null : group)}>{expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{filters.postsOnly ? <>{numberText(group.post_count, language)} ({numberText(group.request_count, language)})</> : numberText(group.request_count, language)}</button><button type="button" className="icon-button honeypot-delete-session actor-delete-button" aria-label={t('honeypotDeleteTestSession')} title={t('honeypotDeleteTestSession')} disabled={deletingGroup === `${group.client_ip ?? ''}-${group.first_time}`} onClick={() => void deleteGroup(group)}><Trash2 size={14} /></button></span></td>
              <td>{numberText(group.path_count, language)}</td>
              <td><span className="honeypot-group-posts">{numberText(group.post_count, language)}<small>{numberText(group.body_count, language)} {t('honeypotData').toLowerCase()}</small></span></td>
              <td>{numberText(group.body_bytes, language)} B</td>
            </tr>
            {expanded && <tr className="honeypot-group-expanded"><td colSpan={6}><div className="honeypot-group-events">
              <PageDataState loading={groupEvents.loading} error={groupEvents.error} retry={groupEvents.reload} t={t} />
              {groupEvents.data && <div className="table-scroll"><table><thead><tr><th>{t('dateTime')}</th><th>{t('honeypotMethod')}</th><th>{t('honeypotPath')}</th><th>{t('honeypotRule')}</th><th>{t('honeypotPhase')}</th><th>{t('honeypotSize')}</th><th>{t('honeypotStatus')}</th><th>{t('honeypotPage')}</th><th>{t('honeypotData')}</th></tr></thead><tbody>
                {groupEvents.data.items.map((event) => <tr key={event.event_id}>
                  <td><span className="incident-time-cell"><strong>{requestDateTimeText(event.time, language)} . {timestampMillisText(event.time, language)}</strong><small>{elapsedDurationText(event.duration / 1_000_000, language)}</small></span></td>
                  <td><span className="method-cell">{event.scheme?.split(',', 1)[0].trim().toLowerCase() === 'https' ? <span className="https-lock" title="HTTPS" aria-label="HTTPS"><LockKeyhole size={13} /></span> : <span className="http-lock" title="HTTP" aria-label="HTTP"><LockOpen size={13} /></span>}<span className="method-badge">{event.method}</span></span></td>
                  <td className="honeypot-path"><code className="path-cell">{event.path}</code></td><td>{event.rule || '—'}</td><td>{honeypotPhaseText(event.session_phase, t)}</td><td>{numberText(event.body_bytes, language)} B</td>
                  <td><span className={`response-code ${(event.status ?? 0) < 400 ? 'response-success' : ''}`}>{event.status ?? '—'}</span></td><td>{event.response_page || '—'}</td>
                  <td>{event.has_body ? <button type="button" className="table-link honeypot-body-link" onClick={() => setSelectedId(event.event_id)}><FileText size={13} />{t('honeypotViewData')}</button> : '—'}</td>
                </tr>)}
              </tbody></table></div>}
            </div></td></tr>}
          </Fragment>
        })}
        {!groups.loading && groups.data?.items.length === 0 && <EmptyRows t={t} columns={6} />}
      </tbody></table></div>
      <Paginator total={groups.data?.total ?? 0} pageIndex={pageIndex} pageSize={pageSize} onPageChange={(page) => { setPageIndex(page); setSelectedId(null); setExpandedGroup(null) }} onPageSizeChange={(size) => { onPageSizeChange(size); setPageIndex(0); setSelectedId(null); setExpandedGroup(null) }} t={t} language={language} />
    </section>
    {selectedId && <div className="honeypot-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedId(null) }}><div className="honeypot-dialog-shell"><div className="honeypot-dialog-controls"><button type="button" className="icon-button" onClick={() => setSelectedId(null)} aria-label={t('close')} title={t('close')}><X size={16} /></button><button type="button" className="icon-button" onClick={() => moveHoneypotDetail(-1)} disabled={honeypotDetailIndex <= 0} aria-label={t('previousRecord')} title={t('previousRecord')}><ChevronUp size={16} /></button><button type="button" className="icon-button" onClick={() => moveHoneypotDetail(1)} disabled={honeypotDetailIndex < 0 || honeypotDetailIndex >= honeypotDetailItems.length - 1} aria-label={t('nextRecord')} title={t('nextRecord')}><ChevronDown size={16} /></button></div><section className="panel honeypot-detail honeypot-detail-dialog" id="honeypot-event-details" role="dialog" aria-modal="true" aria-labelledby="honeypot-details-title"><div className="panel-header"><h2 id="honeypot-details-title">{t('honeypotDetails')}</h2></div>
      <PageDataState loading={detail.loading} error={detail.error} retry={detail.reload} t={t} />
      {detail.data && <><dl className="honeypot-meta"><dt>{t('dateTime')}</dt><dd>{dateText(detail.data.time, language)}</dd><dt>{t('actor')}</dt><dd><span className="actor-detail"><strong className="primary-cell">{detail.data.client_ip || '—'}</strong><ActorMetadata provider={detail.data.provider} asn={detail.data.asn} country={detail.data.country} city={detail.data.city} /></span></dd><dt>{t('host')}</dt><dd>{detail.data.host || '—'}</dd><dt>{t('honeypotSessionId')}</dt><dd>{detail.data.session_id || '—'}</dd><dt>{t('honeypotPhase')}</dt><dd>{honeypotPhaseText(detail.data.session_phase, t)}</dd><dt>{t('honeypotAgent')}</dt><dd>{detail.data.user_agent || '—'}</dd><dt>Content-Type</dt><dd>{detail.data.content_type || '—'}</dd><dt>SHA-256</dt><dd>{detail.data.body_sha256 || '—'}</dd></dl>
        <h3>{t('honeypotBody')}</h3>
        {submittedFields.length > 0 && <><h3>{t('honeypotFields')}</h3><dl className="honeypot-meta">{submittedFields.map(([key, value], index) => <Fragment key={`${key}-${index}`}><dt>{key}</dt><dd>{value}</dd></Fragment>)}</dl></>}
        {detail.data.body_text !== null && <div className="payload-view-toolbar"><PayloadViewTabs view={bodyView} onChange={setBodyView} t={t} /><CopyPayloadButton text={bodyView === 'raw' ? detail.data.body_text : formatMultipartPayloadText(detail.data.body_text, detail.data.content_type, t)} t={t} /></div>}
        {detail.data.body_text !== null ? (() => {
          const bodyText = detail.data.body_text
          const formattedText = formatMultipartPayloadText(bodyText, detail.data.content_type, t)
          const parts = bodyText ? parseHoneypotMultipart(bodyText, detail.data.content_type) : []
          const formattedParts = parts.map((part) => formatPayloadText(part.body, t))
          return <div className="honeypot-payload-area" ref={payloadAreaRef}>
            {bodyView === 'raw'
              ? <PayloadText body={bodyText} view="raw" t={t} height={payloadFrameHeight} />
              : !parts.length
                ? <PayloadText body={bodyText || t('honeypotBodyMissing')} view="formatted" t={t} height={payloadFrameHeight} />
                : <pre style={{ height: payloadFrameHeight }} className="honeypot-body honeypot-body-modal payload-format-view">{parts.map((part, index) => <Fragment key={`${part.name}-${index}`}><span className="payload-part-heading">{part.name || `${t('honeypotFields')} ${index + 1}`}\n{part.headers.join('\n')}\n\n</span><FormattedPayloadContent formatted={formattedParts[index]} t={t} />{index < parts.length - 1 ? '\n\n────────────────────────────────────────\n\n' : ''}</Fragment>)}</pre>}
            <pre ref={rawPayloadProbeRef} className="honeypot-body honeypot-body-modal payload-measure-probe">{bodyText}</pre>
            <pre ref={formattedPayloadProbeRef} className="honeypot-body honeypot-body-modal payload-format-view payload-measure-probe">{formattedText}</pre>
          </div>
        })() : detail.data.body_base64 ? <><p>{t('honeypotBodyBinary')}</p><pre className="honeypot-body honeypot-body-modal">{detail.data.body_base64}</pre></> : <p>{t('honeypotBodyMissing')}</p>}
        {Boolean(detail.data.body_clipped) && <p className="honeypot-clipped">{t('honeypotTruncated')}</p>}
      </>}
    </section></div></div>}
  </>
}

function LoggingPage({ t }: { t: (key: MessageKey) => string }) {
  const [service, setService] = useState<LogService>('collector')
  const services: { key: LogService; label: MessageKey }[] = [
    { key: 'collector', label: 'logCollector' },
    { key: 'api', label: 'logApi' },
    { key: 'ui_access', label: 'logUiAccess' },
    { key: 'ui_error', label: 'logUiErrors' },
  ]
  return <>
    <div className="page-heading"><div><h1>{t('logging')}</h1><p>{t('loggingSubtitle')}</p></div></div>
    <section className="panel log-panel">
      <div className="log-tabs" role="tablist" aria-label={t('logging')}>
        {services.map((entry) => <button key={entry.key} type="button" role="tab" aria-selected={service === entry.key} className={`log-tab${service === entry.key ? ' active' : ''}`} onClick={() => setService(entry.key)}>{t(entry.label)}</button>)}
      </div>
      <LogServicePanel key={service} service={service} t={t} />
    </section>
  </>
}

function LogServicePanel({ service, t }: { service: LogService; t: (key: MessageKey) => string }) {
  const logs = useApiData<LogResponse>(apiUrl('logs', undefined, { service, limit: '4000' }), false)
  const [wrapLines, setWrapLines] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [actionError, setActionError] = useState('')
  const viewer = useRef<HTMLPreElement | null>(null)

  useEffect(() => {
    const element = viewer.current
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 100) {
      element.scrollTop = element.scrollHeight
    }
  }, [logs.data?.content])

  const reset = async () => {
    if (!window.confirm(t('confirmLogReset'))) return
    setResetting(true)
    setActionError('')
    try {
      const response = await apiFetch(apiUrl('logs', undefined, { service }), { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      logs.reload()
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : t('apiError'))
    } finally {
      setResetting(false)
    }
  }

  return <>
    <div className="log-options">
      <label className="log-wrap-toggle"><input type="checkbox" checked={wrapLines} onChange={(event) => setWrapLines(event.target.checked)} />{t('logWrapLines')}</label>
      <button type="button" className="filter-button" onClick={logs.reload}>{t('logRefresh')}</button>
      <button type="button" className="filter-button log-reset" disabled={resetting} onClick={reset}>{resetting ? t('loadingData') : t('logReset')}</button>
    </div>
    {actionError && <div className="log-error" role="alert">{actionError}</div>}
    <div className="log-status" aria-live="polite">{logs.error ? `${t('apiError')}: ${logs.error}` : logs.data?.truncated ? t('logTruncated') : ''}</div>
    <pre ref={viewer} className={`log-viewer${wrapLines ? ' wrap-lines' : ''}`}>{logs.data?.content || (logs.loading ? t('loadingData') : t('logEmpty'))}</pre>
  </>
}

function AdministrationPage({ t, language }: { t: (key: MessageKey) => string; language: Language }) {
  const status = useApiData<StatusData>(apiUrl('status'))
  const controller = useRef<AbortController | null>(null)
  const [pending, setPending] = useState<'import' | 'maintenance' | null>(null)
  const [operationMessage, setOperationMessage] = useState('')
  const [operationError, setOperationError] = useState('')
  const collector = status.data?.collector_status
  const busy = Boolean(pending || (collector?.activity && collector.activity !== 'Idle'))

  useEffect(() => () => controller.current?.abort(), [])
  const runOperation = async (operation: 'import' | 'maintenance') => {
    if (operation === 'maintenance') {
      const retentionDays = status.data?.environment?.MAINTENANCE_LOG_RETENTION_DAYS || '14'
      const confirmation = retentionDays.trim() === '0'
        ? t('confirmMaintenanceCleanupDisabled')
        : t('confirmMaintenanceCleanup').replace('{days}', retentionDays)
      if (!window.confirm(confirmation)) return
    }
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    setPending(operation)
    setOperationMessage('')
    setOperationError('')
    try {
      const response = await apiFetch(apiUrl(operation), { method: 'PUT', signal: nextController.signal })
      const body = await response.json().catch(() => ({})) as { status?: string; activity?: string; detail?: string; error?: { message?: string } }
      if (!response.ok) throw new Error(body.error?.message || body.detail || `HTTP ${response.status}`)
      setOperationMessage(operation === 'import' ? t('importAccepted') : t('maintenanceAccepted'))
      if (operation === 'import') window.dispatchEvent(new Event('inm2-collector-import'))
      status.reload()
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setOperationError(reason instanceof Error ? reason.message : t('operationFailed'))
    } finally {
      if (!nextController.signal.aborted) setPending(null)
    }
  }

  const environment = Object.fromEntries(Object.entries(status.data?.environment ?? {}).filter(([name]) =>
    name !== 'INM2_COLLECTOR_PORT' && !/(SECRET|PASSWORD|TOKEN)/i.test(name),
  ))
  const configRows = (keys: [string, MessageKey][]) => keys.map(([name, hint]) => [name, environment[name] || '—', t(hint)])
  const retentionDays = Number(environment.MAINTENANCE_LOG_RETENTION_DAYS || 14)
  const importIntervalSeconds = Number(environment.INPUT_INTERVAL_SECONDS || 3600)
  const retentionCycleWarning = retentionDays > 0 && Number.isFinite(importIntervalSeconds) && retentionDays * 86400 < importIntervalSeconds
  const importedFiles = collector?.last_import_files?.length
    ? collector.last_import_files
    : collector?.last_import_file ? [{ file: collector.last_import_file, count: collector.import_count }] : []
  const maintenanceRows = configRows([['MAINTENANCE_INTERVAL_DAYS', 'daysUnit'], ['MAINTENANCE_INACTIVE_DAYS', 'daysUnit'], ['MAINTENANCE_LOG_RETENTION_DAYS', retentionCycleWarning ? 'maintenanceCycleWarning' : 'daysUnit']])
  if (retentionCycleWarning) maintenanceRows[2].push('warning')
  const formatActivity = (activity?: string) => activityText(activity, t)
  return <>
    <div className="page-heading admin-page-heading"><div><h1>{t('administration')}</h1><p>{t('adminSubtitle')}</p></div></div>
    <PageDataState loading={status.loading && !status.data} error={status.data ? null : status.error} retry={status.reload} t={t} />
    {!status.loading && (!status.error || status.data) && <>
      <section className={`admin-health-grid${status.data?.cowrie_configured ? ' has-cowrie' : ''}`}>
        <HealthCard icon={Activity} label={t('collector')} status={formatActivity(collector?.activity)} detail={collector?.available ? t('collectorAvailable') : t('collectorUnavailable')} healthy={collector?.available === true} />
        <HealthCard icon={Globe2} label={t('api')} status={status.data?.status === 'ok' ? t('connected') : t('degraded')} detail={status.data?.status === 'ok' ? t('apiConnected') : t('apiUnavailable')} healthy={status.data?.status === 'ok'} />
        <HealthCard icon={Database} label={t('database')} status={status.data?.database === 'ok' ? t('operational') : t('degraded')} detail={status.data?.database === 'ok' ? t('databaseConnected') : t('apiUnavailable')} healthy={status.data?.database === 'ok'} />
        {status.data?.honeypot_configured && <HealthCard icon={Bug} label={t('honeypot')} status={status.data.honeypot_available ? t('operational') : t('notStarted')} detail={status.data.honeypot_available ? t('connected') : t('honeypotNotRunning')} healthy={status.data.honeypot_available === true} />}
        {status.data?.cowrie_configured && <HealthCard icon={Network} label={t('cowrie')} status={status.data.cowrie_available ? t('operational') : t('notStarted')} detail={status.data.cowrie_available ? t('cowrieLogAvailable') : t('cowrieLogUnavailable')} healthy={status.data.cowrie_available} />}
      </section>
      <section className="panel admin-activity-panel">
        <div className="admin-section-heading"><div><h2>{t('collectorActivity')}</h2><p>{t('collectorActivityHint')}</p></div></div>
        <div className="admin-import-table-wrap"><table className="admin-import-table"><thead><tr><th>{t('lastImport')}</th><th>{t('importFile')}</th><th>{t('importCount')}</th></tr></thead><tbody>{importedFiles.length ? importedFiles.map((item, index) => <tr key={`${item.file}-${index}`}><td>{index === 0 ? dateText(collector?.last_import, language) : ''}</td><td>{item.file}</td><td>{numberText(item.count, language)}</td></tr>) : <tr><td>{dateText(collector?.last_import, language)}</td><td>—</td><td>—</td></tr>}</tbody></table></div>
      </section>
      <section className="admin-actions-grid">
        <AdminAction icon={ArrowDownRight} title={t('manualImport')} description={t('manualImportHint')} actionLabel={pending === 'import' ? t('starting') : t('startImport')} onClick={() => void runOperation('import')} disabled={busy} />
        <AdminAction icon={Settings2} title={t('manualMaintenance')} description={t('manualMaintenanceHint')} actionLabel={pending === 'maintenance' ? t('starting') : t('startMaintenance')} onClick={() => void runOperation('maintenance')} disabled={busy} />
      </section>
      {(operationMessage || operationError) && <div className={`operation-message ${operationError ? 'operation-error' : ''}`}>{operationError || operationMessage}</div>}
      <section className="panel admin-config-panel">
        <div className="admin-section-heading"><div><h2>{t('effectiveEnvironment')}</h2><p>{t('effectiveEnvironmentHint')}</p></div><span className="readonly-tag"><ShieldAlert size={13} />{t('readOnly')}</span></div>
        <div className="config-groups">
          <ConfigGroup title={t('serverSettings')} rows={configRows([['INM2_UI_PORT', 'webPort'], ['INM2_API_PORT', 'apiPort'], ['INPUT_LOG_DIR', 'inputLogDirectory'], ['GEOLITE_DB_DIR', 'geoDatabaseDirectory']])} />
          <ConfigGroup title={t('securitySettings')} rows={configRows([['INM2_COOKIE_SECURE', 'secureCookie'], ['INM2_TOTP_ENABLED', 'totpEnabled']])} />
          {status.data?.honeypot_configured && <ConfigGroup title={t('honeypot')} rows={configRows([['HONEYPOT_ENABLED', 'honeypotEnabledSetting'], ['HONEYPOT_HOST', 'honeypotHostSetting'], ['TRAEFIK_DOCKER_NETWORK', 'honeypotNetworkSetting'], ['HONEYPOT_HTTP_ENTRYPOINT', 'honeypotHttpEntryPointSetting'], ['HONEYPOT_ENTRYPOINT', 'honeypotHttpsEntryPointSetting'], ['HONEYPOT_CERT_RESOLVER', 'honeypotCertResolverSetting'], ['HONEYPOT_UID', 'honeypotUidSetting'], ['HONEYPOT_GID', 'honeypotGidSetting']])} />}
          <ConfigGroup title={t('cowrie')} rows={configRows([['COWRIE_ENABLED', 'cowrieEnabledSetting'], ['COWRIE_LOG_PATH', 'cowrieLogPathSetting']])} />
          <ConfigGroup title={t('importSettings')} rows={configRows([['LOG_FILES', 'inputFiles'], ['INPUT_INTERVAL_SECONDS', 'secondsUnit'], ['INPUT_SAVE_MARGIN_CHARACTERS', 'charactersUnit'], ['IGNORE_REQUEST_ROUTES', 'ignoreRequestRoutesHint'], ['KNOWN_HOSTS', 'knownHostsHint']])} />
          <ConfigGroup title={t('maintenanceSettings')} rows={maintenanceRows} />
          <ConfigGroup title={t('burstSettings')} rows={configRows([['BURST_MAX_GAP_SECONDS', 'secondsUnit'], ['BURST_MIN_REQUESTS', 'requestsUnit'], ['BURST_WINDOW_SECONDS', 'secondsUnit']])} />
          <ConfigGroup title={t('incidentMergeSettings')} rows={configRows([['INCIDENT_MERGE_OVERLAP_PERCENT', 'incidentMergeOverlapPercent']])} />
          <ConfigGroup title={t('lowSlowScanSettings')} rows={configRows([['LOW_SLOW_SCAN_WINDOW_SECONDS', 'secondsUnit'], ['LOW_SLOW_SCAN_MIN_PATHS', 'pathsUnit'], ['LOW_SLOW_SCAN_MIN_HOSTS', 'hostsUnit'], ['LOW_SLOW_SCAN_MIN_SPAN_SECONDS', 'secondsUnit']])} />
          <ConfigGroup title={t('geoSettings')} rows={configRows([['GEOLITE_CITY_DB', 'localDatabasePath'], ['GEOLITE_ASN_DB', 'localDatabasePath']])} />
        </div>
        <div className="config-note"><CircleHelp size={15} /><span>{t('environmentRestartNote')}</span></div>
      </section>
    </>}
  </>
}

function HealthCard({ icon: Icon, label, status, detail, healthy, neutral = false }: { icon: typeof Activity; label: string; status: string; detail: string; healthy: boolean; neutral?: boolean }) {
  return <div className="panel health-card"><div className="health-card-icon"><Icon size={17} /></div><div className="health-card-body"><span>{label}</span><strong><i className={neutral ? 'offline-dot neutral-dot' : healthy ? '' : 'offline-dot'} />{status}</strong><small>{detail}</small></div><span className={`health-card-check ${neutral ? 'system-check-neutral' : healthy ? '' : 'system-check-error'}`}>{neutral ? '–' : healthy ? '✓' : '!'}</span></div>
}

function AdminAction({ icon: Icon, title, description, actionLabel, onClick, disabled }: { icon: typeof Activity; title: string; description: string; actionLabel: string; onClick: () => void; disabled: boolean }) {
  return <div className="panel admin-action-card"><div className="admin-action-icon"><Icon size={17} /></div><div className="admin-action-copy"><div className="admin-action-title"><h2>{title}</h2></div><p>{description}</p><button className="admin-action-button" onClick={onClick} disabled={disabled}>{actionLabel}<ArrowUpRight size={14} /></button></div></div>
}

function ConfigGroup({ title, rows }: { title: string; rows: string[][] }) {
  return <div className="config-group"><h3>{title}</h3>{rows.map(([name, value, hint]) => <div className={`config-row ${name === 'MAINTENANCE_LOG_RETENTION_DAYS' && rows.some((row) => row[0] === name && row[3] === 'warning') ? 'config-row-warning' : ''}`} key={name}><div><strong>{name}</strong><span>{hint}</span></div><code>{value}</code></div>)}</div>
}

function AdminLogin({ onLogin, sessionCheckFailed = false, totpRequired = false }: { onLogin: () => void; sessionCheckFailed?: boolean; totpRequired?: boolean }) {
  const loginFormRef = useRef<HTMLFormElement>(null)
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const german = navigator.language.toLowerCase().startsWith('de')
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPending(true)
    setError('')
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ password, totp_code: totpCode }),
      })
      if (!response.headers.get('content-type')?.includes('application/json')) {
        const finalPath = new URL(response.url).pathname
        const responseDescription = response.redirected ? (german ? 'umgeleitet' : 'redirected') : (german ? 'ohne JSON-Antwort' : 'without a JSON response')
        setError(german
          ? `Die API-Anfrage wurde ${responseDescription} (HTTP ${response.status}, Ziel ${finalPath}). Zu prüfen ist, ob /api/v1/auth/login direkt die API erreicht.`
          : `The API request was ${responseDescription} (HTTP ${response.status}, destination ${finalPath}). Check that /api/v1/auth/login reaches the API directly.`)
        return
      }
      if (!response.ok) {
        setError(response.status === 429 ? (german ? 'Zu viele Versuche. Bitte später erneut versuchen.' : 'Too many attempts. Please try again later.') : response.status === 401 ? (german ? (totpRequired ? 'Passwort oder Authenticator-Code ist nicht korrekt.' : 'Das Passwort ist nicht korrekt.') : (totpRequired ? 'The password or authenticator code is incorrect.' : 'The password is incorrect.')) : (german ? 'Anmeldung derzeit nicht möglich.' : 'Sign-in is currently unavailable.'))
        return
      }
      const result = await response.json() as { authenticated?: boolean }
      if (!result.authenticated) {
        setError(german ? 'Die Anmeldung wurde nicht bestätigt.' : 'The sign-in was not confirmed.')
        return
      }
      setPassword('')
      setTotpCode('')
      onLogin()
    } catch {
      setError(german ? 'Die API ist momentan nicht erreichbar.' : 'The API is currently unavailable.')
    } finally {
      setPending(false)
    }
  }
  return (
    <main className="auth-screen">
      <div className="auth-card">
        <form ref={loginFormRef} id="admin-login-form" onSubmit={submit} autoComplete="on">
          <div className="auth-brand"><span><Activity size={20} /></span><strong>INM<span>2</span></strong></div>
          <h1>{german ? 'Anmelden' : 'Sign in'}</h1>
          <p>{german ? 'Admin-Passwort eingeben, um fortzufahren.' : 'Enter the admin password to continue.'}</p>
          {sessionCheckFailed && <div className="auth-error" role="status">{german ? 'Der Sitzungsstatus konnte nicht geprüft werden. Eine Anmeldung ist trotzdem möglich.' : 'The session could not be checked. Sign-in is still available.'}</div>}
          <label htmlFor="admin-password">{german ? 'Passwort' : 'Password'}</label>
          <input id="admin-password" name="password" type="password" autoComplete="current-password" required minLength={1} maxLength={1024} value={password} onChange={(event) => setPassword(event.target.value)} autoFocus />
        </form>
        {totpRequired && <><label htmlFor="admin-totp" className="auth-totp-label">{german ? 'Authenticator-Code' : 'Authenticator code'}</label><div className="auth-code-field"><div className="auth-code-digits" aria-hidden="true">{Array.from({ length: 6 }, (_, index) => <span key={index}>{totpCode[index] ?? ''}</span>)}</div><input id="admin-totp" className="auth-code-input" type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={totpCode} aria-label={german ? 'Sechsstelliger Authenticator-Code' : 'Six-digit authenticator code'} onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, '').slice(0, 6))} onKeyDown={(event) => { if (event.key === 'Backspace' && totpCode) { event.preventDefault(); setTotpCode((code) => code.slice(0, -1)) } else if (event.key === 'Enter' && password && (!totpRequired || totpCode.length === 6)) { event.preventDefault(); loginFormRef.current?.requestSubmit() } }} onPaste={(event) => { const pastedCode = event.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6); if (pastedCode) { event.preventDefault(); setTotpCode(pastedCode) } }} /></div></>}
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button className="auth-submit" form="admin-login-form" type="submit" disabled={pending || !password || (totpRequired && totpCode.length !== 6)}>{pending ? (german ? 'Wird angemeldet …' : 'Signing in …') : (german ? 'Anmelden' : 'Sign in')}</button>
      </div>
    </main>
  )
}

function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)
  const [sessionError, setSessionError] = useState(false)
  const [totpRequired, setTotpRequired] = useState(false)
  const german = navigator.language.toLowerCase().startsWith('de')
  useEffect(() => {
    let active = true
    fetch('/api/v1/auth/session', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<{ authenticated: boolean; totp_required?: boolean }>
      })
      .then((result) => { if (active) { setTotpRequired(Boolean(result.totp_required)); setAuthenticated(result.authenticated) } })
      .catch(() => { if (active) { setSessionError(true); setTotpRequired(true); setAuthenticated(false) } })
    const expired = () => setAuthenticated(false)
    window.addEventListener('inm2-auth-expired', expired)
    return () => { active = false; window.removeEventListener('inm2-auth-expired', expired) }
  }, [])
  useEffect(() => {
    if (!authenticated) return
    const activityEvents: Array<keyof DocumentEventMap> = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']
    let lastActivityPing = Date.now()
    let requestInFlight = false
    const reportActivity = () => {
      const now = Date.now()
      if (requestInFlight || now - lastActivityPing < 60_000) return
      lastActivityPing = now
      requestInFlight = true
      fetch('/api/v1/auth/activity', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then((response) => {
          if (response.status === 401) window.dispatchEvent(new Event('inm2-auth-expired'))
        })
        .catch(() => undefined)
        .finally(() => { requestInFlight = false })
    }
    for (const eventName of activityEvents) document.addEventListener(eventName, reportActivity, { passive: true })
    return () => {
      for (const eventName of activityEvents) document.removeEventListener(eventName, reportActivity)
    }
  }, [authenticated])
  const logout = async () => {
    try { await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'same-origin' }) } finally { setAuthenticated(false) }
  }
  if (authenticated === null) return <div className="preferences-loading">{german ? 'Verbindung wird geprüft …' : 'Checking connection …'}</div>
  if (!authenticated) return <AdminLogin sessionCheckFailed={sessionError} totpRequired={totpRequired} onLogin={() => { setSessionError(false); setAuthenticated(true) }} />
  return <DashboardApp onLogout={logout} />
}

export default App
