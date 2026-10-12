import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react'
import {
  Activity, ArrowDown, ArrowDownRight, ArrowUp, ArrowUpRight, Bell, Blocks, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, CircleHelp,
  Clock3, Command, Database, FileText, Globe2, LayoutDashboard, ListFilter, LockKeyhole, LockOpen, Menu,
  Network, Search, Settings2, ShieldAlert, SkipBack, SkipForward, Sun, Users, X,
} from 'lucide-react'
import { messages, type Language, type MessageKey } from './i18n'

type Theme = 'auto' | 'cloud' | 'midnight' | 'moss'
type PageKey = 'dashboard' | 'bursts' | 'actors' | 'hosts' | 'categories' | 'requests' | 'administration'
type BurstSortColumn = 'start_time' | 'actor_ip' | 'host' | 'country' | 'duration' | 'requests' | 'avg_count'
type BurstSort = { column: BurstSortColumn; direction: 'asc' | 'desc' }
type BurstFilters = { search: string; host: string; country: string }
type ActorSortColumn = 'ip' | 'first_time' | 'last_time' | 'provider' | 'asn' | 'city' | 'country' | 'request_count'
type ActorSort = { column: ActorSortColumn; direction: 'asc' | 'desc' }
type ActorFilters = { search: string; country: string }
type HostSortColumn = 'host' | 'total_count' | 'read_count' | 'write_count' | 'other_count' | 'https_count' | 'https_share'
type HostSort = { column: HostSortColumn; direction: 'asc' | 'desc' }
type HostFilters = { search: string }
type CategorySortColumn = 'category_name' | 'total_count' | 'read_count' | 'write_count' | 'other_count' | 'traffic_share' | 'https_share'
type CategorySort = { column: CategorySortColumn; direction: 'asc' | 'desc' }
type CategoryFilters = { search: string }
type RequestSortColumn = 'start_utc' | 'request_method' | 'request_path' | 'downstream_status' | 'actor_ip' | 'host' | 'duration' | 'downstream_content_size'
type RequestSort = { column: RequestSortColumn; direction: 'asc' | 'desc' }
type RequestFilters = { search: string; status: '' | '2xx' | '3xx' | '4xx' | '5xx' }
const defaultBurstSort: BurstSort = { column: 'start_time', direction: 'asc' }
const defaultBurstFilters: BurstFilters = { search: '', host: '', country: '' }
const defaultActorSort: ActorSort = { column: 'first_time', direction: 'asc' }
const defaultActorFilters: ActorFilters = { search: '', country: '' }
const defaultHostSort: HostSort = { column: 'total_count', direction: 'desc' }
const defaultHostFilters: HostFilters = { search: '' }
const defaultCategorySort: CategorySort = { column: 'category_name', direction: 'asc' }
const defaultCategoryFilters: CategoryFilters = { search: '' }
const defaultRequestSort: RequestSort = { column: 'start_utc', direction: 'desc' }
const defaultRequestFilters: RequestFilters = { search: '', status: '' }
const tablePageSize = 30

const navigation: { key: PageKey; icon: typeof LayoutDashboard }[] = [
  { key: 'dashboard', icon: LayoutDashboard }, { key: 'bursts', icon: Activity },
  { key: 'actors', icon: Users }, { key: 'hosts', icon: Globe2 },
  { key: 'categories', icon: Blocks }, { key: 'requests', icon: FileText },
]

type RangePreset = 'last24h' | 'today' | 'yesterday' | 'last6h' | 'last7d' | 'last30d' | 'last90d' | 'custom'
type TimeRange = { from: Date; to: Date; preset: RangePreset; query: string }
type UiPreferences = { language?: Language; theme?: Theme; timeRange?: { preset: RangePreset; from?: string; to?: string }; burstSort?: BurstSort; burstFilters?: BurstFilters; actorSort?: ActorSort; actorFilters?: ActorFilters; hostSort?: HostSort; hostFilters?: HostFilters; categorySort?: CategorySort; categoryFilters?: CategoryFilters; requestSort?: RequestSort; requestFilters?: RequestFilters }
type ApiResult<T> = { items: T[]; total?: number; summary?: Record<string, number | null> }
type ActorItem = { actor_id: number; ip: string; first_time: string; last_time: string; provider: string | null; asn: string | null; city: string | null; country: string | null; request_count: number }
type BurstItem = { burst_id: number; actor_ip: string; country: string | null; provider: string | null; asn: string | null; city: string | null; host: string | null; start_time: string; end_time: string; avg_count: number; read_count: number; write_count: number; other_count: number }
type HostItem = { host_id: number; host: string; total_count: number; read_count: number; write_count: number; other_count: number; http_count: number; https_count: number; other_scheme_count: number }
type CategoryItem = { category_id: number; category_name: string; total_count: number; read_count: number; write_count: number; other_count: number; http_count: number; https_count: number; other_scheme_count: number }
type RequestItem = { request_id: number; start_utc: string; actor_ip: string; provider: string | null; asn: string | null; city: string | null; country: string | null; host: string | null; request_method: string; request_path: string; request_scheme: string; categories: string | null; downstream_status: number; downstream_content_size: number; duration: number }
type GlobalSearchActor = Pick<ActorItem, 'actor_id' | 'ip' | 'provider' | 'asn' | 'city' | 'country' | 'request_count'>
type GlobalSearchHost = Pick<HostItem, 'host_id' | 'host' | 'total_count'>
type GlobalSearchCategory = Pick<CategoryItem, 'category_id' | 'category_name' | 'total_count'>
type GlobalSearchResults = { actors: GlobalSearchActor[]; hosts: GlobalSearchHost[]; categories: GlobalSearchCategory[] }
type NotificationRequest = { request_id: number; start_utc: string; actor_ip: string; host: string | null; request_method: string; request_path: string; downstream_status: number | null }
type NotificationBurst = { burst_id: number; start_time: string; actor_ip: string; host: string | null; request_count: number }
type NotificationData = { request_count: number; burst_count: number; requests: NotificationRequest[]; bursts: NotificationBurst[]; request_cursor: number; burst_cursor: number }
type StatusData = { status: string; database: string; collector_status: { available: boolean; last_import: string | null; activity: string; import_file: string; last_import_file: string; import_count: number }; environment: Record<string, string> }
type BurstResponse = { summary: Record<string, number | null>; items: BurstItem[]; total?: number; limit: number; offset: number }
type CountItem = { read_count: number; write_count: number; other_count: number; total_count?: number; from?: string; to?: string }

let liveRefreshTick = 0
const liveRefreshListeners = new Set<() => void>()
function subscribeLiveRefresh(listener: () => void) { liveRefreshListeners.add(listener); return () => liveRefreshListeners.delete(listener) }
function getLiveRefreshTick() { return liveRefreshTick }
function triggerLiveRefresh() { liveRefreshTick += 1; liveRefreshListeners.forEach((listener) => listener()) }

let pendingApiRequests = 0
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

function makeRange(preset: RangePreset, start?: string, end?: string): TimeRange {
  const now = new Date()
  let from: Date
  let to = now
  if (preset === 'last24h') from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  else if (preset === 'today') from = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  else if (preset === 'yesterday') {
    to = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    from = new Date(to.getFullYear(), to.getMonth(), to.getDate() - 1)
  } else if (preset === 'last6h') from = new Date(now.getTime() - 6 * 60 * 60 * 1000)
  else if (preset === 'last7d') from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  else if (preset === 'last30d') from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
  else if (preset === 'last90d') from = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000)
  else {
    from = new Date(start ?? '')
    to = new Date(end ?? '')
  }
  const query = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() }).toString()
  return { from, to, preset, query }
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
    malaysia: 'MY', mexico: 'MX', netherlands: 'NL', norway: 'NO', pakistan: 'PK', poland: 'PL',
    portugal: 'PT', romania: 'RO', russia: 'RU', singapore: 'SG', slovakia: 'SK', slovenia: 'SI',
    'south africa': 'ZA', 'south korea': 'KR', spain: 'ES', sweden: 'SE', switzerland: 'CH',
    taiwan: 'TW', thailand: 'TH', turkey: 'TR', ukraine: 'UA', 'united kingdom': 'GB',
    'united states': 'US', 'united states of america': 'US', vietnam: 'VN',
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
  const code = /^[a-z]{2}$/i.test(country.trim()) ? country.trim().toUpperCase() : codeByName[normalized]
  if (!code) return '🌐'
  return String.fromCodePoint(...[...code].map((letter) => 127397 + letter.charCodeAt(0)))
}

function rangeLabel(range: TimeRange, t: (key: MessageKey) => string, language: Language) {
  const key: Partial<Record<RangePreset, MessageKey>> = { last24h: 'last24h', today: 'todayRange', yesterday: 'yesterdayRange', last6h: 'last6h', last7d: 'last7d', last30d: 'last30d', last90d: 'last90d' }
  if (range.preset !== 'custom') return t(key[range.preset] ?? 'last24h')
  const formatter = new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' })
  return `${formatter.format(range.from)} – ${formatter.format(range.to)}`
}

function rangeTick(range: TimeRange, fraction: number, language: Language) {
  const value = new Date(range.from.getTime() + (range.to.getTime() - range.from.getTime()) * fraction)
  const locale = language === 'de' ? 'de-DE' : 'en-GB'
  const options: Intl.DateTimeFormatOptions = range.to.getTime() - range.from.getTime() <= 24 * 60 * 60 * 1000
    ? { hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit' }
  return new Intl.DateTimeFormat(locale, options).format(value)
}

function useApiData<T>(url: string, pollIntervalMs = 0, showActivityToast = true) {
  const refreshTick = useSyncExternalStore(subscribeLiveRefresh, getLiveRefreshTick, getLiveRefreshTick)
  const previousRefreshTick = useRef(refreshTick)
  const scheduledRefresh = previousRefreshTick.current !== refreshTick
  previousRefreshTick.current = refreshTick
  const showToastForRequest = showActivityToast && !scheduledRefresh
  const [data, setData] = useState<T | null>(null)
  const dataRef = useRef<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let pollTimer: number | undefined
    let requestFinished = false
    const finishRequest = () => {
      if (!requestFinished) {
        requestFinished = true
        if (showToastForRequest) updatePendingApiRequests(-1)
      }
    }
    if (showToastForRequest) updatePendingApiRequests(1)
    if (dataRef.current === null) setLoading(true)
    setError(null)
    fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
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
          if (pollIntervalMs > 0) pollTimer = window.setTimeout(() => setReloadKey((key) => key + 1), pollIntervalMs)
        }
      })
    return () => { if (pollTimer !== undefined) window.clearTimeout(pollTimer); finishRequest(); controller.abort() }
  }, [url, reloadKey, pollIntervalMs, showToastForRequest, refreshTick])

  return { data, loading, error, reload: () => setReloadKey((key) => key + 1) }
}

