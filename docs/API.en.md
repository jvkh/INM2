# Using the API and collector

[Deutsche Version](API.de.md) · [Installation guide](../README.en.md)

This guide describes the HTTP API and collector operations for developers and operators. For installing and running the complete application, see the [repository README](../README.en.md).

## Connection and interactive documentation

In the Compose setup, the API is published at `http://localhost:8000`. Data routes are under `/api/v1`. FastAPI also provides interactive OpenAPI documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

```sh
curl http://localhost:8000/api/v1/status
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

`GET /api/v1/metric_trends` returns metrics for the selected range and the immediately preceding range of equal duration. `from` and `to` are required; `page` can be `dashboard`, `bursts`, `actors`, `hosts`, `categories`, or `requests`. List views accept their active filters so the trend reflects the same selection. Each entry in `metrics` contains current and previous values, percentage change, and direction (`up`, `down`, `steady`). Changes of up to 5% are steady. An empty comparison range returns `0%` and `steady`.

### Status

`GET /api/v1/status` reports API/database health, stored collector status, and supported non-sensitive configuration values. It does not expose credentials or arbitrary process environment variables.

```sh
curl http://localhost:8000/api/v1/status
```

A healthy response includes `status: "ok"`, `database: "ok"`, `collector_status`, and `environment`. `collector_status.import_file` is populated while a file is being processed. `collector_status.last_import_file` retains the most recently started filename after an import finishes. If the status handler cannot read the database or settings, it still returns HTTP 200 with `status: "degraded"`, `database: "unavailable"`, and an unavailable collector status.

### New data notifications

`GET /api/v1/notifications` returns requests and bursts whose IDs are newer than the stored seen cursors. The response includes totals, up to five recent entries of each type, and the latest cursor values. `PUT /api/v1/notifications/seen?request_cursor=…&burst_cursor=…` stores the cursors in the settings table. On the first read, current maximum IDs are saved as the starting point so existing records are not reported as new.

### Requests

`GET /api/v1/requests` returns paginated requests for a required time range. Supported filters include:

| Parameter | Meaning |
| --- | --- |
| `from`, `to` | Required time range |
| `host` | Hostname substring |
| `actor`, `ip` | Actor IP substring |
| `actor_id` | Exact actor ID |
| `country`, `city`, `provider`, `asn` | Actor metadata substring |
| `category` | Request category substring |
| `path` | Request path substring; set `path_exact=true` for an exact match |
| `search` | Substring search in IP, host, country, city, provider, ASN, and request path |
| `status_class` | HTTP status class: `2xx`, `3xx`, `4xx`, or `5xx` |
| `burst_id` | Requests assigned to the burst |
| `limit`, `offset` | Pagination |

The `search` parameter can be limited to a field with `field:term`, for example `host:inm.jvkh.de`, `path:/login`, or `pfad:/login`. English field names work regardless of the interface language; German aliases such as `pfad`, `land`, `stadt`, `anbieter`, and `kategorie` are also recognized. The Requests page additionally supports `ip`, `country`, `city`, `provider`, `asn`, `category`, `method`, `status`, `scheme`, and `ua`. Unknown field names are treated as ordinary free text. New interface languages can add their field names as search aliases.

`GET /api/v1/request_paths` returns the most frequent distinct request paths containing a search term. `from`, `to`, and `search` are required; `limit` is optional (default 100, maximum 500). The global search uses these results and opens the Requests page with an exact path filter.

`sort_by` and `sort_order` control ordering. Supported columns are `start_utc`, `request_method`, `request_path`, `user_agent`, `downstream_status`, `actor_ip`, `host`, `duration`, and `downstream_content_size`; direction is `asc` or `desc`.

The `actor` and `host` filters use substring matching by default. Set `actor_exact=true`, `host_exact=true`, or `category_exact=true` to match the value exactly.

```sh
curl -G 'http://localhost:8000/api/v1/requests' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'actor=203.0.113.' \
  --data-urlencode 'limit=50'
