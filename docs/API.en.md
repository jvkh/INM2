# Using the API and collector

[Deutsche Version](API.de.md) · [Installation guide](../README.en.md)

This guide describes the HTTP API and collector operations for developers and operators. For installing and running the complete application, see the [repository README](../README.en.md).

## Connection and interactive documentation

All API routes except `POST /api/v1/auth/login` and `GET /api/v1/auth/session` require a valid administrator session. When `INM2_TOTP_ENABLED=true`, login must also include `totp_code` with a current six-digit authenticator code. The web UI signs in and manages the session cookie automatically. `/docs` is also protected.

For scripts, the cookie can be saved after sign-in. HTTPS is required, and `Origin` must match the request address:

```sh
curl -c cookies.txt -b cookies.txt \\
  -H 'Origin: https://inm2.example.org' -H 'Content-Type: application/json' \\
  -d '{"password":"ADMIN-PASSWORD","totp_code":"123456"}' \\
  https://inm2.example.org/api/v1/auth/login
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

The UI extends the session on actual user activity. A new sign-in is required after 12 hours without such activity; automatic background requests do not extend the session. API clients can extend a session with `POST /api/v1/auth/activity`; other API requests do not extend it. Mutating `POST`, `PUT`, `PATCH`, and `DELETE` requests also require a matching `Origin` header.

The API examples below assume an authenticated session. With `curl`, the cookie is passed using `-b cookies.txt`; mutating requests also require `-H 'Origin: https://inm2.example.org'`. The example host must match the address used for API access.

```sh
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

The API returns JSON. Query parameters are used for `GET` and `PUT` routes; `PUT` requests do not require a JSON body.

## General conventions

### Time ranges

Timestamps must use ISO 8601, such as `2026-10-01T00:00:00Z` or `2026-10-01T02:00:00+02:00`. Timestamps without a time zone are interpreted as UTC. `from` and `to` form a half-open interval: `from` is included and `to` is excluded. `from` must be earlier than `to`.

### Filters and pagination

Text filters such as `host`, `country`, `city`, `provider`, `asn`, `ip`, and `category` match substrings. When multiple filters are supplied, all must match. IDs, timestamps, and numeric filters are exact. Where supported, `limit` defaults to 100 and has a maximum of 1000; `offset` starts at 0.

### Request method categories

- Read: `GET`, `HEAD`, `OPTIONS`
- Write: `POST`, `PUT`, `PATCH`, `DELETE`
- Other: all remaining methods

Unrecognized or missing URL schemes are counted as `other_scheme_count` in HTTP/HTTPS breakdowns.

## Endpoints

### Metric trends

`GET /api/v1/metric_trends` returns metrics for the selected range and the immediately preceding range of equal duration. `from` and `to` are required; `page` can be `dashboard`, `bursts`, `actors`, `hosts`, `categories`, or `requests`. The requests view also accepts `incident_id`, so its metrics match the incident request list. Each entry in `metrics` contains current and previous values, percentage change, and direction (`up`, `down`, `steady`). Changes of up to 5% are steady. An empty comparison range returns `0%` and `steady`.

### Status

`GET /api/v1/status` reports API/database health, stored collector status, and supported non-sensitive configuration values. It does not expose credentials or arbitrary process environment variables.