function apiUrl(path: string, query?: string, extras?: Record<string, string>) {
  const params = new URLSearchParams(query ?? '')
  for (const [key, value] of Object.entries(extras ?? {})) params.set(key, value)
  return `/api/v1/${path}${params.size ? `?${params.toString()}` : ''}`
}

const preferenceGroup = 'ui_preferences'

function parsePreferences(items: { name: string; value: string | null }[]): UiPreferences {
  const values = Object.fromEntries(items.map(({ name, value }) => [name, value]))
  const preferences: UiPreferences = {}
  if (values.language === 'de' || values.language === 'en') preferences.language = values.language
  if (values.theme === 'auto' || values.theme === 'cloud' || values.theme === 'midnight' || values.theme === 'moss') preferences.theme = values.theme
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
      const columns: BurstSortColumn[] = ['start_time', 'actor_ip', 'host', 'country', 'duration', 'requests', 'avg_count']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.burstSort = parsed
    } catch { /* Ignore malformed saved sorting and use the default order. */ }
  }
  if (values.burst_filters) {
    try {
      const parsed = JSON.parse(values.burst_filters) as BurstFilters
      if (parsed && typeof parsed.search === 'string' && typeof parsed.host === 'string' && typeof parsed.country === 'string') preferences.burstFilters = parsed
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
      if (parsed && typeof parsed.search === 'string' && typeof parsed.country === 'string') preferences.actorFilters = parsed
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
      if (parsed && typeof parsed.search === 'string') preferences.hostFilters = parsed
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
      const columns: RequestSortColumn[] = ['start_utc', 'request_method', 'request_path', 'downstream_status', 'actor_ip', 'host', 'duration', 'downstream_content_size']
      if (parsed && columns.includes(parsed.column) && (parsed.direction === 'asc' || parsed.direction === 'desc')) preferences.requestSort = parsed
    } catch { /* Ignore malformed request sorting preferences. */ }
  }
  if (values.request_filters) {
    try {
      const parsed = JSON.parse(values.request_filters) as RequestFilters
      if (parsed && typeof parsed.search === 'string' && ['', '2xx', '3xx', '4xx', '5xx'].includes(parsed.status)) preferences.requestFilters = parsed
    } catch { /* Ignore malformed request filter preferences. */ }
  }
  return preferences
}

function numberText(value: number | null | undefined, language: Language) {
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US').format(value ?? 0)
}

