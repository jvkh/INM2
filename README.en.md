# Internet Noise Monitor (INM2)

[Deutsche Version](README.de.md)

Changelog: [English](CHANGELOG.en.md) · [Deutsch](CHANGELOG.de.md)

Current project version: [`VERSION`](VERSION).

INM2 processes Traefik access logs and displays requests, actors, hosts, categories, and detected bursts in a web dashboard. The application consists of a React UI, a FastAPI API, and a collector. Both backend services read and write the same SQLite database.

## Prerequisites

- Docker Engine with Docker Compose v2 (`docker compose`)
- Access to Traefik access logs in JSON-lines format
- For optional IP geolocation: locally supplied MaxMind GeoLite2 City and/or ASN databases, obtained under the applicable terms

The Compose project builds all three images locally. It publishes the UI on host port `3000` and the API on host port `8000`. The collector's internal control port (`8001`) is not published on the host. No user accounts or access control are configured; expose these ports only on a suitably protected network.

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

The collector must have read and write access to the log file: after a successful import, processed lines are removed from the beginning of the file. Arrange separate archival outside this working file if needed.

Create the data directories and start the application:

```sh
mkdir -p logs databases/geoip
docker compose up -d --build
```

Then open [http://localhost:3000](http://localhost:3000). The API is available at [http://localhost:8000](http://localhost:8000), with interactive documentation at [http://localhost:8000/docs](http://localhost:8000/docs). Due jobs run immediately when the collector starts. Imports process only complete JSON lines in the configured Traefik format.

## Configuration

Compose loads collector settings from `.env`. `.env.example` contains this repository's recommended starting values. Empty or unset values fall back to the defaults defined in `common/env.py`; those may differ from the example values.

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

The UI provides Dashboard, Bursts, Actors, Hosts, Categories, Requests, and administration features. Language (German/English), theme, and time range are stored in the shared SQLite database. There are no user accounts; settings and data are shared across the installation.

API routes are under `/api/v1`. Check the status with:

```sh
curl http://localhost:8000/api/v1/status
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
