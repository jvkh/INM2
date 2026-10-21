# Changelog

[Deutsche Version](CHANGELOG.de.md)

INM2 uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. The canonical version is stored in [`VERSION`](VERSION). The UI footer and API OpenAPI metadata read their runtime version from that file; `ui/package.json` must be updated to the same value whenever the version changes.

Pending changes are recorded under **Unreleased**. For a release, `VERSION` and `ui/package.json` are updated, entries are moved into a section named `X.Y.Z — YYYY-MM-DD`, a new **Unreleased** section is created, and the release commit is tagged in Git as `vX.Y.Z`.

There are no published version tags in the repository yet. No earlier releases are inferred from commit messages. The current working version is `0.1.0`.

## Unreleased

- Added Cowrie SSH import, a dedicated event view and SSH statistics, plus clearly qualified time-based links to web honeypot `.env` requests.

- Added an optional, rule-based HTTP honeypot as a resource-light Python service behind Traefik; it uses no external services or LLM and publishes no host port.
- Captured honeypot POST bodies, including submitted login fields; large bodies and uploads are stored separately and imported by the collector.
- Aligned the Honeypot page with the main lists: shared time range and paginator, sorting and free-text search, actor metadata, and direct access to submitted data.
- Added a Honeypot statistics tab with access frequency, HTTP methods, detection rules, and matching against stored incidents; the time series gains an additional Honeypot tile whenever the service is configured.
- Added a Honeypot enable switch to the setup script; when disabled, INM2 hides the Honeypot menu entry, statistics, and status notices.
- Added German and English documentation for the optional honeypot.
- Added path-scan detection: at least eight distinct sensitive paths from the same source IP and host within ten minutes create an incident shown in notifications.
- Added low-and-slow multi-host path-scan detection with configurable time window, path and host counts, and minimum duration.
- Added Linux setup menu items for required settings, ports, access security, and burst and incident thresholds.
- Added a setup menu item to delete `.env.backup.*` files after confirmation.
- Added an Incidents page with time range, status, and free-text filters. IPs include provider, ASN, country, and city in the page and incident notifications.
- Incident status can be persistently set to Open, Acknowledged, or Resolved from the list.
- Incident IDs are displayed and link to a request list filtered to that exact incident.
- Added optional TOTP two-factor sign-in for the single administrator.
- Added single-administrator sign-in for the UI and API with a signed, expiring session cookie, CSRF origin checks, and throttling for failed login attempts.
- Replaced the plaintext password configuration with a scrypt password hash.
- Documented required authentication settings and authenticated API usage.
- Added Linux setup support for configuring Traefik log and GeoLite2 host directories in `.env`; Compose mounts them read-only and `LOG_FILES` accepts filenames relative to the log directory.


## 0.1.1 - 2026-10.12

### Added

- A canonical version file and a shared version displayed by the UI and API.
- Installation and operation documentation in German and English, including a Docker Compose example configuration.
- English versions of the UI, API, and architecture documentation.
- This changelog and guidance for future releases.

### Changed

- Updated the architecture and API documentation to match the implemented application and configuration.
- Clarified that the UI README covers local UI development.
- Aligned the API version with the existing UI version, `0.1.0`.
- Stored incidents in one typed table with explicit request membership; existing path-scan records are migrated at startup.
- Added detection for login failures, sensitive-file and exploit responses, write activity, error spikes, and scanner signatures.

### Removed

- Obsolete project status and decision specification files.