```

The response contains `items`, `total`, `limit`, `offset`, `from`, and `to`. Each item includes the request ID and time, actor and available geolocation/provider data, host, method, path, scheme, status, response size, and duration. `GET /api/v1/requests/{id}` returns one request with actor, host, and category data; an unknown ID returns HTTP 404.

### Actors

`GET /api/v1/actors` returns actors with at least one request in the selected time range. With `new_only=true`, it returns only actors whose `first_time` falls in that range. It supports `from`, `to`, substring filters `provider`, `country`, `city`, `asn`, and `ip`, plus `country_exact=true` and `ip_exact=true` for exact matching. `search` searches IP, city, provider, and ASN; `global_search` searches IP, country, city, and ASN. Pagination uses `limit` and `offset`. `sort_by` supports `ip`, `first_time`, `last_time`, `provider`, `asn`, `city`, `country`, and `request_count`; `sort_order` is `asc` or `desc`.

`GET /api/v1/countries` returns countries with requests in the selected period. `GET /api/v1/actors/{id}` returns an actor profile, including request and burst totals over the full stored history.

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

`GET /api/v1/request_counts` returns counts in equally sized time buckets. Required parameters: `from`, `to`, and `bars` (1–500). Optional filters: `host`, `actor_ip`, `actor_id`, `category`, `path`, `path_exact`, `burst_id`, `search`, and `status_class`. The response includes `items` with `from`, `to`, `read_count`, `write_count`, `other_count`, and `total_count` for each bucket; empty buckets have zero counts.

`GET /api/v1/categories` requires `from` and `to`, with an optional `category` substring filter. Results are grouped by category and include read/write/other method counts and HTTP/HTTPS/other-scheme counts. `sort_by` supports `category_name`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count`, `traffic_share`, and `https_share`; `sort_order` is `asc` or `desc`.

`GET /api/v1/hosts` has the same time range and count breakdown, grouped by host, with an optional `host` substring filter. `sort_by` supports `host`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count`, and `https_share`; `sort_order` is `asc` or `desc`.

### Read and change stored settings

`GET /api/v1/params` requires `group_name`. Include `name` to retrieve one setting; omit it to retrieve the whole group.

```sh
curl -G 'http://localhost:8000/api/v1/params' --data-urlencode 'group_name=collector'
curl -G 'http://localhost:8000/api/v1/params' --data-urlencode 'group_name=collector' --data-urlencode 'name=last_import'
```

`PUT /api/v1/params` requires `group_name` and `name`. If `value` is present, it is saved or updated; if omitted, the setting is deleted. An explicitly empty value can be saved with `value=`.

The UI stores language, theme, time range, and other preferences in the `ui_preferences` group. Since the application has no user accounts, these preferences are shared by everyone using the installation. Updating the settings table does not change Docker environment variables. Values from `.env` are read when containers start; restart the affected service after editing `.env`.

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

Accepted requests return HTTP 202, for example `{"status":"accepted","activity":"Import"}`. The work runs in the background; use `/api/v1/status` to inspect progress.

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

The collector reads files in `LOG_FILES`, parses Traefik access logs in JSON-lines format, and writes requests, actors, hosts, categories, and bursts to the shared database. Its control service listens on port `8001` inside the Compose network; that port is not published on the host. The API on port `8000` is the client-facing service.

Scheduled and manual operations share a lock. If the collector is busy, a manual request is rejected with HTTP 409 rather than run concurrently. Accepted manual operations run in the background. The scheduler runs due jobs when the collector starts and schedules the next run after the current run completes.

### Input files and retention

`LOG_FILES` contains one or more semicolon-separated `type:path` entries, for example:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

The Traefik reader processes complete JSON lines before the end-of-file buffer configured by `INPUT_SAVE_MARGIN_CHARACTERS`. The value must be greater than zero. After successful storage, the collector removes the processed prefix and moves the unprocessed remainder to the beginning of the input file. The configured log is a working file, not an archive; archive logs separately if they must be retained.

### Configuration reference

The collector supports these variables. The values below are code defaults from `common/env.py`; `.env.example` may set different starting values.

| Variable | Code default | Purpose |
| --- | --- | --- |
| `LOG_FILES` | empty | Semicolon-separated input files in `type:path` format |
| `INPUT_INTERVAL_SECONDS` | `3600` | Interval between imports, in seconds |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Number of characters held back at the end of each file; must be positive |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Interval between maintenance runs, in days |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Inactivity period used to remove old actors and related data |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximum gap between requests in one burst |
| `BURST_MIN_REQUESTS` | `5` | Minimum requests in a burst |
| `BURST_WINDOW_SECONDS` | `60` | Burst detection window |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Container path to the optional GeoLite City database |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Container path to the optional GeoLite ASN database |
| `IGNORE_REQUEST_ROUTES` | empty | Semicolon-separated `host/path-prefix` routes to skip |

A host/path prefix is skipped only for the configured host. The path must match exactly or start at a `/` segment boundary; `assets` skips `/assets/app.js` but not `/assets-old/app.js`. Example for `.env`:

```dotenv
IGNORE_REQUEST_ROUTES=inm2.example.de/api;inm2.example.de/assets
```

In Compose, collector variables come from `.env`. `./logs` and `./databases` are mounted in the collector; `./databases/geoip` is mounted read-only. The API shares the database directory with the collector. If a GeoLite file is absent, importing continues and the corresponding fields remain empty.

Maintenance removes actors that have been inactive longer than `MAINTENANCE_INACTIVE_DAYS`, along with dependent records. Imported actor history is therefore not necessarily retained indefinitely.
