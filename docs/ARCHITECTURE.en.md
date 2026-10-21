# Architecture and data flow

[Deutsche Version](ARCHITECTURE.de.md) · [Installation guide](../README.en.md)

INM2 consists of three services started with Docker Compose. The collector reads Traefik access logs and detects bursts and path scans, the API serves stored data, and the React UI calls that API from the browser. The collector and API share a SQLite database.

## Services

| Service | Implementation | Responsibility | Compose availability |
| --- | --- | --- | --- |
| `ui` | React, TypeScript, Nginx | Dashboard and web interface; Nginx forwards `/api/` to the API. | Host port `3000`, container port `80` |
| `api` | FastAPI, Uvicorn | REST endpoints under `/api/v1`, database access, and forwarding manual collector jobs. | Host loopback `127.0.0.1:8000` only; container port `8000` on the Compose network |
| `collector` | Python, Uvicorn control service | Imports logs, optionally adds geolocation/ASN data, detects bursts, and runs maintenance. | Control port `8001` on the internal Compose network only |

Compose builds the images from the Dockerfiles in the repository. The UI is reachable on the host. The API port is bound to `127.0.0.1` only; the UI reaches it over the internal Compose network. The API requires an administrator sign-in.

## Data flow

1. The collector reads filenames from `LOG_FILES` in the directory mounted read-only at `/input-logs`. It expects Traefik JSON objects, one per line, and also discovers matching rotated files. When `COWRIE_ENABLED=true`, it also incrementally reads `cowrie.json` from `/cowrie-logs` and stores SSH events separately. Cowrie login events, including password values, are imported into `cowrie_event.password`.
2. Complete, processable lines are converted into requests, actors, hosts, and categories. Burst detection processes new requests incrementally and extends the previous import's last burst when the gap allows it. It rebuilds the full history only once when migrating existing data, or for an actor/host pair that receives a backdated request. Only globally routable client IP addresses are imported; private, loopback, link-local, reserved, and invalid addresses are skipped.
3. When available, the collector adds city/country and ASN/provider data from local GeoLite2 MMDB files. This enrichment is optional.
4. The collector and API use the same SQLite file at `databases/inm2.sqlite3`. The database uses WAL so API reads can continue during imports; short write conflicts are retried for up to 30 seconds. The UI accesses data only through HTTP requests to the API.
5. Scheduled and manually triggered imports and maintenance share a lock. Manual jobs run in the background; if the collector is busy, the API returns `409`.

## Incidents

All detections are stored in the shared `incident` table. `incident_criterion` records every detector criterion met by an incident, so one incident can cover multiple types. `incident_request` records exact request membership for incident details and filtered request views. After each import, incidents from the same actor are merged when more than `INCIDENT_MERGE_OVERLAP_PERCENT` percent of the shorter time range overlaps (default 80). The merged incident time range is the minimum and maximum timestamp of its linked requests. On startup, the database initializer migrates existing `path_scan_incident` rows and their request associations. On the first import after upgrade, a one-time backfill also checks the latest activity window for each actor/host pair against the new rules.

Rules inspect rolling 10-minute windows per source IP and host: path scan (at least 8 distinct sensitive paths), failed logins (at least 5 responses 401/403 on login/auth paths), error spike (at least 20 responses of 400 or higher), write activity (at least 5 POST/PUT/PATCH/DELETE requests to admin/auth/API paths), scanner activity (at least 5 requests with known scanner signatures in the User-Agent), and request spikes (at least 50 requests). Three requests after at least 30 days without host activity also create an investigation lead. Error spikes show error count and non-error response share; request spikes show average, minimum, and maximum requests per second. By default, a low-and-slow, multi-host path scan is detected over a rolling 3-hour window when at least 12 sensitive or error paths span at least 2 hosts and 5 minutes. The time window, minimum path and host counts, and minimum duration can be configured with `LOW_SLOW_SCAN_WINDOW_SECONDS`, `LOW_SLOW_SCAN_MIN_PATHS`, `LOW_SLOW_SCAN_MIN_HOSTS`, and `LOW_SLOW_SCAN_MIN_SPAN_SECONDS`; a separate minimum request count is unnecessary because each distinct path requires a request. A 2xx response to a sensitive-file or exploit probe is flagged individually. URL and User-Agent checks are heuristics; a response does not establish that content was exposed or an exploit succeeded. Missing logs and misattributed proxy IPs affect results.