function decimalText(value: number | null | undefined, language: Language) {
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(value ?? 0)
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

function secondsText(seconds: number | null | undefined, language: Language) {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const totalSeconds = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(totalSeconds / 60)
  const remaining = totalSeconds % 60
  return minutes ? `${minutes}${language === 'de' ? ' Min' : 'm'} ${remaining}${language === 'de' ? ' s' : 's'}` : `${remaining}${language === 'de' ? ' s' : 's'}`
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

function NotificationPopover({ data, t, language, onClose, onSelect }: { data: NotificationData | null; t: (key: MessageKey) => string; language: Language; onClose: () => void; onSelect: (item: { type: 'request' | 'burst'; id: number; actorIp: string }) => void }) {
  return <section className="notification-popover" aria-label={t('notifications')}>
    <header><strong>{t('notifications')}</strong><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={15} /></button></header>
    {!data ? <p className="notification-empty">{t('loadingData')}</p> : <>
      <p className="notification-summary">{numberText(data.request_count, language)} {t('newRequests')} · {numberText(data.burst_count, language)} {t('newBursts')}</p>
      {data.bursts.map((burst) => <button type="button" key={`burst-${burst.burst_id}`} className="notification-row" onClick={() => onSelect({ type: 'burst', id: burst.burst_id, actorIp: burst.actor_ip })}><span><strong>{t('newBurst')} · {burst.actor_ip}</strong><small>{burst.host || '—'} · {numberText(burst.request_count, language)} {t('requestsLabel')}</small></span><ArrowUpRight size={14} /></button>)}
      {data.requests.map((item) => <button type="button" key={`request-${item.request_id}`} className="notification-row" onClick={() => onSelect({ type: 'request', id: item.request_id, actorIp: item.actor_ip })}><span><strong>{item.request_method || 'GET'} {item.request_path || '/'}</strong><small>{item.actor_ip} · {item.host || '—'} · {dateText(item.start_utc, language)}</small></span><ArrowUpRight size={14} /></button>)}
      {data.request_count + data.burst_count === 0 && <p className="notification-empty">{t('noNewNotifications')}</p>}
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

function App() {
  const [language, setLanguage] = useState<Language>('de')
  const [theme, setTheme] = useState<Theme>('midnight')
  const [systemPrefersDark, setSystemPrefersDark] = useState(() => typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const activeTheme: Exclude<Theme, 'auto'> = theme === 'auto' ? (systemPrefersDark ? 'midnight' : 'cloud') : theme
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [notificationData, setNotificationData] = useState<NotificationData | null>(null)
  const [notificationSnapshot, setNotificationSnapshot] = useState<NotificationData | null>(null)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [activePage, setActivePage] = useState<PageKey>('dashboard')
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
  const [selectedBurstId, setSelectedBurstId] = useState<number | null>(null)
  const [selectedActorIp, setSelectedActorIp] = useState<string | null>(null)
  const [selectedHost, setSelectedHost] = useState<string | null>(null)
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [preferencesLoaded, setPreferencesLoaded] = useState(false)
  const [preferencesError, setPreferencesError] = useState(false)
  const preferenceSaves = useRef<Record<string, AbortController>>({})
  const searchInputRef = useRef<HTMLInputElement>(null)
  const t = (key: MessageKey) => messages[language][key]
  const liveStatus = useApiData<StatusData>(apiUrl('status'), 10_000, false)

  useEffect(() => {
    if (range.preset !== 'last24h') return
    const configuredSeconds = Number(liveStatus.data?.environment.INPUT_INTERVAL_SECONDS)
    const intervalMs = Number.isFinite(configuredSeconds) && configuredSeconds > 0 ? configuredSeconds * 1000 : 3_600_000
    const timer = window.setInterval(() => {
      setRange(makeRange('last24h'))
      triggerLiveRefresh()
    }, intervalMs)
    return () => window.clearInterval(timer)
  }, [range.preset, liveStatus.data?.environment.INPUT_INTERVAL_SECONDS])

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
    fetch(apiUrl('params', undefined, { group_name: preferenceGroup }), { signal: controller.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (response.status === 404) return null
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<{ items: { name: string; value: string | null }[] }>
      })
      .then((result) => {
        if (!result || controller.signal.aborted) return
        const saved = parsePreferences(result.items)
        if (saved.language) setLanguage(saved.language)
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
      .finally(() => { if (!controller.signal.aborted) setPreferencesLoaded(true) })
    return () => controller.abort()
  }, [])

  useEffect(() => () => Object.values(preferenceSaves.current).forEach((controller) => controller.abort()), [])

  useEffect(() => {
    if (!preferencesLoaded) return
    let timer: number | undefined
    let stopped = false
    let controller: AbortController | null = null
    const poll = () => {
      controller = new AbortController()
      fetch(apiUrl('notifications'), { signal: controller.signal, headers: { Accept: 'application/json' } })
        .then(async (response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json() as Promise<NotificationData> })
        .then((result) => { if (!stopped) setNotificationData(result) })
        .catch(() => { /* Keep the last known notification state during temporary API failures. */ })
        .finally(() => { if (!stopped) timer = window.setTimeout(poll, 10_000) })
    }
    poll()
    return () => { stopped = true; if (timer !== undefined) window.clearTimeout(timer); controller?.abort() }
  }, [preferencesLoaded])

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
    fetch(apiUrl('params', undefined, { group_name: preferenceGroup, name, value }), { method: 'PUT', signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error(`HTTP ${response.status}`) })
      .then(() => { if (!controller.signal.aborted) setPreferencesError(false) })
      .catch(() => { if (!controller.signal.aborted) setPreferencesError(true) })
      .finally(() => { if (preferenceSaves.current[name] === controller) delete preferenceSaves.current[name] })
  }

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

  if (!preferencesLoaded) return <div className="preferences-loading">{messages.de.loadingPreferences}</div>

  return (
    <div className="app-shell" data-theme={activeTheme}>
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark"><Activity size={19} strokeWidth={2.4} /></div>
          <div className="brand-copy"><strong>INM<span>2</span></strong><small>{t('product')}</small></div>
          <button className="icon-button mobile-close" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <div className="nav-caption">{t('navigation')}</div>
        <nav className="main-nav" aria-label={t('navigation')}>
          {navigation.map(({ key, icon: Icon }) => (
            <a key={key} href="#" className={`nav-link ${activePage === key ? 'active' : ''}`} aria-current={activePage === key ? 'page' : undefined} onClick={(event) => { event.preventDefault(); setActivePage(key); setSelectedBurstId(null); setSelectedActorIp(null); setMenuOpen(false) }}>
              <Icon size={18} strokeWidth={1.9} /><span>{t(key)}</span>
            </a>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="nav-caption">{t('administration')}</div>
        <a href="#" className={`nav-link ${activePage === 'administration' ? 'active' : ''}`} aria-current={activePage === 'administration' ? 'page' : undefined} onClick={(event) => { event.preventDefault(); setActivePage('administration'); setMenuOpen(false) }}><Settings2 size={18} /><span>{t('administration')}</span></a>
      </aside>

      {menuOpen && <button className="mobile-scrim" onClick={() => setMenuOpen(false)} aria-label="Close menu" />}

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setMenuOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="breadcrumbs"><span>{t('workspace')}</span><span className="crumb-slash">/</span><strong>{t(activePage)}</strong></div>
          <div className="topbar-actions">
            <label className="search-trigger"><Search size={16} /><input ref={searchInputRef} value={searchText} placeholder={t('search')} aria-label={t('search')} onChange={(event) => { const value = event.target.value; setSearchText(value); setSearchOpen(Boolean(value.trim())) }} onKeyDown={(event) => { if (event.key === 'Enter' && searchText.trim()) { event.preventDefault(); setSearchOpen(true) } }} /><kbd><Command size={11} /> K</kbd></label>
            <span className="topbar-divider" />
            <div className="notification-wrap"><button className="icon-button notification-button" aria-label={t('notifications')} title={t('notifications')} aria-expanded={notificationsOpen} onClick={() => { const opening = !notificationsOpen; setNotificationsOpen(opening); if (opening && notificationData) { setNotificationSnapshot(notificationData); const params = new URLSearchParams({ request_cursor: String(notificationData.request_cursor), burst_cursor: String(notificationData.burst_cursor) }); setNotificationData({ ...notificationData, request_count: 0, burst_count: 0 }); fetch(apiUrl('notifications/seen', params.toString()), { method: 'PUT' }).then((response) => { if (!response.ok) throw new Error('Could not save notification cursor') }).catch(() => setPreferencesError(true)) } }}><Bell size={18} />{notificationData && notificationData.request_count + notificationData.burst_count > 0 && <span className="notification-badge">{numberText(notificationData.request_count + notificationData.burst_count, language)}</span>}</button>{notificationsOpen && <NotificationPopover data={notificationSnapshot ?? notificationData} t={t} language={language} onClose={() => setNotificationsOpen(false)} onSelect={(item) => { setSelectedBurstId(item.type === 'burst' ? item.id : null); setSelectedActorIp(item.type === 'request' ? item.actorIp : null); setSelectedHost(null); setSelectedCategory(null); setActivePage('requests'); setNotificationsOpen(false) }} />}</div>
          </div>
        </header>

        <div className="content-wrap">
          {activePage === 'bursts' ? <BurstsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} sort={burstSort} onSortChange={updateBurstSort} filters={burstFilters} onFiltersChange={updateBurstFilters} onBurstSelect={(id) => { setSelectedBurstId(id); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setActivePage('requests') }} /> : activePage === 'actors' ? <ActorsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} sort={actorSort} onSortChange={updateActorSort} filters={actorFilters} onFiltersChange={updateActorFilters} onActorSelect={(ip) => { setSelectedActorIp(ip); setSelectedBurstId(null); setSelectedHost(null); setSelectedCategory(null); setActivePage('requests') }} /> : activePage === 'hosts' ? <HostsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} sort={hostSort} onSortChange={updateHostSort} filters={hostFilters} onFiltersChange={updateHostFilters} onHostSelect={(host) => { setSelectedHost(host); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedCategory(null); setActivePage('requests') }} /> : activePage === 'categories' ? <CategoriesPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} sort={categorySort} onSortChange={updateCategorySort} filters={categoryFilters} onFiltersChange={updateCategoryFilters} onCategorySelect={(category) => { setSelectedCategory(category); setSelectedBurstId(null); setSelectedActorIp(null); setSelectedHost(null); setActivePage('requests') }} /> : activePage === 'requests' ? <RequestsPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} burstId={selectedBurstId} actorIp={selectedActorIp} host={selectedHost} category={selectedCategory} filters={requestFilters} onFiltersChange={updateRequestFilters} sort={requestSort} onSortChange={updateRequestSort} onBurstClear={() => setSelectedBurstId(null)} onActorClear={() => setSelectedActorIp(null)} onHostClear={() => setSelectedHost(null)} onCategoryClear={() => setSelectedCategory(null)} /> : activePage === 'administration' ? <AdministrationPage t={t} language={language} /> : <DashboardPage t={t} language={language} range={range} onRangeChange={updateRange} lastImport={liveStatus.data?.collector_status.last_import} onBurstSelect={(id) => { setSelectedBurstId(id); setSelectedActorIp(null); setSelectedHost(null); setSelectedCategory(null); setActivePage('requests') }} />}

          <footer className="page-footer"><span>INM2 <b>·</b> Internet Noise Monitor</span><div className="footer-controls">{preferencesError && <span className="preferences-error">{t('preferencesError')}</span>}<label><span>{t('theme')}</span><select value={theme} onChange={(event) => updateTheme(event.target.value as Theme)} aria-label={t('theme')}><option value="auto">{t('themeAuto')}</option><option value="cloud">{t('themeCloud')}</option><option value="midnight">{t('themeMidnight')}</option><option value="moss">{t('themeMoss')}</option></select><Sun size={14} /></label><label><span>{t('language')}</span><select value={language} onChange={(event) => updateLanguage(event.target.value as Language)} aria-label={t('language')}><option value="de">DE</option><option value="en">EN</option></select></label><span className="version-label">v0.1.0</span></div></footer>
        </div>
      </main>
      <ApiActivityToast t={t} />
      {searchOpen && <GlobalSearchDialog query={searchText} queryRange={range.query} language={language} t={t} onClose={() => setSearchOpen(false)} onSelect={(kind, value) => { setSelectedBurstId(null); setSelectedActorIp(kind === 'actor' ? value : null); setSelectedHost(kind === 'host' ? value : null); setSelectedCategory(kind === 'category' ? value : null); setActivePage('requests'); setSearchOpen(false); setSearchText('') }} />}
    </div>
  )
}

function GlobalSearchDialog({ query, queryRange, language, t, onClose, onSelect }: { query: string; queryRange: string; language: Language; t: (key: MessageKey) => string; onClose: () => void; onSelect: (kind: 'actor' | 'host' | 'category', value: string) => void }) {
  const [results, setResults] = useState<GlobalSearchResults>({ actors: [], hosts: [], categories: [] })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])
  useEffect(() => {
    const term = query.trim()
    if (!term) { setResults({ actors: [], hosts: [], categories: [] }); setLoading(false); setError(false); return }
    setResults({ actors: [], hosts: [], categories: [] })
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
      const requests = [
        fetch(apiUrl('actors', queryRange, { global_search: term, sort_by: 'request_count', sort_order: 'desc', limit: '100', offset: '0' }), { signal: controller.signal, headers: { Accept: 'application/json' } }),
        fetch(apiUrl('hosts', queryRange, { host: term, sort_by: 'total_count', sort_order: 'desc' }), { signal: controller.signal, headers: { Accept: 'application/json' } }),
        fetch(apiUrl('categories', queryRange, { category: term, sort_by: 'total_count', sort_order: 'desc' }), { signal: controller.signal, headers: { Accept: 'application/json' } }),
      ]
      Promise.all(requests).then(async ([actorResponse, hostResponse, categoryResponse]) => {
        if (!actorResponse.ok || !hostResponse.ok || !categoryResponse.ok) throw new Error('Search request failed')
        const [actors, hosts, categories] = await Promise.all([
          actorResponse.json() as Promise<{ items: GlobalSearchActor[] }>,
          hostResponse.json() as Promise<{ items: GlobalSearchHost[] }>,
          categoryResponse.json() as Promise<{ items: GlobalSearchCategory[] }>,
        ])
        if (!controller.signal.aborted) setResults({ actors: actors.items, hosts: hosts.items, categories: categories.items })
      }).catch((reason: unknown) => {
        if (!controller.signal.aborted && !(reason instanceof DOMException && reason.name === 'AbortError')) setError(true)
      }).finally(() => {
        finish()
        if (!controller.signal.aborted) setLoading(false)
      })
    }, 250)
    return () => { if (timer !== undefined) window.clearTimeout(timer); finish(); controller.abort() }
  }, [query, queryRange])

  const resultCount = results.actors.length + results.hosts.length + results.categories.length
  return <div className="global-search-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section className="global-search-dialog" role="dialog" aria-modal="true" aria-label={t('searchPopupTitle')}>
      <header className="global-search-header"><div><h2>{t('searchPopupTitle')}</h2><p>{t('searchPopupHint')}</p></div><button type="button" className="icon-button" onClick={onClose} aria-label={t('close')}><X size={18} /></button></header>
      <div className="global-search-results" aria-live="polite">
        {loading && <div className="global-search-message"><span className="loading-spinner" />{t('searchPopupLoading')}</div>}
        {error && <div className="global-search-message">{t('searchPopupError')}</div>}
        {!query.trim() && !loading && <div className="global-search-message">{t('searchPopupHint')}</div>}
        {query.trim() && !loading && !error && resultCount === 0 && <div className="global-search-message">{t('searchPopupEmpty')}</div>}
        {results.actors.length > 0 && <SearchResultGroup title={t('searchActors')} icon={Users}>{results.actors.map((actor) => <SearchResultRow key={`actor-${actor.actor_id}`} primary={actor.ip} secondary={[actor.country, actor.city, actor.asn].filter(Boolean).join(' · ')} detail={actor.provider || undefined} language={language} country={actor.country} onClick={() => onSelect('actor', actor.ip)} />)}</SearchResultGroup>}
        {results.hosts.length > 0 && <SearchResultGroup title={t('searchHosts')} icon={Globe2}>{results.hosts.map((host) => <SearchResultRow key={`host-${host.host_id}`} primary={host.host} secondary={`${numberText(host.total_count, language)} ${t('requestsLabel')}`} language={language} onClick={() => onSelect('host', host.host)} />)}</SearchResultGroup>}
        {results.categories.length > 0 && <SearchResultGroup title={t('searchCategories')} icon={Blocks}>{results.categories.map((category) => <SearchResultRow key={`category-${category.category_id}`} primary={category.category_name} secondary={`${numberText(category.total_count, language)} ${t('requestsLabel')}`} language={language} onClick={() => onSelect('category', category.category_name)} />)}</SearchResultGroup>}
      </div>
    </section>
  </div>
}

