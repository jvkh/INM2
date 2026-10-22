import { CircleHelp } from 'lucide-react'
import type { MessageKey } from './i18n'

type GuideEntry = { title: MessageKey; description: MessageKey; example?: string; exampleKey?: MessageKey }
type Props = { t: (key: MessageKey) => string; page: string }

export default function BackgroundGuidePage({ t, page }: Props) {
  switch (page) {
    case 'categoryGuide': return <CategoryGuidePage t={t} />
    case 'burstGuide': return <BurstGuidePage t={t} />
    case 'incidentGuide': return <IncidentGuidePage t={t} />
    case 'countGuide': return <CountGuidePage t={t} />
    case 'hostGuide': return <HostGuidePage t={t} />
    case 'pathsGuide': return <PathsGuidePage t={t} />
    case 'honeypotGuide': return <HoneypotGuidePage t={t} />
    case 'cowrieGuide': return <CowrieGuidePage t={t} />
    default: return null
  }
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
    { title: 'guideOnionHosts', description: 'guideOnionHostsDescription', example: 'Host: abc123.onion' },
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
function InfoGuidePage({ t, title, subtitle, entries, note }: { t: (key: MessageKey) => string; title: MessageKey; subtitle: MessageKey; entries: GuideEntry[]; note: MessageKey }) {
  return <><div className="page-heading"><div><h1>{t(title)}</h1><p>{t(subtitle)}</p></div></div><div className="category-guide-grid">{entries.map((entry) => <article className="panel category-guide-card" key={entry.title}><h2>{t(entry.title)}</h2><p>{t(entry.description)}</p>{(entry.example || entry.exampleKey) && <div className="category-guide-example"><strong>{t('guideExamples')}</strong><code>{entry.exampleKey ? t(entry.exampleKey) : entry.example}</code></div>}</article>)}</div><div className="category-guide-note"><CircleHelp size={16} /><span>{t(note)}</span></div></>
}
