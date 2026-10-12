# Architecture and data flow

[Deutsche Version](ARCHITECTURE.de.md) · [Installation guide](../README.en.md)

INM2 consists of three services started with Docker Compose. The collector reads Traefik access logs, the API serves stored data, and the React UI calls that API from the browser. The collector and API share a SQLite database.

## Services

| Service | Implementation | Responsibility | Compose availability |
| --- | --- | --- | --- |
| `ui` | React, TypeScript, Nginx | Dashboard and web interface; Nginx forwards `/api/` to the API. | Host port `3000`, container port `80` |
| `api` | FastAPI, Uvicorn | REST endpoints under `/api/v1`, database access, and forwarding manual collector jobs. | Host port `8000`, container port `8000` |
| `collector` | Python, Uvicorn control service | Imports logs, optionally adds geolocation/ASN data, detects bursts, and runs maintenance. | Control port `8001` on the internal Compose network only |

Compose builds the images from the Dockerfiles in the repository. The UI and API are published on host ports; the Compose setup does not configure authentication or access control.

## Data flow

1. The collector reads files configured in `LOG_FILES`. The supported reader type is `traefik`, which expects one JSON object per line.
2. Complete, processable lines are converted into requests, actors, hosts, categories, and bursts. Only globally routable client IP addresses are imported; private, loopback, link-local, reserved, and invalid addresses are skipped.
3. When available, the collector adds city/country and ASN/provider data from local GeoLite2 MMDB files. This enrichment is optional.
4. The collector and API use the same SQLite file at `databases/inm2.sqlite3`. The UI accesses data only through HTTP requests to the API.
5. Scheduled and manually triggered imports and maintenance share a lock. Manual jobs run in the background; if the collector is busy, the API returns `409`.

## Import behavior and log files

`INPUT_SAVE_MARGIN_CHARACTERS` leaves a buffer at the end of the file so incomplete log lines are not processed. After successful storage, the reader removes the processed prefix from the input file and moves the remainder to the beginning. A configured log file is therefore a mutable working file, not an archive. Configure rotation or archival so the collector and rotation process do not modify the same file concurrently.

In Compose, `./logs` is mounted at `/logs`. Example:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Multiple entries can be separated with semicolons. `IGNORE_REQUEST_ROUTES` can skip requests for configured host/path prefixes.

## Scheduling and maintenance

The scheduler runs due jobs when the collector starts and schedules each next run after the current run finishes. `INPUT_INTERVAL_SECONDS` controls the import interval; `MAINTENANCE_INTERVAL_DAYS` controls the maintenance interval. Maintenance removes actors inactive for longer than `MAINTENANCE_INACTIVE_DAYS`, along with dependent data.

## Persistence and mounts

- `./databases` is mounted at `/app/databases` for the API and collector and contains the SQLite database.
- `./logs` is mounted at `/logs` for the collector.
- `./databases/geoip` is mounted read-only at `/geoip`.

Compose uses host bind mounts. Back up and monitor the database on the host. Because the imported log file is consumed by prefix, it is not suitable as a backup or archive.

## Configuration

Compose loads collector environment variables from `.env`. Supported variables and code defaults are documented in [API.en.md – Collector configuration](API.en.md#configuration); example startup values are in [`../.env.example`](../.env.example). Restart the collector after changing `.env` for the new values to take effect.

Compose sets `COLLECTOR_CONTROL_URL` for the API; its default is `http://collector:8001`. Database paths are defined in `common/database.py`.

## Related documentation

- [Installation, operation, and troubleshooting](../README.en.md)
- [Using the API and collector](API.en.md)
- [API und Collector verwenden (Deutsch)](API.de.md)