```sh
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

A healthy response includes `status: "ok"`, `database: "ok"`, `collector_status`, and `environment`. `collector_status.import_file` is populated while a file is being processed. `collector_status.last_import_file` retains the most recently started filename after an import finishes. If the status handler cannot read the database or settings, it still returns HTTP 200 with `status: "degraded"`, `database: "unavailable"`, and an unavailable collector status.

### Logs

`GET /api/v1/logs?service=collector` reads the latest log entries. `service` can be `collector`, `api`, `ui_access`, or `ui_error`; `limit` is optional (default 2000, maximum 10000 lines). Output is also capped at 2 MiB. `DELETE /api/v1/logs?service=collector` resets the selected log. The Logging page displays the same services in tabs and refreshes automatically. This endpoint does not require a database connection, so logs remain viewable during a database outage.

### New data notifications

`GET /api/v1/notifications` returns requests, bursts, and incidents whose IDs are newer than the stored seen cursors. The response includes totals, up to five recent entries of each type, and the latest cursor values. `PUT /api/v1/notifications/seen?request_cursor=…&burst_cursor=…&incident_cursor=…` stores the cursors in the settings table. On the first read, current maximum IDs are saved as the starting point so existing records are not reported as new.

The collector stores all detections in the shared `incident` table, with exact request membership in `incident_request`. Besides path scans (8 distinct sensitive paths), it detects failed-login clusters (5 responses 401/403), error spikes (20 responses 400+), write requests to admin/auth/API paths (5), scanner User-Agents (5), and a request-rate spike (50 requests) per source IP and host within 10 minutes. Three or more requests after at least 30 days without host activity also create an investigation lead. Error spikes show error count and non-error response share; request spikes show average, minimum, and maximum requests per second. 2xx responses to sensitive-file and exploit probes are flagged individually. These rules are heuristics and do not prove a successful attack or disclosure.

`GET /api/v1/incidents` returns paginated incidents overlapping the required `from` to `to` time range. Optional filters are `search` (IP, provider, ASN, country, city, host, or indicator), `incident_type`, and `state` (`open`, `acknowledged`, `resolved`). `incident_type` optionally filters by `path_scan`, `failed_login`, `sensitive_file_access`, `exploit_response`, `write_activity`, `http_error_spike`, `scanner_activity`, `activity_spike`, `dormant_host_activity`, `low_slow_path_scan`, or `unknown_host_404_activity`. `sort_by` supports `incident_id`, `incident_type`, `first_seen`, `last_seen`, `actor_ip`, `host`, `indicator_count`, `request_count`, and `state`; `sort_order` is `asc` or `desc`. Responses include `incident_type`, `incident_types` (all matched criteria), `indicator_count`, `indicators`, type-specific metrics in `summary`, and the IP with its provider, ASN, country, and city.

`GET /api/v1/incident_statistics` aggregates incidents in the selected period by type, detection time, actor, and host. It keeps incident counts separate from linked request counts; one request may be linked to multiple incidents. Error and request-spike values use the stored detector metrics. The parameter `include_incidents=true` adds incident details to each timeline bucket, for example for dashboard hints.

`PUT /api/v1/incidents/{incident_id}/state` persists an incident status. Its JSON body is `{"state":"acknowledged"}`; allowed values are `open`, `acknowledged`, and `resolved`. The Incidents page exposes this action directly in each status field.

### Statistics

`GET /api/v1/statistics` returns complete distributions by provider, country, host, and category for `from` and `to`, along with burst averages and extreme values. Links from distribution rows use exact filters, so a selected country or provider does not also match names that merely contain it.

### Requests

`GET /api/v1/requests` returns paginated requests for a required time range. `incident_id` restricts results to categorized requests belonging to the path-scan incident. Supported filters include:

| Parameter | Meaning |
| --- | --- |
| `from`, `to` | Required time range |
| `host` | Hostname substring |
| `actor`, `ip` | Actor IP substring |
| `actor_id` | Exact actor ID |
| `incident_id` | Requests belonging to the given path-scan incident |
| `country`, `city`, `provider`, `asn` | Actor metadata substring |
| `country_exact`, `provider_exact` | When `true`, match the country or provider exactly |
| `category` | Request category substring |
| `path` | Request path substring; set `path_exact=true` for an exact match |
| `search` | Substring search in IP, host, country, city, provider, ASN, and request path |
| `status_class` | HTTP status class: `2xx`, `3xx`, `4xx`, or `5xx` |
| `burst_id` | Requests assigned to the burst |
| `without_burst` | When `true`, return only requests without a burst assignment |
| `burst_extreme` | `min_requests`, `max_requests`, `min_duration`, or `max_duration`: requests from bursts with that extreme in the selected time range |
| `sort_by=burst_id` | Sort the request list by burst ID |
| `limit`, `offset` | Pagination |

The `search` parameter can be limited to a field with `field:term`, for example `host:inm.jvkh.de`, `path:/login`, or `pfad:/login`. English field names work regardless of the interface language; German aliases such as `pfad`, `land`, `stadt`, `anbieter`, and `kategorie` are also recognized. The Requests page additionally supports `ip`, `country`, `city`, `provider`, `asn`, `category`, `method`, `status`, `scheme`, and `ua`. Unknown field names are treated as ordinary free text. New interface languages can add their field names as search aliases.

`GET /api/v1/request_paths` returns the most frequent distinct request paths containing a search term. `from`, `to`, and `search` are required; `limit` is optional (default 100, maximum 500). The global search uses these results and opens the Requests page with an exact path filter.

`sort_by` and `sort_order` control ordering. Supported columns are `start_utc`, `request_method`, `request_path`, `user_agent`, `downstream_status`, `actor_ip`, `host`, `duration`, and `downstream_content_size`; direction is `asc` or `desc`.

The `actor` and `host` filters use substring matching by default. Exact matching is enabled by setting `actor_exact=true`, `host_exact=true`, `country_exact=true`, `provider_exact=true`, or `category_exact=true`. When `burst_extreme` is supplied, the response also includes `burst_extreme_value` and `matching_burst_count`. Multiple bursts can tie for a minimum or maximum, in which case requests from all tied bursts are shown.

```sh
curl -G 'http://localhost:8000/api/v1/requests' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'actor=203.0.113.' \
  --data-urlencode 'limit=50'
