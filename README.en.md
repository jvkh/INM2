# Internet Noise Monitor (INM2)

[Deutsche Version](README.de.md)

Changelog: [English](CHANGELOG.en.md) · [Deutsch](CHANGELOG.de.md)

Current project version: [`VERSION`](VERSION).

INM2 processes Traefik access logs and displays requests, actors, hosts, categories, detected bursts, and path-scan incidents in a web dashboard. The application consists of a React UI, a FastAPI API, and a collector. Both backend services read and write the same SQLite database.

## Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose`)
- Access to Traefik access logs in JSON-lines format
- For optional IP geolocation: locally supplied MaxMind GeoLite2 City and/or ASN databases, obtained under the applicable terms

The Compose project builds all three images locally. It publishes the UI on host port `3000`. The API port `8000` is bound to the server's loopback interface only; the UI proxies `/api` to it over the Compose network. The collector's internal control port (`8001`) is not published on the host. The API requires its own administrator password and signed session.

## Installation and first start

```sh
git clone <REPOSITORY-URL>
cd <REPOSITORY-DIRECTORY>
./scripts/setup-linux.sh
```

The interactive Linux setup checks Docker Engine with Compose v2, the Docker service, project files, and write permissions. It guides configuration of required settings, ports, access security, detection, import, and maintenance. For the log source, it checks that the path points to a file and whether it is empty. The collector's access permissions and the JSON format are checked during import. The setup checks whether the UI port is in use and suggests an available port if needed. OpenSSL is required to generate the session secret. Existing `.env` files are backed up before changes; other entries are preserved. The admin password can be changed in the setup. A separate menu item lists `.env.backup.*` files for deletion after confirmation.

The setup asks for the full host path to an input log file, for example `/var/log/my-service/access.log`. It mounts that directory read-only in the collector. `LOG_FILES` then contains only the filename; rotated files such as `access.log.1` and `access.log.2.gz` are discovered automatically. The host directory can later be changed through `INPUT_LOG_DIR` in `.env`.

The setup checks the log source and UI port. It does not start the application. After configuration, start it with `docker compose up -d --build`.

### Example: Traefik Docker provider

When Traefik uses the Docker provider, router labels for the UI can be added through a `docker-compose.override.yml` in the INM2 directory. The domain, Docker network, certificate resolver, and optional middleware must match the existing Traefik installation:

```yaml
services:
  ui:
    networks:
      - default
      - traefik-proxy
    labels:
      - traefik.enable=true
      - traefik.docker.network=traefik-proxy
      - traefik.http.routers.inm2.rule=Host(`inm2.example.org`)
      - traefik.http.routers.inm2.entrypoints=websecure
      - traefik.http.routers.inm2.tls=true
      - traefik.http.routers.inm2.tls.certresolver=letsencrypt
      - traefik.http.services.inm2.loadbalancer.server.port=80
      # Optional, if Traefik middleware is used:
      # - traefik.http.routers.inm2.middlewares=auth-chain@file

networks:
  traefik-proxy:
    external: true
    name: traefik-proxy
```

`traefik-proxy` must be an existing Docker network also used by the Traefik container. This example assumes that the Docker provider is enabled and that `websecure` and the `letsencrypt` certificate resolver are configured in Traefik. Middleware is optional. The UI listens on port `80` in the container; `INM2_UI_PORT` is an additional published host port and is not used as the Traefik target in this Docker network example. File-based Traefik configurations and other network setups require the corresponding service target.

```dotenv
INPUT_LOG_DIR=/var/log/my-service
LOG_FILES=access.log
```

The administrator password must not be stored in plaintext in `.env`. A scrypt hash can be generated with the following command; the prompt hides the password:

```sh
docker compose run --rm --no-deps --entrypoint python api -m api.password_hash
```

The password is entered twice. The generated hash and a separate session signing secret belong in `.env`:

```dotenv
INM2_ADMIN_PASSWORD_HASH='<hash-output>'
INM2_AUTH_SECRET=<output-of-openssl-rand-hex-32>
INM2_COOKIE_SECURE=true
INM2_TOTP_ENABLED=true
INM2_TOTP_SECRET=<Base32-secret>
```

The secret is generated with `openssl rand -hex 32`. The `.env` file must be kept private. `INM2_COOKIE_SECURE=true` is required for HTTPS; `false` is reserved for local HTTP development. The API refuses to start if the hash or signing secret is missing or invalid. Password changes require a new hash and an API service restart. Changing the signing secret signs out every active session. The hash uses scrypt; a long, unique password is required.