function SearchResultGroup({ title, icon: Icon, children }: { title: string; icon: typeof Users; children: ReactNode }) {
  return <section className="search-result-group"><h3><Icon size={15} />{title}</h3><div>{children}</div></section>
}

function SearchResultRow({ primary, secondary, detail, country, language, onClick }: { primary: string; secondary: string; detail?: string; country?: string | null; language: Language; onClick: () => void }) {
  return <button type="button" className="search-result-row" onClick={onClick}><span className="search-result-copy"><strong>{primary}</strong><small>{country && <span className="country-flag" title={country}>{countryFlag(country)}</span>}{secondary || (language === 'de' ? 'Ohne weitere Angaben' : 'No additional details')}{detail ? ` · ${detail}` : ''}</small></span><ArrowUpRight size={15} /></button>
}

type RangePageProps = { t: (key: MessageKey) => string; language: Language; range: TimeRange; onRangeChange: (range: TimeRange) => void; lastImport: string | null | undefined }

function DashboardPage({ t, language, range, onRangeChange, lastImport, onBurstSelect }: RangePageProps & { onBurstSelect: (id: number) => void }) {
  const [burstSort, setBurstSort] = useState<BurstSort>({ column: 'requests', direction: 'desc' })
  const counts = useApiData<ApiResult<CountItem>>(apiUrl('request_counts', range.query, { bars: '24' }))
  const bursts = useApiData<BurstResponse>(apiUrl('bursts', range.query, { limit: '6', offset: '0', sort_by: burstSort.column, sort_order: burstSort.direction }))
  const actors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0' }))
  const newActors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0', new_only: 'true' }))
  const hosts = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query))
  const status = useApiData<StatusData>(apiUrl('status'), 10_000, false)
  const requestRows = counts.data?.items ?? []
  const requestsTotal = requestRows.reduce((sum, item) => sum + item.read_count + item.write_count + item.other_count, 0)
  const readTotal = requestRows.reduce((sum, item) => sum + item.read_count, 0)
  const writeTotal = requestRows.reduce((sum, item) => sum + item.write_count, 0)
  const otherTotal = requestRows.reduce((sum, item) => sum + item.other_count, 0)
  const busy = counts.loading || bursts.loading || actors.loading || newActors.loading || hosts.loading || (status.loading && !status.data)
  const error = counts.error ?? bursts.error ?? actors.error ?? newActors.error ?? hosts.error ?? (status.data ? null : status.error)
  const retry = () => { counts.reload(); bursts.reload(); actors.reload(); newActors.reload(); hosts.reload(); status.reload() }
  const changeBurstSort = (column: BurstSortColumn) => setBurstSort({ column, direction: burstSort.column === column && burstSort.direction === 'asc' ? 'desc' : 'asc' })
  const maxBucket = Math.max(1, ...requestRows.map((item) => item.read_count + item.write_count + item.other_count))
  const burstRead = bursts.data?.summary.read_count ?? 0
  const burstWrite = bursts.data?.summary.write_count ?? 0
  const burstOther = bursts.data?.summary.other_count ?? 0
  const burstTotal = burstRead + burstWrite + burstOther
  const burstReadEnd = burstTotal ? burstRead / burstTotal * 100 : 100 / 3
  const burstWriteEnd = burstTotal ? (burstRead + burstWrite) / burstTotal * 100 : 200 / 3
  const burstOtherEnd = 100
  const burstRingStyle = { background: `conic-gradient(var(--blue) 0 ${burstReadEnd}%, var(--green) ${burstReadEnd}% ${burstWriteEnd}%, var(--amber) ${burstWriteEnd}% ${burstOtherEnd}%)` }

  return <>
    <PageHeading title={t('overview')} subtitle={t('subtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    {busy || error ? <PageDataState loading={busy} error={error} retry={retry} t={t} /> : <>
      <section className="metric-grid" aria-label={t('trafficSummary')}>
        <MetricCard label={t('totalRequests')} value={numberText(requestsTotal, language)} icon={Activity} iconClass="blue" />
        <MetricCard label={t('detectedBursts')} value={numberText(bursts.data?.summary.burst_count, language)} icon={ShieldAlert} iconClass="amber" />
        <MetricCard label={t('uniqueActors')} value={numberText(actors.data?.total, language)} icon={Users} iconClass="violet" caption={`${numberText(newActors.data?.total, language)} ${t('newActors').toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')}`} />
        <MetricCard label={t('monitoredHosts')} value={numberText(hosts.data?.items.length, language)} icon={Network} iconClass="green" />
      </section>
      <section className="primary-grid">
        <div className="panel traffic-panel">
          <div className="panel-header"><div><h2>{t('trafficActivity')}</h2><p>{t('trafficDescription')}</p></div></div>
          <div className="chart-summary"><div><strong>{numberText(requestsTotal, language)}</strong><span>{t('requestsLabel')}</span></div></div>
          <div className="chart-wrap" role="img" aria-label={t('trafficActivity')}>
            <div className="y-labels"><span>{numberText(maxBucket, language)}</span><span>{numberText(Math.round(maxBucket * .75), language)}</span><span>{numberText(Math.round(maxBucket * .5), language)}</span><span>{numberText(Math.round(maxBucket * .25), language)}</span><span>0</span></div>
            <div className="chart-main"><div className="grid-lines"><i /><i /><i /><i /><i /></div><div className="bars">{requestRows.map((item, index) => { const total = item.read_count + item.write_count + item.other_count; const height = total === 0 ? 1 : Math.max(2, total / maxBucket * 100); const hint = `${t('startDate')}: ${dateText(item.from, language)}\n${t('endDate')}: ${dateText(item.to, language)}\n${t('read')}: ${numberText(item.read_count, language)}\n${t('write')}: ${numberText(item.write_count, language)}\n${t('other')}: ${numberText(item.other_count, language)}`; return <div className="bar-slot" key={item.from ?? index} data-tooltip={hint} style={{ '--bar-height': `${height}%` } as CSSProperties} aria-label={hint}><div className="bar-stack" style={{ height: `${height}%` }}><i className="bar-read" style={{ height: `${total ? item.read_count / total * 100 : 0}%` }} /><i className="bar-write" style={{ height: `${total ? item.write_count / total * 100 : 0}%` }} /><i className="bar-other" style={{ height: `${total ? item.other_count / total * 100 : 0}%` }} /></div></div> })}</div><div className="x-labels"><span>{rangeTick(range, 0, language)}</span><span>{rangeTick(range, .25, language)}</span><span>{rangeTick(range, .5, language)}</span><span>{rangeTick(range, .75, language)}</span><span>{rangeTick(range, 1, language)}</span></div></div>
          </div>
          <div className="chart-legend"><span><i className="legend-dot read-dot" />{t('read')} · {numberText(readTotal, language)}</span><span><i className="legend-dot write-dot" />{t('write')} · {numberText(writeTotal, language)}</span><span><i className="legend-dot other-dot" />{t('other')} · {numberText(otherTotal, language)}</span></div>
        </div>
        <div className="panel burst-panel">
          <div className="panel-header"><div><h2>{t('burstOverview')}</h2><p>{t('burstDescription')}</p></div></div>
          <div className="burst-highlight"><div className="burst-ring" style={burstRingStyle}><div><strong>{numberText(bursts.data?.summary.burst_count, language)}</strong><span>{t('bursts').toLocaleUpperCase(language === 'de' ? 'de-DE' : 'en-US')}</span></div></div><div className="burst-stats"><div><span><i className="legend-dot read-dot" />{t('read')}</span><strong>{numberText(burstRead, language)}</strong></div><div><span><i className="legend-dot write-dot" />{t('write')}</span><strong>{numberText(burstWrite, language)}</strong></div><div><span><i className="legend-dot other-dot" />{t('other')}</span><strong>{numberText(burstOther, language)}</strong></div></div></div>
          <div className="burst-footer"><span>{numberText(bursts.data?.summary.avg_requests_per_second, language)} {t('avgPerSecond')}</span><span>{rangeLabel(range, t, language)}</span></div>
        </div>
      </section>
      <section className="lower-grid">
        <div className="panel table-panel"><div className="panel-header"><div><h2>{t('burstsInPeriod')}</h2></div></div>
          <div className="table-scroll"><table><thead><tr><SortableHeader column="start_time" label={t('startTime')} sort={burstSort} onSort={changeBurstSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="actor_ip" label={t('actor')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="host" label={t('host')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="country" label={t('country')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="duration" label={t('duration')} sort={burstSort} onSort={changeBurstSort} /><SortableHeader column="requests" label={t('requestsLabel')} sort={burstSort} onSort={changeBurstSort} /><th /></tr></thead><tbody>{bursts.data?.items.length ? bursts.data.items.map((burst) => <tr key={burst.burst_id}><td>{dateText(burst.start_time, language)}</td><td><strong className="primary-cell">{burst.actor_ip}</strong></td><td className="host-cell">{burst.host || '—'}</td><td><span className="country-cell"><span className="country-flag">{countryFlag(burst.country)}</span>{burst.country || '—'}</span></td><td>{secondsText((new Date(burst.end_time).getTime() - new Date(burst.start_time).getTime()) / 1000, language)}</td><td><span className="request-count">{numberText(burst.read_count + burst.write_count + burst.other_count, language)}</span></td><td><button className="icon-button row-more" aria-label={t('viewBurstRequests')} title={t('viewBurstRequests')} onClick={() => onBurstSelect(burst.burst_id)}><ArrowUpRight size={15} /></button></td></tr>) : <EmptyRows t={t} columns={7} />}</tbody></table></div>
        </div>
        <div className="panel system-panel"><div className="panel-header"><div><h2>{t('status')}</h2><p>{t('infrastructure')}</p></div><span className={`health-pill ${status.data?.status === 'ok' ? '' : 'health-degraded'}`}><i />{status.data?.status === 'ok' ? t('allSystems') : t('degraded')}</span></div>
          <div className="system-list"><SystemRow icon={Activity} label={t('collector')} detail={activityText(status.data?.collector_status.activity, t)} healthy={status.data?.collector_status.available === true} /><SystemRow icon={Globe2} label={t('api')} detail={status.data?.status === 'ok' ? t('connected') : t('degraded')} healthy={status.data?.status === 'ok'} /><SystemRow icon={Database} label={t('database')} detail={status.data?.database === 'ok' ? t('operational') : t('degraded')} healthy={status.data?.database === 'ok'} /></div>
          <div className="system-updated"><span className="status-pulse" />{t('lastImport')}: {dateText(status.data?.collector_status.last_import, language)}</div>
        </div>
      </section>
    </>}
  </>
}

function MetricCard({ label, value, change, positive = true, icon: Icon, iconClass, caption }: { label: string; value: string; change?: string; positive?: boolean; icon: typeof ArrowUpRight; iconClass: string; caption?: string }) {
  return <div className="panel metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${iconClass}`}><Icon size={17} /></span></div><div className="metric-bottom"><strong className={value.length > 10 ? 'metric-value-compact' : ''}>{value}</strong>{change && <span className={`metric-change ${positive ? 'positive' : 'negative'}`}>{positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{change}</span>}</div>{caption && <div className="metric-caption">{caption}</div>}</div>
}

function SystemRow({ icon: Icon, label, detail, healthy }: { icon: typeof Activity; label: string; detail: string; healthy: boolean }) {
  return <div className="system-row"><div className="system-icon"><Icon size={16} /></div><div className="system-copy"><strong>{label}</strong><span>{detail}</span></div><span className={`system-check ${healthy ? '' : 'system-check-error'}`}>{healthy ? '✓' : '!'}</span></div>
}

function BurstsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onBurstSelect }: RangePageProps & { sort: BurstSort; onSortChange: (sort: BurstSort) => void; filters: BurstFilters; onFiltersChange: (filters: BurstFilters) => void; onBurstSelect: (id: number) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState<BurstFilters>(filters)
  const hostOptions = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query, { sort_by: 'host', sort_order: 'asc' }))
  const countryOptions = useApiData<ApiResult<{ country: string }>>(apiUrl('countries', range.query))
  const burstFilterParams = Object.fromEntries(Object.entries({ search: filters.search.trim(), host: filters.host, host_exact: filters.host ? 'true' : '', country: filters.country, country_exact: filters.country ? 'true' : '' }).filter(([, value]) => value))
  const result = useApiData<BurstResponse>(apiUrl('bursts', range.query, { limit: String(tablePageSize), offset: String(pageIndex * tablePageSize), sort_by: sort.column, sort_order: sort.direction, ...burstFilterParams }))
  const newActors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0', new_only: 'true' }))
  const summary = result.data?.summary
  const items = result.data?.items ?? []
  const retry = () => { result.reload(); newActors.reload(); hostOptions.reload(); countryOptions.reload() }
  const changeSort = (column: BurstSortColumn) => {
    setPageIndex(0)
    onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' })
  }
  useEffect(() => setPageIndex(0), [range.query, filters.search, filters.host, filters.country])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { const empty = { ...defaultBurstFilters }; setDraftFilters(empty); setPageIndex(0); onFiltersChange(empty) }
  return <>
    <PageHeading title={t('burstAnalysis')} subtitle={t('burstPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading || newActors.loading} error={result.error ?? newActors.error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('burstSearchPlaceholder')} aria-label={t('burstSearchPlaceholder')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select"><Globe2 size={15} /><select aria-label={t('filterHost')} value={draftFilters.host} onChange={(event) => setDraftFilters((value) => ({ ...value, host: event.target.value }))}><option value="">{t('allHosts')}</option>{hostOptions.data?.items.map((item) => <option key={item.host_id} value={item.host}>{item.host}</option>)}</select><span className="filter-select-value">{draftFilters.host || t('allHosts')}</span><ChevronDown size={13} /></label><label className="filter-select country-filter"><select aria-label={t('filterCountry')} value={draftFilters.country} onChange={(event) => setDraftFilters((value) => ({ ...value, country: event.target.value }))}><option value="">{t('allCountries')}</option>{countryOptions.data?.items.map((item) => <option key={item.country} value={item.country}>{countryFlag(item.country)} {item.country}</option>)}</select><span className="filter-select-value">{draftFilters.country && <span className="country-flag">{countryFlag(draftFilters.country)}</span>}{draftFilters.country || t('allCountries')}</span><ChevronDown size={13} /></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !newActors.loading && !result.error && !newActors.error && <>
      <section className="burst-metrics">
        <MetricCard label={t('burstsInPeriod')} value={numberText(summary?.burst_count, language)} icon={Activity} iconClass="blue" />
        <MetricCard label={t('affectedActors')} value={numberText(summary?.actor_count, language)} icon={Users} iconClass="violet" caption={`${numberText(newActors.data?.total, language)} ${t('newActors').toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')}`} />
        <MetricCard label={t('requestsInBursts')} value={numberText(summary?.request_count, language)} icon={Network} iconClass="green" caption={`${decimalText(summary?.avg_requests_per_burst, language)} ${t('avgRequestsPerBurst').toLocaleLowerCase(language === 'de' ? 'de-DE' : 'en-US')}`} />
        <MetricCard label={t('avgBurstDuration')} value={secondsText(summary?.avg_duration_seconds, language)} icon={Clock3} iconClass="amber" caption={`${t('maximumDuration')}: ${secondsText(summary?.max_duration_seconds, language)}`} />
      </section>
      <section className="panel burst-composition">
        <div className="composition-copy"><div><h2>{t('requestTypes')}</h2><p>{t('burstRequestTypeHint')}</p></div><strong>{numberText(summary?.request_count, language)} <span>{t('requestsLabel')}</span></strong></div>
        <div className="composition-bar"><i className="bar-read" style={{ width: `${summary?.request_count ? (summary.read_count ?? 0) / summary.request_count * 100 : 0}%` }} /><i className="bar-write" style={{ width: `${summary?.request_count ? (summary.write_count ?? 0) / summary.request_count * 100 : 0}%` }} /><i className="bar-other" style={{ width: `${summary?.request_count ? (summary.other_count ?? 0) / summary.request_count * 100 : 0}%` }} /></div>
        <div className="composition-legend"><span><i className="legend-dot read-dot" />{t('read')} <b>{numberText(summary?.read_count, language)}</b></span><span><i className="legend-dot write-dot" />{t('write')} <b>{numberText(summary?.write_count, language)}</b></span><span><i className="legend-dot other-dot" />{t('other')} <b>{numberText(summary?.other_count, language)}</b></span></div>
      </section>
      <section className="panel burst-list-panel">
        <div className="burst-list-heading"><div><h2>{t('burstEvents')}</h2></div></div>
        
        <Paginator total={summary?.burst_count ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
        <div className="table-scroll burst-table-scroll"><table className="burst-table"><thead><tr><SortableHeader column="start_time" label={t('startTime')} sort={sort} onSort={changeSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="actor_ip" label={t('actor')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="host" label={t('host')} sort={sort} onSort={changeSort} filtered={Boolean(filters.host)} filterLabel={t('filteredColumn')} /><SortableHeader column="country" label={t('country')} sort={sort} onSort={changeSort} filtered={Boolean(filters.country)} filterLabel={t('filteredColumn')} /><SortableHeader column="duration" label={t('duration')} sort={sort} onSort={changeSort} /><SortableHeader column="requests" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="avg_count" label={t('avgPerSecond')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>
          {items.length ? items.map((burst) => <tr key={burst.burst_id}><td><span className="burst-time"><strong>{dateText(burst.start_time, language)}</strong><span>{dateText(burst.end_time, language)}</span></span></td><td><span className="actor-detail"><strong className="primary-cell">{burst.actor_ip}</strong>{(burst.provider || burst.asn) && <small>{[burst.provider, burst.asn].filter(Boolean).join(' · ')}</small>}</span></td><td className="host-cell">{burst.host || '—'}</td><td><span className="actor-detail"><span className="country-cell"><span className="country-flag" title={burst.country || ''}>{countryFlag(burst.country)}</span>{burst.country || '—'}</span>{burst.city && <small>{burst.city}</small>}</span></td><td>{secondsText((new Date(burst.end_time).getTime() - new Date(burst.start_time).getTime()) / 1000, language)}</td><td><span className="request-count">{numberText(burst.read_count + burst.write_count + burst.other_count, language)}</span></td><td><span className="rate-value">{numberText(burst.avg_count, language)}<small> {t('requestsPerSecond')}</small></span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewBurstRequests')} title={t('viewBurstRequests')} onClick={() => onBurstSelect(burst.burst_id)}><ArrowUpRight size={15} /></button></td></tr>) : <EmptyRows t={t} columns={8} />}
        </tbody></table></div>
        <Paginator total={summary?.burst_count ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
      </section>
    </>}
  </>
}

function ActorsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onActorSelect }: RangePageProps & { sort: ActorSort; onSortChange: (sort: ActorSort) => void; filters: ActorFilters; onFiltersChange: (filters: ActorFilters) => void; onActorSelect: (ip: string) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState<ActorFilters>(filters)
  const countryOptions = useApiData<ApiResult<{ country: string }>>(apiUrl('countries', range.query))
  const actorParams = Object.fromEntries(Object.entries({ search: filters.search.trim(), country: filters.country, country_exact: filters.country ? 'true' : '', sort_by: sort.column, sort_order: sort.direction, limit: String(tablePageSize), offset: String(pageIndex * tablePageSize) }).filter(([, value]) => value))
  const result = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, actorParams))
  const newActors = useApiData<PagedResponse<ActorItem>>(apiUrl('actors', range.query, { limit: '1', offset: '0', new_only: 'true' }))
  const actors = result.data?.items ?? []
  const totalRequests = actors.reduce((sum, actor) => sum + actor.request_count, 0)
  const countries = new Set(actors.map((actor) => actor.country).filter(Boolean)).size
  const retry = () => { result.reload(); newActors.reload(); countryOptions.reload() }
  useEffect(() => setPageIndex(0), [range.query, filters.search, filters.country, sort])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { const empty = { ...defaultActorFilters }; setDraftFilters(empty); setPageIndex(0); onFiltersChange(empty) }
  const changeSort = (column: ActorSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('actors')} subtitle={t('actorPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading || newActors.loading} error={result.error ?? newActors.error} retry={retry} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('actorSearchPlaceholder')} aria-label={t('actorSearchPlaceholder')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select"><Globe2 size={15} /><select aria-label={t('filterCountry')} value={draftFilters.country} onChange={(event) => setDraftFilters((value) => ({ ...value, country: event.target.value }))}><option value="">{t('allCountries')}</option>{countryOptions.data?.items.map((item) => <option key={item.country} value={item.country}>{countryFlag(item.country)} {item.country}</option>)}</select><span className="filter-select-value">{draftFilters.country && <span className="country-flag">{countryFlag(draftFilters.country)}</span>}{draftFilters.country || t('allCountries')}</span><ChevronDown size={13} /></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !newActors.loading && !result.error && !newActors.error && <>
      <div className="metric-grid"><MetricCard label={t('uniqueActors')} value={numberText(result.data?.total, language)} icon={Users} iconClass="violet" /><MetricCard label={t('newActors')} value={numberText(newActors.data?.total, language)} icon={ArrowUpRight} iconClass="blue" /><MetricCard label={t('countriesSeen')} value={numberText(countries, language)} icon={Globe2} iconClass="green" caption={t('loadedActors')} /><MetricCard label={t('avgRequestsActor')} value={numberText(actors.length ? totalRequests / actors.length : 0, language)} icon={Activity} iconClass="amber" caption={t('loadedActors')} /></div>
      <div className="panel data-list-panel"><ListHeading title={t('actors')} />
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
        <div className="table-scroll"><table className="actor-table"><thead><tr><SortableHeader column="ip" label={t('ipAddress')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="country" label={t('location')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || filters.country)} filterLabel={t('filteredColumn')} /><SortableHeader column="first_time" label={t('firstSeen')} sort={sort} onSort={changeSort} /><SortableHeader column="last_time" label={t('lastSeen')} sort={sort} onSort={changeSort} /><SortableHeader column="request_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{actors.length ? actors.map((actor) => <tr key={actor.actor_id}><td><span className="actor-detail"><button type="button" className="table-link primary-cell" onClick={() => onActorSelect(actor.ip)}>{actor.ip}</button>{(actor.provider || actor.asn) && <small>{[actor.provider, actor.asn].filter(Boolean).join(' · ')}</small>}</span></td><td><span className="actor-detail"><span className="country-cell"><span className="country-flag" title={actor.country || ''}>{countryFlag(actor.country)}</span>{actor.country || '—'}</span>{actor.city && <small>{actor.city}</small>}</span></td><td>{dateText(actor.first_time, language)}</td><td>{dateText(actor.last_time, language)}</td><td><span className="request-count">{numberText(actor.request_count, language)}</span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewActorRequests')} title={t('viewActorRequests')} onClick={() => onActorSelect(actor.ip)}><ArrowUpRight size={15} /></button></td></tr>) : <EmptyRows t={t} columns={6} />}</tbody></table></div>
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
      </div>
    </>}
  </>
}

function HostsPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onHostSelect }: RangePageProps & { sort: HostSort; onSortChange: (sort: HostSort) => void; filters: HostFilters; onFiltersChange: (filters: HostFilters) => void; onHostSelect: (host: string) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [draftSearch, setDraftSearch] = useState(filters.search)
  const hostParams = Object.fromEntries(Object.entries({ host: filters.search.trim(), sort_by: sort.column, sort_order: sort.direction }).filter(([, value]) => value))
  const result = useApiData<ApiResult<HostItem>>(apiUrl('hosts', range.query, hostParams))
  const hosts = result.data?.items ?? []
  const visibleHosts = hosts.slice(pageIndex * tablePageSize, (pageIndex + 1) * tablePageSize)
  const total = hosts.reduce((sum, host) => sum + host.total_count, 0)
  const https = hosts.reduce((sum, host) => sum + host.https_count, 0)
  const httpsShare = total ? https / total * 100 : 0
  const topHost = [...hosts].sort((a, b) => b.total_count - a.total_count)[0]
  useEffect(() => setPageIndex(0), [range.query, filters.search, sort])
  useEffect(() => setDraftSearch(filters.search), [filters.search])
  const applyFilter = () => { setPageIndex(0); onFiltersChange({ search: draftSearch }) }
  const resetFilter = () => { setDraftSearch(''); setPageIndex(0); onFiltersChange({ ...defaultHostFilters }) }
  const changeSort = (column: HostSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('hosts')} subtitle={t('hostPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading} error={result.error} retry={result.reload} t={t} />
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search"><Search size={15} /><input value={draftSearch} placeholder={t('filterHost')} aria-label={t('filterHost')} onChange={(event) => setDraftSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') applyFilter() }} /></label><button type="button" className="filter-button" onClick={resetFilter}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilter}>{t('applyFilters')}</button></div>
    {!result.loading && !result.error && <>
      <div className="metric-grid"><MetricCard label={t('totalHosts')} value={numberText(hosts.length, language)} icon={Globe2} iconClass="blue" /><MetricCard label={t('totalRequests')} value={numberText(total, language)} icon={Network} iconClass="green" /><MetricCard label={t('httpsShare')} value={`${new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(httpsShare)}%`} icon={ShieldAlert} iconClass="violet" /><MetricCard label={t('topHost')} value={topHost?.host ?? '—'} icon={Activity} iconClass="amber" caption={t('trafficShare')} /></div>
      <div className="panel data-list-panel"><ListHeading title={t('hosts')} />
        <Paginator total={hosts.length} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
        <div className="table-scroll"><table className="host-table"><thead><tr><SortableHeader column="host" label={t('hostName')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="total_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="read_count" label={t('read')} sort={sort} onSort={changeSort} /><SortableHeader column="write_count" label={t('write')} sort={sort} onSort={changeSort} /><SortableHeader column="other_count" label={t('other')} sort={sort} onSort={changeSort} /><SortableHeader column="https_count" label={t('schemeSplit')} sort={sort} onSort={changeSort} /><SortableHeader column="https_share" label={t('httpsShare')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{visibleHosts.length ? visibleHosts.map((host) => { const hostTotal = host.total_count || 0; const share = hostTotal ? host.https_count / hostTotal * 100 : 0; return <tr key={host.host_id}><td><strong className="primary-cell">{host.host}</strong></td><td><span className="request-count">{numberText(host.total_count, language)}</span></td><td>{numberText(host.read_count, language)}</td><td>{numberText(host.write_count, language)}</td><td>{numberText(host.other_count, language)}</td><td><span className="scheme-chips"><i>HTTPS {numberText(host.https_count, language)}</i><i>HTTP {numberText(host.http_count, language)}</i></span></td><td><span className="share-cell"><span><i style={{ width: `${share}%` }} /></span>{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 0 }).format(share)}%</span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewHostRequests')} title={t('viewHostRequests')} onClick={() => onHostSelect(host.host)}><ArrowUpRight size={15} /></button></td></tr> }) : <EmptyRows t={t} columns={8} />}</tbody></table></div>
        <Paginator total={hosts.length} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
      </div>
    </>}
  </>
}

function CategoriesPage({ t, language, range, onRangeChange, lastImport, sort, onSortChange, filters, onFiltersChange, onCategorySelect }: RangePageProps & { sort: CategorySort; onSortChange: (sort: CategorySort) => void; filters: CategoryFilters; onFiltersChange: (filters: CategoryFilters) => void; onCategorySelect: (category: string) => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [draftSearch, setDraftSearch] = useState(filters.search)
  const params = Object.fromEntries(Object.entries({ category: filters.search.trim(), sort_by: sort.column, sort_order: sort.direction }).filter(([, value]) => value))
  const result = useApiData<ApiResult<CategoryItem>>(apiUrl('categories', range.query, params))
  const categories = result.data?.items ?? []
  const total = categories.reduce((sum, category) => sum + category.total_count, 0)
  const https = categories.reduce((sum, category) => sum + category.https_count, 0)
  const top = [...categories].sort((a, b) => b.total_count - a.total_count)[0]
  const visibleCategories = categories.slice(pageIndex * tablePageSize, (pageIndex + 1) * tablePageSize)
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
      <div className="metric-grid"><MetricCard label={t('activeCategories')} value={numberText(categories.length, language)} icon={Blocks} iconClass="blue" /><MetricCard label={t('totalRequests')} value={numberText(total, language)} icon={Activity} iconClass="green" /><MetricCard label={t('topCategory')} value={top?.category_name ?? '—'} icon={ShieldAlert} iconClass="amber" caption={top ? `${numberText(top.total_count, language)} ${t('requestsLabel')}` : t('noResults')} /><MetricCard label={t('httpsShare')} value={`${new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(total ? https / total * 100 : 0)}%`} icon={Globe2} iconClass="violet" /></div>
      <div className="panel data-list-panel"><ListHeading title={t('categories')} />
        <Paginator total={categories.length} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
        <div className="table-scroll"><table className="category-table"><thead><tr><SortableHeader column="category_name" label={t('categoryName')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim())} filterLabel={t('filteredColumn')} /><SortableHeader column="total_count" label={t('requestsLabel')} sort={sort} onSort={changeSort} /><SortableHeader column="read_count" label={t('read')} sort={sort} onSort={changeSort} /><SortableHeader column="write_count" label={t('write')} sort={sort} onSort={changeSort} /><SortableHeader column="other_count" label={t('other')} sort={sort} onSort={changeSort} /><SortableHeader column="traffic_share" label={t('trafficShare')} sort={sort} onSort={changeSort} /><SortableHeader column="https_share" label={t('schemeSplit')} sort={sort} onSort={changeSort} /><th /></tr></thead><tbody>{visibleCategories.length ? visibleCategories.map((category) => { const share = total ? category.total_count / total * 100 : 0; const schemeTotal = category.http_count + category.https_count + category.other_scheme_count; const secure = schemeTotal ? category.https_count / schemeTotal * 100 : 0; return <tr key={category.category_id}><td><strong className="primary-cell">{category.category_name}</strong></td><td><span className="request-count">{numberText(category.total_count, language)}</span></td><td>{numberText(category.read_count, language)}</td><td>{numberText(category.write_count, language)}</td><td>{numberText(category.other_count, language)}</td><td><span className="share-cell"><span><i style={{ width: `${share}%` }} /></span>{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 1 }).format(share)}%</span></td><td><span className="https-text">HTTPS</span> <span className="scheme-muted">{new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US', { maximumFractionDigits: 0 }).format(secure)}%</span></td><td><button type="button" className="icon-button row-more" aria-label={t('viewCategoryRequests')} title={t('viewCategoryRequests')} onClick={() => onCategorySelect(category.category_name)}><ArrowUpRight size={15} /></button></td></tr> }) : <EmptyRows t={t} columns={8} />}</tbody></table></div>
        <Paginator total={categories.length} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
      </div>
    </>}
  </>
}

function RequestsPage({ t, language, range, onRangeChange, lastImport, burstId, actorIp, host, category, filters, onFiltersChange, sort, onSortChange, onBurstClear, onActorClear, onHostClear, onCategoryClear }: RangePageProps & { burstId: number | null; actorIp: string | null; host: string | null; category: string | null; filters: RequestFilters; onFiltersChange: (filters: RequestFilters) => void; sort: RequestSort; onSortChange: (sort: RequestSort) => void; onBurstClear: () => void; onActorClear: () => void; onHostClear: () => void; onCategoryClear: () => void }) {
  const [pageIndex, setPageIndex] = useState(0)
  const [draftFilters, setDraftFilters] = useState(filters)
  const requestFilter: Record<string, string> = { ...(burstId == null ? {} : { burst_id: String(burstId) }), ...(actorIp == null ? {} : { actor: actorIp }), ...(host == null ? {} : { host }), ...(category == null ? {} : { category }), ...(filters.search.trim() ? { search: filters.search.trim() } : {}), ...(filters.status ? { status_class: filters.status } : {}), sort_by: sort.column, sort_order: sort.direction }
  const countFilter: Record<string, string> = { ...(burstId == null ? {} : { burst_id: String(burstId) }), ...(actorIp == null ? {} : { actor_ip: actorIp }), ...(host == null ? {} : { host }), ...(category == null ? {} : { category }), ...(filters.search.trim() ? { search: filters.search.trim() } : {}), ...(filters.status ? { status_class: filters.status } : {}) }
  const result = useApiData<PagedResponse<RequestItem>>(apiUrl('requests', range.query, { limit: String(tablePageSize), offset: String(pageIndex * tablePageSize), ...requestFilter }))
  const counts = useApiData<ApiResult<CountItem>>(apiUrl('request_counts', range.query, { bars: '1', ...countFilter }))
  const requests = result.data?.items ?? []
  const countRow = counts.data?.items[0]
  const total = countRow ? countRow.read_count + countRow.write_count + countRow.other_count : 0
  const errorCount = requests.filter((request) => request.downstream_status >= 400).length
  const retry = () => { result.reload(); counts.reload() }
  useEffect(() => setPageIndex(0), [range.query, burstId, actorIp, host, category, filters, sort])
  useEffect(() => setDraftFilters(filters), [filters])
  const applyFilters = () => { setPageIndex(0); onFiltersChange(draftFilters) }
  const resetFilters = () => { setDraftFilters({ ...defaultRequestFilters }); setPageIndex(0); onFiltersChange({ ...defaultRequestFilters }) }
  const changeSort = (column: RequestSortColumn) => { setPageIndex(0); onSortChange({ column, direction: sort.column === column && sort.direction === 'asc' ? 'desc' : 'asc' }) }
  return <>
    <PageHeading title={t('requests')} subtitle={t('requestPageSubtitle')} t={t} language={language} range={range} onRangeChange={onRangeChange} lastImport={lastImport} />
    <PageDataState loading={result.loading || counts.loading} error={result.error ?? counts.error} retry={retry} t={t} />
    {burstId != null && <div className="burst-filter-notice"><span>{t('filteredByBurst')} <strong>#{burstId}</strong></span><button type="button" onClick={onBurstClear}>{t('clearFilter')}</button></div>}{actorIp != null && <div className="burst-filter-notice"><span>{t('filteredByActor')} <strong>{actorIp}</strong></span><button type="button" onClick={onActorClear}>{t('clearFilter')}</button></div>}{host != null && <div className="burst-filter-notice"><span>{t('filteredByHost')} <strong>{host}</strong></span><button type="button" onClick={onHostClear}>{t('clearFilter')}</button></div>}{category != null && <div className="burst-filter-notice"><span>{t('filteredByCategory')} <strong>{category}</strong></span><button type="button" onClick={onCategoryClear}>{t('clearFilter')}</button></div>}
    <div className="filter-toolbar burst-filters burst-filter-controls"><label className="filter-search request-search"><Search size={15} /><input value={draftFilters.search} placeholder={t('searchRequests')} aria-label={t('searchRequests')} onChange={(event) => setDraftFilters((value) => ({ ...value, search: event.target.value }))} onKeyDown={(event) => { if (event.key === 'Enter') applyFilters() }} /></label><label className="filter-select"><select aria-label={t('responseStatus')} value={draftFilters.status} onChange={(event) => setDraftFilters((value) => ({ ...value, status: event.target.value as RequestFilters['status'] }))}><option value="">{t('allStatuses')}</option><option value="2xx">2xx · {t('statusSuccess')}</option><option value="3xx">3xx · {t('statusRedirect')}</option><option value="4xx">4xx · {t('statusClientError')}</option><option value="5xx">5xx · {t('statusServerError')}</option></select><span className="filter-select-value">{draftFilters.status ? `${draftFilters.status} · ${draftFilters.status === '2xx' ? t('statusSuccess') : draftFilters.status === '3xx' ? t('statusRedirect') : draftFilters.status === '4xx' ? t('statusClientError') : t('statusServerError')}` : t('allStatuses')}</span><ChevronDown size={13} /></label><button type="button" className="filter-button" onClick={resetFilters}>{t('resetFilters')}</button><button type="button" className="primary-button filter-submit" onClick={applyFilters}>{t('applyFilters')}</button></div>
    {!result.loading && !counts.loading && !result.error && !counts.error && <>
      <div className="metric-grid request-metrics"><MetricCard label={t('totalRequests')} value={numberText(result.data?.total ?? total, language)} icon={Activity} iconClass="blue" /><MetricCard label={t('errorsInLoadedRows')} value={numberText(errorCount, language)} icon={ShieldAlert} iconClass="amber" caption={`${numberText(requests.length, language)} ${t('loadedRequests')}`} /><MetricCard label={t('writeRequests')} value={numberText(countRow?.write_count, language)} icon={ArrowUpRight} iconClass="violet" /></div>
      <div className="panel data-list-panel requests-list-panel"><ListHeading title={t('requests')} />
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
        <div className="table-scroll"><table className="requests-table"><thead><tr><SortableHeader column="start_utc" label={t('startTime')} sort={sort} onSort={changeSort} filtered={true} filterLabel={t('filteredColumn')} /><SortableHeader column="request_method" label={t('method')} sort={sort} onSort={changeSort} /><SortableHeader column="request_path" label={t('requestPath')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || category != null)} filterLabel={t('filteredColumn')} /><SortableHeader column="downstream_status" label={t('responseStatus')} sort={sort} onSort={changeSort} filtered={Boolean(filters.status)} filterLabel={t('filteredColumn')} /><SortableHeader column="actor_ip" label={t('actor')} sort={sort} onSort={changeSort} filtered={Boolean(filters.search.trim() || actorIp != null || burstId != null)} filterLabel={t('filteredColumn')} /><SortableHeader column="host" label={t('host')} sort={sort} onSort={changeSort} filtered={Boolean(host != null || burstId != null)} filterLabel={t('filteredColumn')} /><SortableHeader column="duration" label={t('durationShort')} sort={sort} onSort={changeSort} /><SortableHeader column="downstream_content_size" label={t('responseSize')} sort={sort} onSort={changeSort} /></tr></thead><tbody>{requests.length ? requests.map((request) => <tr key={request.request_id}><td>{dateText(request.start_utc, language)}</td><td><span className="method-cell">{request.request_scheme.toLowerCase() === 'https' && <span className="https-lock" title="HTTPS" aria-label="HTTPS"><LockKeyhole size={13} /></span>}{request.request_scheme.toLowerCase() === 'http' && <span className="http-lock" title="HTTP" aria-label="HTTP"><LockOpen size={13} /></span>}<span className={`method-badge ${request.request_method.toLowerCase()}`}>{request.request_method}</span></span></td><td><span className="request-path-detail"><code className="path-cell">{request.request_path}</code>{request.categories && <small>{request.categories}</small>}</span></td><td><span className={`response-code ${request.downstream_status < 400 ? 'response-success' : ''}`}>{request.downstream_status}</span></td><td><span className="actor-detail"><strong className="primary-cell">{request.actor_ip}</strong>{(request.provider || request.asn) && <small>{[request.provider, request.asn].filter(Boolean).join(' · ')}</small>}{(request.city || request.country) && <small className="country-cell">{request.country && <><span className="country-flag" title={request.country}>{countryFlag(request.country)}</span>{request.country}</>}{request.city && <>{request.country ? ' · ' : ''}{request.city}</>}</small>}</span></td><td className="host-cell">{request.host || '—'}</td><td>{numberText(request.duration / 1_000_000, language)} ms</td><td>{numberText(request.downstream_content_size, language)} B</td></tr>) : <EmptyRows t={t} columns={8} />}</tbody></table></div>
        <Paginator total={result.data?.total ?? 0} pageIndex={pageIndex} pageSize={tablePageSize} onPageChange={setPageIndex} t={t} language={language} />
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

function SortableHeader<T extends string>({ column, label, sort, onSort, filtered = false, filterLabel }: { column: T; label: string; sort: { column: T; direction: 'asc' | 'desc' }; onSort: (column: T) => void; filtered?: boolean; filterLabel?: string }) {
  const active = sort.column === column
  return <th aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}><button type="button" className="sort-header" title={filtered ? `${label} · ${filterLabel ?? ''}` : label} aria-label={filtered ? `${label} · ${filterLabel ?? ''}` : label} onClick={() => onSort(column)}>{label}{active && (sort.direction === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}{filtered && <ListFilter size={11} className="column-filter-marker" aria-hidden="true" />}</button></th>
}

function Paginator({ total, pageIndex, pageSize, onPageChange, t, language }: { total: number; pageIndex: number; pageSize: number; onPageChange: (page: number) => void; t: (key: MessageKey) => string; language: Language }) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const page = Math.min(pageIndex, pageCount - 1)
  const from = total ? page * pageSize + 1 : 0
  const to = Math.min((page + 1) * pageSize, total)
  const jump = (nextPage: number) => onPageChange(Math.max(0, Math.min(pageCount - 1, nextPage)))
  const button = (Icon: typeof ChevronLeft, label: MessageKey, target: number) => <button type="button" className="page-button" aria-label={t(label)} title={t(label)} disabled={page === Math.max(0, Math.min(pageCount - 1, target))} onClick={() => jump(target)}><Icon size={15} /></button>
  return <div className="table-pagination"><span>{t('showing')} {numberText(from, language)}–{numberText(to, language)} {t('of')} {numberText(total, language)}</span><div className="pagination-controls">{button(SkipBack, 'firstPage', 0)}{button(ChevronsLeft, 'previousTenPages', page - 10)}{button(ChevronLeft, 'previousPage', page - 1)}<select aria-label={t('selectPage')} value={page} onChange={(event) => jump(Number(event.target.value))}>{Array.from({ length: pageCount }, (_, index) => <option key={index} value={index}>{index + 1}</option>)}</select>{button(ChevronRight, 'nextPage', page + 1)}{button(ChevronsRight, 'nextTenPages', page + 10)}{button(SkipForward, 'lastPage', pageCount - 1)}</div></div>
}

function AdministrationPage({ t, language }: { t: (key: MessageKey) => string; language: Language }) {
  const status = useApiData<StatusData>(apiUrl('status'), 10_000)
  const controller = useRef<AbortController | null>(null)
  const [pending, setPending] = useState<'import' | 'maintenance' | null>(null)
  const [operationMessage, setOperationMessage] = useState('')
  const [operationError, setOperationError] = useState('')
  const collector = status.data?.collector_status
  const busy = Boolean(pending || (collector?.activity && collector.activity !== 'Idle'))

  useEffect(() => () => controller.current?.abort(), [])
  const runOperation = async (operation: 'import' | 'maintenance') => {
    controller.current?.abort()
    const nextController = new AbortController()
    controller.current = nextController
    setPending(operation)
    setOperationMessage('')
    setOperationError('')
    try {
      const response = await fetch(apiUrl(operation), { method: 'PUT', signal: nextController.signal })
      const body = await response.json().catch(() => ({})) as { status?: string; activity?: string; detail?: string; error?: { message?: string } }
      if (!response.ok) throw new Error(body.error?.message || body.detail || `HTTP ${response.status}`)
      setOperationMessage(operation === 'import' ? t('importAccepted') : t('maintenanceAccepted'))
      status.reload()
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setOperationError(reason instanceof Error ? reason.message : t('operationFailed'))
    } finally {
      if (!nextController.signal.aborted) setPending(null)
    }
  }

  const environment = status.data?.environment ?? {}
  const configRows = (keys: [string, MessageKey][]) => keys.map(([name, hint]) => [name, environment[name] || '—', t(hint)])
  const formatActivity = (activity?: string) => activityText(activity, t)
  return <>
    <div className="page-heading admin-page-heading"><div><h1>{t('administration')}</h1><p>{t('adminSubtitle')}</p></div></div>
    <PageDataState loading={status.loading && !status.data} error={status.data ? null : status.error} retry={status.reload} t={t} />
    {!status.loading && (!status.error || status.data) && <>
      <section className="admin-health-grid">
        <HealthCard icon={Activity} label={t('collector')} status={formatActivity(collector?.activity)} detail={collector?.available ? t('collectorAvailable') : t('collectorUnavailable')} healthy={collector?.available === true} />
        <HealthCard icon={Globe2} label={t('api')} status={status.data?.status === 'ok' ? t('connected') : t('degraded')} detail={status.data?.status === 'ok' ? t('apiConnected') : t('apiUnavailable')} healthy={status.data?.status === 'ok'} />
        <HealthCard icon={Database} label={t('database')} status={status.data?.database === 'ok' ? t('operational') : t('degraded')} detail={status.data?.database === 'ok' ? t('databaseConnected') : t('apiUnavailable')} healthy={status.data?.database === 'ok'} />
      </section>
      <section className="panel admin-activity-panel">
        <div className="admin-section-heading"><div><h2>{t('collectorActivity')}</h2><p>{t('collectorActivityHint')}</p></div></div>
        <div className="activity-details"><AdminDetail label={t('lastImport')} value={dateText(collector?.last_import, language)} /><AdminDetail label={t('currentActivity')} value={formatActivity(collector?.activity)} /><AdminDetail label={t('importFile')} value={collector?.import_file || collector?.last_import_file || '—'} /><AdminDetail label={t('importCount')} value={numberText(collector?.import_count, language)} /></div>
      </section>
      <section className="admin-actions-grid">
        <AdminAction icon={ArrowDownRight} title={t('manualImport')} description={t('manualImportHint')} actionLabel={pending === 'import' ? t('starting') : t('startImport')} onClick={() => void runOperation('import')} disabled={busy} />
        <AdminAction icon={Settings2} title={t('manualMaintenance')} description={t('manualMaintenanceHint')} actionLabel={pending === 'maintenance' ? t('starting') : t('startMaintenance')} onClick={() => void runOperation('maintenance')} disabled={busy} />
      </section>
      {(operationMessage || operationError) && <div className={`operation-message ${operationError ? 'operation-error' : ''}`}>{operationError || operationMessage}</div>}
      <section className="panel admin-config-panel">
        <div className="admin-section-heading"><div><h2>{t('effectiveEnvironment')}</h2><p>{t('effectiveEnvironmentHint')}</p></div><span className="readonly-tag"><ShieldAlert size={13} />{t('readOnly')}</span></div>
        <div className="config-groups">
          <ConfigGroup title={t('importSettings')} rows={configRows([['LOG_FILES', 'inputFiles'], ['INPUT_INTERVAL_SECONDS', 'secondsUnit'], ['INPUT_SAVE_MARGIN_CHARACTERS', 'charactersUnit']])} />
          <ConfigGroup title={t('maintenanceSettings')} rows={configRows([['MAINTENANCE_INTERVAL_DAYS', 'daysUnit'], ['MAINTENANCE_INACTIVE_DAYS', 'daysUnit']])} />
          <ConfigGroup title={t('burstSettings')} rows={configRows([['BURST_MAX_GAP_SECONDS', 'secondsUnit'], ['BURST_MIN_REQUESTS', 'requestsUnit'], ['BURST_WINDOW_SECONDS', 'secondsUnit']])} />
          <ConfigGroup title={t('geoSettings')} rows={configRows([['GEOLITE_CITY_DB', 'localDatabasePath'], ['GEOLITE_ASN_DB', 'localDatabasePath']])} />
        </div>
        <div className="config-note"><CircleHelp size={15} /><span>{t('environmentRestartNote')}</span></div>
      </section>
    </>}
  </>
}

function HealthCard({ icon: Icon, label, status, detail, healthy }: { icon: typeof Activity; label: string; status: string; detail: string; healthy: boolean }) {
  return <div className="panel health-card"><div className="health-card-icon"><Icon size={17} /></div><div className="health-card-body"><span>{label}</span><strong><i className={healthy ? '' : 'offline-dot'} />{status}</strong><small>{detail}</small></div><span className={`health-card-check ${healthy ? '' : 'system-check-error'}`}>{healthy ? '✓' : '!'}</span></div>
}

function AdminDetail({ label, value }: { label: string; value: string }) {
  return <div className="admin-detail"><span>{label}</span><strong>{value}</strong></div>
}

function AdminAction({ icon: Icon, title, description, actionLabel, onClick, disabled }: { icon: typeof Activity; title: string; description: string; actionLabel: string; onClick: () => void; disabled: boolean }) {
  return <div className="panel admin-action-card"><div className="admin-action-icon"><Icon size={17} /></div><div className="admin-action-copy"><div className="admin-action-title"><h2>{title}</h2></div><p>{description}</p><button className="admin-action-button" onClick={onClick} disabled={disabled}>{actionLabel}<ArrowUpRight size={14} /></button></div></div>
}

function ConfigGroup({ title, rows }: { title: string; rows: string[][] }) {
  return <div className="config-group"><h3>{title}</h3>{rows.map(([name, value, hint]) => <div className="config-row" key={name}><div><strong>{name}</strong><span>{hint}</span></div><code>{value}</code></div>)}</div>
}

export default App