```

The response contains `items`, `total`, `limit`, `offset`, `from`, and `to`. Each item includes the request ID and time, actor and available geolocation/provider data, host, `burst_id` (`null` when the request is not assigned to a burst), method, path, scheme, status, response size, and duration. `GET /api/v1/requests/{id}` returns one request with actor, host, and category data; an unknown ID returns HTTP 404.

### Actors

`GET /api/v1/actors` returns actors with at least one request in the selected time range. With `new_only=true`, it returns only actors whose `first_time` falls in that range. It supports `from`, `to`, substring filters `provider`, `country`, `city`, `asn`, and `ip`, plus `country_exact=true` and `ip_exact=true` for exact matching. `search` searches IP, city, provider, and ASN; `global_search` searches IP, country, city, and ASN. Pagination uses `limit` and `offset`. `sort_by` supports `ip`, `first_time`, `last_time`, `provider`, `asn`, `city`, `country`, and `request_count`; `sort_order` is `asc` or `desc`.

`GET /api/v1/countries` returns countries with requests in the selected period. `GET /api/v1/actors/{id}` returns an actor profile, including request and burst totals over the full stored history. `DELETE /api/v1/actors/{id}` deletes an actor and its requests and bursts through foreign-key cascades. The response includes the IP and deleted request and burst counts; the action is recorded in the API log.

```sh
curl -G 'http://localhost:8000/api/v1/actors' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'country=Germany' \
  --data-urlencode 'new_only=true'
```

### Bursts

`GET /api/v1/bursts` returns bursts whose start time falls in the selected time range. Filters include `actor` (IP substring), `actor_id` (exact), `host`, `country`, `provider`, `asn`, and `city` (substrings), `search` (substring in burst ID, IP, provider, ASN, or city), `limit`, and `offset`. Set `host_exact=true` or `country_exact=true` for exact host or country matching. `sort_by` supports `burst_id`, `start_time`, `actor_ip`, `host`, `country`, `duration`, `requests`, and `avg_count`; `sort_order` is `asc` or `desc`.

The response contains `summary` and paginated `items`. Summary metrics include totals for bursts, actors, and requests; request method counts; and average, median, and maximum values for requests per burst, burst duration, and bursts per actor.

```sh
curl -G 'http://localhost:8000/api/v1/bursts' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'country=Germany'
```

`GET /api/v1/bursts/{id}` returns a burst. `GET /api/v1/burst_requests/{id}` returns its associated requests and their count (`total`).

### Request counts, hosts, and categories

`GET /api/v1/request_counts` returns counts in equally sized time buckets. Required parameters: `from`, `to`, and `bars` (1–500). Optional filters: `host`, `actor_ip`, `actor_id`, `incident_id`, `category`, `path`, `path_exact`, `burst_id`, `without_burst`, `search`, and `status_class`. The response includes `items` with `from`, `to`, `read_count`, `write_count`, `other_count`, and `total_count` for each bucket; empty buckets have zero counts.

`GET /api/v1/categories` requires `from` and `to`, with an optional `category` substring filter. Results are grouped by category and include read/write/other method counts and HTTP/HTTPS/other-scheme counts. `sort_by` supports `category_name`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count`, `traffic_share`, and `https_share`; `sort_order` is `asc` or `desc`.