## Import behavior and log files

`INPUT_SAVE_MARGIN_CHARACTERS` leaves a buffer at the end of the active file so incomplete log lines are not processed. The collector also discovers matching rotated segments (`access.log.*`, including `.gz`) and reads them in time order through EOF. Positions are keyed by device/inode identity and therefore follow renamed segments. A SHA-256 fingerprint of the first complete log line (up to 64 KiB) detects a new file if an inode is reused. The fingerprint, offset, and request are committed together. The collector never changes or deletes log files; rotation and retention remain the responsibility of logrotate.

Compose mounts the host directory in `INPUT_LOG_DIR` at `/input-logs`. `LOG_FILES` contains only the filename within that directory:

```dotenv
INPUT_LOG_DIR=/var/log/my-service
LOG_FILES=access.log
```

Operational logs also live in `./logs`, but each service writes to separate files: `collector.log`, `api.log`, `ui-access.log`, and `ui-error.log`. A single shared file is avoided because independent containers can write concurrently and rotate it. Collector and API logs rotate; Nginx records UI request failures and Nginx errors separately. The **Logging** page shows them in tabs, refreshes automatically, and can reset the selected file. Collector and API log size is bounded by rotation; Nginx logs can be reset from the Logging page.

Multiple entries can be separated with semicolons. `IGNORE_REQUEST_ROUTES` can skip requests for configured host/path prefixes. `KNOWN_HOSTS` lists host names belonging to this installation; the collector syncs them to the `known_host` table at startup. An entry such as `jvkh.de` marks both `jvkh.de` and any subdomain such as `inm.jvkh.de` as an own host. `www.example.org` and `example.org` are also treated as the same host for matching. Stored hosts and their bursts remain separate.

Burst detection splits a sequence when the gap between requests exceeds `BURST_MAX_GAP_SECONDS`. A sequence qualifies once at least `BURST_MIN_REQUESTS` requests fall within `BURST_WINDOW_SECONDS`; from its first qualifying request, the sequence continues until the next gap. Normal imports process only new requests and the short qualification window, extending the last burst for that actor/host pair when appropriate. The `burst_request` table stores exact membership, and its unique request ID prevents one request from belonging to multiple bursts. Existing data is rebuilt once on the first collector start with this schema; a backdated request triggers a full rebuild only for its affected actor/host pair.

## Scheduling and maintenance

The scheduler runs due jobs when the collector starts and schedules each next run after the current run finishes. `INPUT_INTERVAL_SECONDS` controls the import interval; `MAINTENANCE_INTERVAL_DAYS` controls the maintenance interval. Maintenance removes actors inactive for longer than `MAINTENANCE_INACTIVE_DAYS`, along with dependent data. It also removes Web/Cowrie database events and rotated Cowrie JSON/diagnostic logs older than `MAINTENANCE_LOG_RETENTION_DAYS`; setting it to `0` disables that cleanup.

## Persistence and mounts

- `./databases` is mounted at `/app/databases` for the API and collector and contains the SQLite database.
- `./logs` is mounted at `/logs` for the collector, API, and UI; operational log files are kept separate by service.
- The directory in `INPUT_LOG_DIR` is mounted read-only at `/input-logs`.
- The directory in `GEOLITE_DB_DIR` is mounted read-only at `/geoip`.
- Cowrie's `var/` is stored under `./cowrie-data/var`; `var/log/cowrie` is mounted at `/cowrie-logs` for the collector so it can delete dated rotations according to `MAINTENANCE_LOG_RETENTION_DAYS`. The active log is kept.

Compose uses host bind mounts. Regular database backups and monitoring are recommended on the host. The collector reads access logs and rotated segments read-only and never modifies or deletes them. After a successful import, the Web Honeypot queue is truncated through the last fully read line.

## Configuration

Compose loads collector environment variables from `.env`. Supported variables and code defaults are documented in [API.en.md – Collector configuration](API.en.md#configuration); example startup values are in [`../.env.example`](../.env.example). Restart the collector after changing `.env` for the new values to take effect.

Compose sets `COLLECTOR_CONTROL_URL` for the API; its default is `http://collector:8001`. Database paths are defined in `common/database.py`.

## Related documentation

- [Installation, operation, and troubleshooting](../README.en.md)
- [Using the API and collector](API.en.md)
- [API und Collector verwenden (Deutsch)](API.de.md)
