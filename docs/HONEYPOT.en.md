# HTTP honeypot integration

[Deutsche Version](HONEYPOT.de.md)

## Standalone operation

The Python honeypot is a separate subproject under `honeypot/`. INM2 works without it. The regular root `docker-compose.yml` does not start the honeypot.

Configure and start it:

```sh
cd honeypot
cp .env.example .env
# Adjust the hostname, Traefik network, entrypoints, and certificate resolver
docker compose up -d --build
```

The external Docker network must already exist and be connected to Traefik. HTTP redirects to HTTPS, which Traefik terminates. The honeypot publishes no host port. Stop it with:

```sh
docker compose down
```

The setup script's main menu includes “Configure honeypot” and writes `honeypot/.env`. It can enable or disable the honeypot (`HONEYPOT_ENABLED`). When disabled, INM2 hides the Honeypot menu entry, statistics, and status notice. When enabled but stopped, a warning appears on the dashboard and under System.

## Captured data and import

The honeypot writes one JSON line per request to `logs/honeypot.jsonl`. It stores POST bodies, including submitted login fields, up to 10 MiB per request. Bodies up to 64 KiB are embedded in the JSONL event. Larger bodies and uploads are stored as individual files in `logs/honeypot-bodies/`, with a reference in the JSONL event. Bodies over the capture limit are truncated and marked as such. The decoy portal includes a fake file and backup manager that invites uploads of archives, PHP files, configuration files, and scripts. The public `/files/upload` endpoint displays a form and accepts uploads without authentication; both the request and uploaded content are logged. Uploads are stored and logged only as honeypot evidence; they are never opened or executed. Uploaded files appear in the file list with a public website path and an ordinary “Open” link. Requests to uploaded PHP paths are captured and return a simulated portal response; the file contents are never executed.

The collector imports these events into the `honeypot_event` table during its next regular import. It locks the shared log while importing and truncates the queue only after the database commit succeeds. This keeps the queue small and allows an interrupted import to be retried without duplicates. Large body files remain available to the detail view.

The INM2 Honeypot page displays requests and their bodies. It appears only while the honeypot has left a status file after successfully binding its HTTP port. If the service did not start, Dashboard and System show a notice that its separate configuration may be missing or startup may have failed.

## Decoy behavior

The main site imitates SV Eichenwacht, a small football club, with a club office, automatically calculated upcoming training dates, a searchable member register with dues and team details, and a notice board. The member area, webmaster file manager, and terminal are part of the decoy interface.

The terminal imitates common Linux workflows: navigation, file viewing and search, PHP and system information, environment variables, and simple file operations. Basic pipes, command chaining, and redirection use simulated output and a session-only virtual filesystem. It never starts operating-system commands, executes PHP code, or accesses real network services or host files. Inputs are logged as honeypot requests; unsupported commands return ordinary shell-style errors.

The service also imitates common login pages, WordPress, phpMyAdmin, API endpoints, and selected sensitive-file probes. It never connects to a real backend or serves host files. Unknown paths return 404. Responses are static, rule-based imitations and do not establish that an exploit succeeded.
