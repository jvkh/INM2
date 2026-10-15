# Internet Noise Monitor (INM2)

[Deutsche Version](README.de.md)

Changelog: [English](CHANGELOG.en.md) · [Deutsch](CHANGELOG.de.md)

Current project version: [`VERSION`](VERSION).

INM2 processes Traefik access logs and displays requests, actors, hosts, categories, and detected bursts in a web dashboard. The application consists of a React UI, a FastAPI API, and a collector. Both backend services read and write the same SQLite database.

## Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose`)
- Access to Traefik access logs in JSON-lines format
- For optional IP geolocation: locally supplied MaxMind GeoLite2 City and/or ASN databases, obtained under the applicable terms

The Compose project builds all three images locally. It publishes the UI on host port `3000` and the API on host port `8000`. The collector's internal control port (`8001`) is not published on the host. The API requires its own administrator password and signed session. A reverse-proxy access layer can remain in front of it as an additional barrier.

## Installation and first start

```sh
git clone <REPOSITORY-URL>
cd <REPOSITORY-DIRECTORY>
cp .env.example .env
```

Edit `.env` and set `LOG_FILES` to the path of the Traefik access log **inside the collector container**. The project directory `./logs` is mounted as `/logs`. For a file at `./logs/access.log`, use:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Do not put the administrator password itself in `.env`. Generate a scrypt hash instead; the prompt hides the password:

```sh
docker compose run --rm --no-deps --entrypoint python api -m api.password_hash
```

Enter the password twice when prompted, then put the generated hash and a separate session signing secret in `.env`:

```dotenv
INM2_ADMIN_PASSWORD_HASH='<hash-output>'
INM2_AUTH_SECRET=<output-of-openssl-rand-hex-32>
INM2_COOKIE_SECURE=true
INM2_TOTP_ENABLED=true
INM2_TOTP_SECRET=<Base32-secret>
```

Generate the secret with `openssl rand -hex 32`. Keep `.env` private. Leave `INM2_COOKIE_SECURE=true` when using HTTPS; set it to `false` only for local HTTP development. The API refuses to start if the hash or signing secret is missing or invalid. To change the password, generate a new hash and restart the API service; changing the signing secret signs out every active session. The hash uses scrypt; use a long, unique password.

To configure the second factor, generate a key with `docker compose run --rm --no-deps --entrypoint python api -m api.totp_secret`. Copy the printed `INM2_TOTP_SECRET` line into `.env` and set up your authenticator app using the displayed setup key or URI. `INM2_TOTP_ENABLED=true` requires the code; `false` keeps password-only sign-in. When enabled, the API refuses to start without a valid secret. Keep the device clock synchronized. Codes are valid for 30 seconds and can be used only once during the API process lifetime.

The collector must have read and write access to the log file: after a successful import, processed lines are removed from the beginning of the file. Arrange separate archival outside this working file if needed.

Create the data directories and start the application:

```sh
mkdir -p logs databases/geoip
docker compose up -d --build
```