The second factor is configured by generating a key with `docker compose run --rm --no-deps --entrypoint python api -m api.totp_secret`. The printed `INM2_TOTP_SECRET` line is added to `.env`; the authenticator app is configured using the displayed setup key or URI. `INM2_TOTP_ENABLED=true` requires the code; `false` keeps password-only sign-in. When enabled, the API refuses to start without a valid secret. The device clock must be synchronized. Codes are valid for 30 seconds and can be used only once during the API process lifetime.

The collector reads the access log and its rotated segments read-only. It does not modify or delete the source files; import positions are stored in the SQLite database.

Data directories and application startup:

```sh
mkdir -p logs databases/geoip
docker compose up -d --build
```

For local HTTP access, `INM2_COOKIE_SECURE=false` is required; for HTTPS it remains `true`. The UI is available at `http://localhost:<INM2_UI_PORT>` (default `3000`); sign-in uses the administrator password. The UI proxies API calls internally. The API port (default `8000`) is bound to `127.0.0.1` for local administration and reverse proxies on the same server. Due jobs run immediately when the collector starts. Imports process only complete JSON lines in the configured Traefik format.

## Configuration

Compose loads collector and authentication settings from `.env`. Compose also reads the host directories for Traefik and GeoLite files from that file. `.env.example` contains recommended starting values. Empty or unset collector values fall back to the defaults defined in `common/env.py`; authentication values are required.

| Variable | Example value / default | Description |
| --- | --- | --- |
| `INPUT_LOG_DIR` | `./logs` | Host directory containing input log files; mounted read-only at `/input-logs`. |
| `LOG_FILES` | Example `access.log`; code default is empty | One or more filenames in `INPUT_LOG_DIR`, separated by semicolons. The collector reads Traefik JSON lines and matching rotated files. |
| `GEOLITE_DB_DIR` | `./databases/geoip` | Compose host directory containing GeoLite2 databases; mounted read-only at `/geoip`. |
| `INM2_UI_PORT` | `3000` | Host port for the web interface; another value is required if the port is already in use. |
| `INM2_API_PORT` | `8000` | Local host port for the API, bound to `127.0.0.1`; another value is required if the port is already in use. |
| `INM2_COLLECTOR_PORT` | `8001` | Internal control port on the Compose network; not published on the host. Change only if the port is occupied inside the container. |
| `INPUT_INTERVAL_SECONDS` | Example `60`; default `3600` | Interval between imports, in seconds. |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Character buffer at the end of the file to avoid importing incomplete lines; must be positive. |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Interval between maintenance runs, in days. |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Maintenance removes inactive actors and related data after this period. |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximum gap between requests in the same burst. |
| `BURST_MIN_REQUESTS` | Default `5` | Minimum number of requests for a burst. |
| `BURST_WINDOW_SECONDS` | Default `60` | Burst detection time window. |
| `INCIDENT_MERGE_OVERLAP_PERCENT` | Default `80` | Combines criteria for the same actor when more than this percentage of the shorter incident's time range overlaps (0–100). |
| `LOW_SLOW_SCAN_WINDOW_SECONDS` | `10800` | Rolling time window for low-and-slow multi-host path scans (3 hours). |
| `LOW_SLOW_SCAN_MIN_PATHS` | `12` | Required distinct sensitive or error paths; this already implies the minimum request count. |
| `LOW_SLOW_SCAN_MIN_HOSTS` | `2` | Required distinct hosts. |
| `LOW_SLOW_SCAN_MIN_SPAN_SECONDS` | `300` | Minimum time between the first and last matching request (5 minutes). |
| `UNKNOWN_HOST_404_WINDOW_DAYS` | `7` | Rolling window for repeated 404 requests to unknown hosts. |
| `UNKNOWN_HOST_404_MIN_REQUESTS` | `50` | Minimum number of such requests from the same actor and User-Agent. |
| `UNKNOWN_HOST_404_MIN_HOSTS` | `3` | Minimum number of distinct unknown hosts for an incident. |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Container path to the optional City database. |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Container path to the optional ASN database. |
| `IGNORE_REQUEST_ROUTES` | empty | Semicolon-separated `host/path-prefix` entries to skip during import. Host must match Traefik's `RequestHost`. |
| `KNOWN_HOSTS` | empty | Semicolon-separated host names belonging to this installation; each entry also matches all subdomains and is shown/filterable as an own host. |
| `INM2_ADMIN_PASSWORD_HASH` | required | scrypt hash for the single administrator password, generated inside the API container with the command above. Plaintext passwords do not belong in `.env`. |
| `INM2_AUTH_SECRET` | required | Private session signing secret, at least 32 bytes; generation with `openssl rand -hex 32`. |
| `INM2_COOKIE_SECURE` | `true` | Restricts the session cookie to HTTPS. `false` is intended only for local HTTP development. |
| `INM2_TOTP_ENABLED` | `false` | Requires a six-digit TOTP code in addition to the password when set to `true`. |
| `INM2_TOTP_SECRET` | required when TOTP is enabled | Secret Base32 key for the authenticator app; generated with `python -m api.totp_secret` and requires secure storage. |

