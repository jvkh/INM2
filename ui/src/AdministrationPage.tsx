import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowDownRight, ArrowUpRight, Bug, CircleHelp, Database, Globe2, Network, Settings2, ShieldAlert } from 'lucide-react'
import type { Language, MessageKey } from './i18n'

type Translator = (key: MessageKey) => string
type StatusData = {
  status: string
  database: string
  honeypot_available: boolean
  honeypot_configured: boolean
  cowrie_configured: boolean
  cowrie_available: boolean
  collector_status: {
    available: boolean
    last_import: string | null
    activity: string
    import_file: string
    last_import_file: string
    import_count: number
    last_import_files: { file: string; count: number }[]
  }
  environment: Record<string, string>
}

function apiUrl(path: string) { return `/api/v1/${path}` }
function numberText(value: number | null | undefined, language: Language) {
  return new Intl.NumberFormat(language === 'de' ? 'de-DE' : 'en-US').format(value ?? 0)
}
function dateText(value: string | null | undefined, language: Language) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(language === 'de' ? 'de-DE' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
function activityText(activity: string | undefined, t: Translator) {
  if (activity === 'Import') return t('importInProgress')
  if (activity === 'Maintenance') return t('maintenanceInProgress')
  if (activity === 'Idle') return t('idle')
  return activity || '—'
}

export default function AdministrationPage({ t, language }: { t: Translator; language: Language }) {
  const [status, setStatus] = useState<StatusData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const controller = useRef<AbortController | null>(null)
  const [pending, setPending] = useState<'import' | 'maintenance' | null>(null)
  const [operationMessage, setOperationMessage] = useState('')
  const [operationError, setOperationError] = useState('')
  const reload = useCallback(() => setReloadKey((key) => key + 1), [])

  useEffect(() => {
    const abort = new AbortController()
    controller.current = abort
    setLoading(true)
    setError(null)
    window.dispatchEvent(new CustomEvent('inm2-api-activity', { detail: 1 }))
    fetch(apiUrl('status'), { credentials: 'same-origin', signal: abort.signal, headers: { Accept: 'application/json' } })
      .then(async (response) => {
        if (response.status === 401) window.dispatchEvent(new Event('inm2-auth-expired'))
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<StatusData>
      })
      .then((data) => { if (!abort.signal.aborted) setStatus(data) })
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : 'Request failed')
      })
      .finally(() => {
        window.dispatchEvent(new CustomEvent('inm2-api-activity', { detail: -1 }))
        if (!abort.signal.aborted) setLoading(false)
      })
    const onImport = () => reload()
    window.addEventListener('inm2-collector-import', onImport)
    window.addEventListener('inm2-live-refresh', onImport)
    return () => { abort.abort(); window.removeEventListener('inm2-collector-import', onImport); window.removeEventListener('inm2-live-refresh', onImport) }
  }, [reloadKey, reload])

  const collector = status?.collector_status
  const busy = Boolean(pending || (collector?.activity && collector.activity !== 'Idle'))
  const runOperation = async (operation: 'import' | 'maintenance') => {
    if (operation === 'maintenance') {
      const retentionDays = status?.environment?.MAINTENANCE_LOG_RETENTION_DAYS || '14'
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
      const response = await fetch(apiUrl(operation), { method: 'PUT', credentials: 'same-origin', signal: nextController.signal, headers: { Accept: 'application/json' } })
      const body = await response.json().catch(() => ({})) as { detail?: string; error?: { message?: string } }
      if (!response.ok) throw new Error(body.error?.message || body.detail || `HTTP ${response.status}`)
      setOperationMessage(operation === 'import' ? t('importAccepted') : t('maintenanceAccepted'))
      if (operation === 'import') window.dispatchEvent(new Event('inm2-collector-import'))
      reload()
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      setOperationError(reason instanceof Error ? reason.message : t('operationFailed'))
    } finally {
      if (!nextController.signal.aborted) setPending(null)
    }
  }

  const environment = Object.fromEntries(Object.entries(status?.environment ?? {}).filter(([name]) =>
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
    {error && !status && <div className="panel data-state error-state"><strong>{t('apiError')}</strong><span>{t('apiUnavailable')}</span><small>{error}</small><button className="select-button" onClick={reload}>{t('retry')}</button></div>}
    {loading && !status && <div className="panel data-state">{t('loadingData')}</div>}
    {!loading && (!error || status) && <>
      <section className={`admin-health-grid${status?.cowrie_configured ? ' has-cowrie' : ''}`}>
        <HealthCard icon={Activity} label={t('collector')} status={formatActivity(collector?.activity)} detail={collector?.available ? t('collectorAvailable') : t('collectorUnavailable')} healthy={collector?.available === true} />
        <HealthCard icon={Globe2} label={t('api')} status={status?.status === 'ok' ? t('connected') : t('degraded')} detail={status?.status === 'ok' ? t('apiConnected') : t('apiUnavailable')} healthy={status?.status === 'ok'} />
        <HealthCard icon={Database} label={t('database')} status={status?.database === 'ok' ? t('operational') : t('degraded')} detail={status?.database === 'ok' ? t('databaseConnected') : t('apiUnavailable')} healthy={status?.database === 'ok'} />
        {status?.honeypot_configured && <HealthCard icon={Bug} label={t('honeypot')} status={status.honeypot_available ? t('operational') : t('notStarted')} detail={status.honeypot_available ? t('connected') : t('honeypotNotRunning')} healthy={status.honeypot_available} />}
        {status?.cowrie_configured && <HealthCard icon={Network} label={t('cowrie')} status={status.cowrie_available ? t('operational') : t('notStarted')} detail={status.cowrie_available ? t('cowrieLogAvailable') : t('cowrieLogUnavailable')} healthy={status.cowrie_available} />}
      </section>
      <section className="panel admin-activity-panel">
        <div className="admin-section-heading"><div><h2>{t('collectorActivity')}</h2><p>{t('collectorActivityHint')}</p></div></div>
        <div className="admin-import-table-wrap"><table className="admin-import-table"><thead><tr><th>{t('lastImport')}</th><th>{t('importFile')}</th><th>{t('importCount')}</th></tr></thead><tbody>{importedFiles.length ? importedFiles.map((item, index) => <tr key={`${item.file}-${index}`}><td>{index === 0 ? dateText(collector?.last_import, language) : ''}</td><td>{item.file}</td><td><span className="request-count">{numberText(item.count, language)}</span></td></tr>) : <tr><td>{dateText(collector?.last_import, language)}</td><td>—</td><td>—</td></tr>}</tbody></table></div>
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
          {status?.honeypot_configured && <ConfigGroup title={t('honeypot')} rows={configRows([['HONEYPOT_ENABLED', 'honeypotEnabledSetting'], ['HONEYPOT_HOST', 'honeypotHostSetting'], ['TRAEFIK_DOCKER_NETWORK', 'honeypotNetworkSetting'], ['HONEYPOT_HTTP_ENTRYPOINT', 'honeypotHttpEntryPointSetting'], ['HONEYPOT_ENTRYPOINT', 'honeypotHttpsEntryPointSetting'], ['HONEYPOT_CERT_RESOLVER', 'honeypotCertResolverSetting'], ['HONEYPOT_UID', 'honeypotUidSetting'], ['HONEYPOT_GID', 'honeypotGidSetting']])} />}
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