`GET /api/v1/hosts` has the same time range and count breakdown, grouped by host, with an optional `host` substring filter and `known=own|foreign` filter. Each host includes a `known` flag; `known_count` reports the configured number of known hosts. `sort_by` supports `host`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count`, and `https_share`; `sort_order` is `asc` or `desc`.

`GET /api/v1/statistics` returns the leading providers, countries, hosts, and categories for `from` and `to`. `limit` sets the number of rows per group (default 10, maximum 50). `request_count` is the absolute count; `share_percent` is relative to all requests in the selected period. Since a request can have multiple categories, category shares can add up to more than 100%.

### Read and change stored settings

`GET /api/v1/params` requires `group_name`. Include `name` to retrieve one setting; omit it to retrieve the whole group.

```sh
curl -G 'http://localhost:8000/api/v1/params' --data-urlencode 'group_name=collector'
curl -G 'http://localhost:8000/api/v1/params' --data-urlencode 'group_name=collector' --data-urlencode 'name=last_import'
```

`PUT /api/v1/params` requires `group_name` and `name`. If `value` is present, it is saved or updated; if omitted, the setting is deleted. An explicitly empty value can be saved with `value=`.

The UI stores language, theme, time range, and other preferences in the `ui_preferences` group. The single administrator login protects access; settings remain shared across the installation. Updating the settings table does not change Docker environment variables. Values from `.env` are read when containers start; restart the affected service after editing `.env`.

```sh
curl -X PUT -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector' \
  --data-urlencode 'name=example' \
  --data-urlencode 'value=enabled'

curl -X PUT -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector' \
  --data-urlencode 'name=example'