### GeoLite2 databases (optional)

The host directory set by `GEOLITE_DB_DIR` (default `databases/geoip/`) contains the properly obtained files:

- `databases/geoip/GeoLite2-City.mmdb`
- `databases/geoip/GeoLite2-ASN.mmdb`

Compose mounts this directory read-only at `/geoip`. If a database is missing, imports continue and the corresponding geolocation/ASN fields remain empty. These files are not included in the repository.

### Ports and data

| Service | Host port | Container port | Purpose |
| --- | --- | --- | --- |
| UI | `3000` | `80` | Web interface |
| API | `127.0.0.1:8000` only | `8000` | REST API and FastAPI documentation; the UI uses the Compose network |
| Collector | not published | `INM2_COLLECTOR_PORT` (default `8001`) | Internal control service on the Compose network |

Compose mounts `./databases` at `/app/databases` for both API and collector and `./logs` at `/logs` for operational logs. The host directories set by `INPUT_LOG_DIR` and `GEOLITE_DB_DIR` are mounted read-only at `/input-logs` and `/geoip`. The SQLite file is created at `databases/inm2.sqlite3`. Regular backups of `databases/` are recommended.

## Using the application

The UI provides Dashboard, Bursts, Actors, Hosts, Categories, Requests, and administration features. Access requires the configured single administrator password; a new sign-in is required after 12 hours without user activity. Automatic background refreshes do not extend the session. Language (German/English), theme, and time range are stored in the shared SQLite database. Settings and data are shared across the installation.

API routes are under `/api/v1`. The status is available after sign-in at:

```sh
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

See [docs/API.en.md](docs/API.en.md) for further API documentation and examples. Scheduled maintenance removes inactive actors and dependent data according to `MAINTENANCE_INACTIVE_DAYS`.

## Updating

Before updating, backups of `databases/` and `.env` are recommended. The desired change is incorporated in the cloned repository, followed by an image rebuild:

```sh
git pull
docker compose up -d --build
```

The Compose setup uses no external database service or versioned image tags; images are built from the current working tree. The UI and status endpoint should be checked after the update.

## Stopping and troubleshooting

```sh
docker compose ps
docker compose logs --tail=100
docker compose logs --tail=100 collector
docker compose logs --tail=100 api
docker compose logs --tail=100 ui
docker compose down
```

`docker compose down` removes containers and the network; mounted data directories remain. `docker compose down -v` is not intended for routine stops.

- **UI unavailable:** Possible causes include host port `3000` already being in use or the UI container not running.
- **API unavailable:** `docker compose logs api` shows the API logs. From the host, the API is available at `127.0.0.1:8000`; the web interface reaches it internally.
- **No requests:** Relevant settings are `INPUT_LOG_DIR`, the filenames in `LOG_FILES`, and host-file read permissions. The file must contain Traefik JSON lines. The collector skips private, loopback, link-local, reserved, and invalid client IP addresses.
- **Geolocation/ASN fields are empty:** Relevant settings are `GEOLITE_DB_DIR` and the filenames `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb`; imports work without the optional databases.
- **Collector status:** `/api/v1/status` reports collector and database status.

## Local UI development

Node.js/npm are required for the UI. The Vite development server proxies `/api` to `http://localhost:8000`. The API must be running first, for example through Compose. The following commands run in `ui/`:

```sh
npm install
npm run dev
```

## License

INM2 is licensed under the [MIT License](LICENSE). MaxMind GeoLite2 files are not part of this repository and are subject to MaxMind's terms of use.