For local HTTP access, set `INM2_COOKIE_SECURE=false`; leave it `true` for HTTPS access. Then open [http://localhost:3000](http://localhost:3000) and sign in with the administrator password. The API is available on port `8000`; its interactive documentation is also protected. Due jobs run immediately when the collector starts. Imports process only complete JSON lines in the configured Traefik format.

## Configuration

Compose loads collector and authentication settings from `.env`. `.env.example` contains this repository's recommended starting values. Empty or unset collector values fall back to the defaults defined in `common/env.py`; authentication values are required.

| Variable | Example value / default | Description |
| --- | --- | --- |
| `LOG_FILES` | Example: `traefik:/logs/access.log`; code default is empty | One or more `type:path` inputs, separated by semicolons. The collector reads Traefik JSON lines. |
| `INPUT_INTERVAL_SECONDS` | Example `60`; default `3600` | Interval between imports, in seconds. |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Character buffer at the end of the file to avoid importing incomplete lines; must be positive. |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Interval between maintenance runs, in days. |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Maintenance removes inactive actors and related data after this period. |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximum gap between requests in the same burst. |
| `BURST_MIN_REQUESTS` | Default `5` | Minimum number of requests for a burst. |
| `BURST_WINDOW_SECONDS` | Default `60` | Burst detection time window. |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Container path to the optional City database. |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Container path to the optional ASN database. |
| `IGNORE_REQUEST_ROUTES` | empty | Semicolon-separated `host/path-prefix` entries to skip during import. Host must match Traefik's `RequestHost`. |
| `KNOWN_HOSTS` | empty | Semicolon-separated host names belonging to this installation; each entry also matches all subdomains and is shown/filterable as an own host. |
| `INM2_ADMIN_PASSWORD_HASH` | required | scrypt hash for the single administrator password, generated inside the API container with the command above. Do not store the plaintext password in `.env`. |
| `INM2_AUTH_SECRET` | required | Private session signing secret, at least 32 bytes; generate with `openssl rand -hex 32`. |
| `INM2_COOKIE_SECURE` | `true` | Sends the session cookie only over HTTPS. Set to `false` only for local HTTP development. |
| `INM2_TOTP_ENABLED` | `false` | Requires a six-digit TOTP code in addition to the password when set to `true`. |
| `INM2_TOTP_SECRET` | required when TOTP is enabled | Secret Base32 key for the authenticator app; generate with `python -m api.totp_secret` and keep it protected. |

### GeoLite2 databases (optional)

Place properly obtained files under `databases/geoip/`:

- `databases/geoip/GeoLite2-City.mmdb`
- `databases/geoip/GeoLite2-ASN.mmdb`

Compose mounts this directory read-only at `/geoip`. If a database is missing, imports continue and the corresponding geolocation/ASN fields remain empty. These files are not included in the repository.

### Ports and data

| Service | Host port | Container port | Purpose |
| --- | --- | --- | --- |
| UI | `3000` | `80` | Web interface |
| API | `8000` | `8000` | REST API and FastAPI documentation |
| Collector | not published | `8001` | Internal control service on the Compose network |

Compose mounts `./databases` at `/app/databases` for both API and collector, `./logs` at `/logs` for the collector, and `./databases/geoip` read-only at `/geoip`. The SQLite file is created at `databases/inm2.sqlite3`. Back up `databases/` regularly; the access log under `logs/` is a mutable import working file, not an archive.

## Using the application

The UI provides Dashboard, Bursts, Actors, Hosts, Categories, Requests, and administration features. Access requires the configured single administrator password; sessions expire after 12 hours. Language (German/English), theme, and time range are stored in the shared SQLite database. Settings and data are shared across the installation.

API routes are under `/api/v1`. After signing in, check the status with:

```sh
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

See [docs/API.en.md](docs/API.en.md) for further API documentation and examples. Scheduled maintenance removes inactive actors and dependent data according to `MAINTENANCE_INACTIVE_DAYS`.

## Updating

Back up at least `databases/` and `.env` before updating. In the cloned repository, fetch the desired change and rebuild the images:

```sh
git pull
docker compose up -d --build
```

The Compose setup uses no external database service or versioned image tags; images are built from the current working tree. Check the UI and status endpoint after the update.

## Stopping and troubleshooting

```sh
docker compose ps
docker compose logs --tail=100
docker compose logs --tail=100 collector
docker compose logs --tail=100 api
docker compose logs --tail=100 ui
docker compose down
```

`docker compose down` removes containers and the network; mounted data directories remain. Do not use `docker compose down -v` as a normal stop command.

- **UI unavailable:** Check whether host port `3000` is in use and whether the UI container is running.
- **API unavailable:** Check host port `8000` and `docker compose logs api`.
- **No requests:** Check `LOG_FILES`, the container path, and read/write access to the log file. It must contain Traefik JSON lines. The collector skips private, loopback, link-local, reserved, and invalid client IP addresses.
- **Geolocation/ASN fields are empty:** Check the filenames and mount under `databases/geoip`; imports work without the optional databases.
- **Check collector status:** Open `/api/v1/status` and inspect collector and database status.

## Local UI development

Node.js/npm are required for the UI. The Vite development server proxies `/api` to `http://localhost:8000`. Start the API first, for example with Compose, then run in `ui/`:

```sh
npm install
npm run dev
```

## License

INM2 is licensed under the [MIT License](LICENSE). MaxMind GeoLite2 files are not part of this repository and are subject to MaxMind's terms of use.