```

### Trigger collector import or maintenance

`PUT /api/v1/import` starts an import regardless of the configured interval. `PUT /api/v1/maintenance` does the same for maintenance. Neither endpoint takes parameters or a request body.

```sh
curl -X PUT http://localhost:8000/api/v1/import
curl -X PUT http://localhost:8000/api/v1/maintenance
```

Accepted requests return HTTP 202, for example `{"status":"accepted","activity":"Import"}`. The work runs in the background; progress is available from `/api/v1/status`.

## Error responses

| HTTP status | Meaning |
| --- | --- |
| 404 | Requested request/actor/burst ID or settings group/entry was not found |
| 422 | Invalid or missing parameters, such as `from >= to` |
| 409 | Collector is already importing or running maintenance (`collector_busy`) |
| 502 | Collector rejected the operation or returned an invalid response (`collector_error`) |
| 503 | Database or collector is temporarily unavailable |
| 500 | Unexpected API error (`internal_server_error`) |

API infrastructure errors use `{"error":{"code":"…","message":"…"}}`. FastAPI validation and not-found errors retain FastAPI's `detail` format. The status endpoint is an exception: it catches failures and reports a degraded state with HTTP 200.

## Collector behavior and configuration

The collector reads files in `LOG_FILES`, parses Traefik access logs in JSON-lines format, and writes requests, actors, hosts, categories, and bursts to the shared database. Its control service listens on port `8001` inside the Compose network; that port is not published on the host. The API listens internally on port `8000`; Compose binds its host port to `127.0.0.1` only. Browser requests go through the UI's internal `/api` proxy.

Scheduled and manual operations share a lock. If the collector is busy, a manual request is rejected with HTTP 409 rather than run concurrently. Accepted manual operations run in the background. The scheduler runs due jobs when the collector starts and schedules the next run after the current run completes.

### Input files and retention

`LOG_FILES` contains one or more semicolon-separated filenames, for example:

```dotenv
LOG_FILES=access.log
```

Compose mounts the host directory in `INPUT_LOG_DIR` read-only at `/input-logs`. `LOG_FILES` names files in that directory. The setup accepts the full host path to an input log file, saves its directory in `INPUT_LOG_DIR`, and stores only its filename in `LOG_FILES`. The default host directory is `./logs`.

The Traefik reader processes complete JSON lines before the end-of-file buffer configured by `INPUT_SAVE_MARGIN_CHARACTERS` in the active file. The value must be greater than zero. Matching rotated segments (`access.log.*`, including `.gz`) are discovered automatically and read through EOF in time order. Positions are keyed by device/inode identity and follow renamed segments. A SHA-256 fingerprint of the first complete log line (up to 64 KiB) detects a new file if an inode is reused. The fingerprint, position, and request are committed together. The collector never changes or deletes log files; logrotate handles rotation and retention.

### Configuration reference

The collector variables appear with their effective values in status. `INPUT_LOG_DIR` and `GEOLITE_DB_DIR` are also read by Compose to mount host directories.

| Variable | Code default | Purpose |
| --- | --- | --- |
| `LOG_FILES` | empty | Semicolon-separated filenames in `/input-logs`; legacy `type:path` entries remain supported |
| `INPUT_LOG_DIR` | Compose default `./logs` | Compose: host access-log directory, mounted read-only at `/input-logs` |
| `GEOLITE_DB_DIR` | Compose default `./databases/geoip` | Compose: host directory containing GeoLite2 files, mounted read-only at `/geoip` |
| `INPUT_INTERVAL_SECONDS` | `3600` | Interval between imports, in seconds |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Number of characters held back at the end of each file; must be positive |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Interval between maintenance runs, in days |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Inactivity period used to remove old actors and related data |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximum gap between requests in one burst |
| `BURST_MIN_REQUESTS` | `5` | Minimum requests in a burst |
| `BURST_WINDOW_SECONDS` | `60` | Burst detection window |
| `INCIDENT_MERGE_OVERLAP_PERCENT` | `80` | Minimum overlap, as a percentage of the shorter incident's time range, for merging incidents from the same actor; values 0–100 |
| `LOW_SLOW_SCAN_WINDOW_SECONDS` | `10800` | Rolling time window for low-and-slow multi-host path scans |
| `LOW_SLOW_SCAN_MIN_PATHS` | `12` | Minimum number of distinct sensitive or error paths |
| `LOW_SLOW_SCAN_MIN_HOSTS` | `2` | Minimum number of distinct hosts |
| `LOW_SLOW_SCAN_MIN_SPAN_SECONDS` | `300` | Minimum time between the first and last matching request |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Container path to the optional GeoLite City database |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Container path to the optional GeoLite ASN database |
| `IGNORE_REQUEST_ROUTES` | empty | Semicolon-separated `host/path-prefix` routes to skip |
| `KNOWN_HOSTS` | empty | Semicolon-separated list of host names belonging to this installation |

A host/path prefix is skipped only for the configured host. The path must match exactly or start at a `/` segment boundary; `assets` skips `/assets/app.js` but not `/assets-old/app.js`. Example for `.env`:

```dotenv
IGNORE_REQUEST_ROUTES=inm2.example.de/api;inm2.example.de/assets
```

In Compose, collector variables come from `.env`. `./logs` and `./databases` are mounted for operational logs and database storage. The host directories from `INPUT_LOG_DIR` and `GEOLITE_DB_DIR` are mounted read-only at `/input-logs` and `/geoip`. The API shares the database directory with the collector. If a GeoLite file is absent, importing continues and the corresponding fields remain empty.

Maintenance removes actors that have been inactive longer than `MAINTENANCE_INACTIVE_DAYS`, along with dependent records. Imported actor history is therefore not necessarily retained indefinitely.
