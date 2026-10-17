# Internet Noise Monitor (INM2)

[English version](README.en.md)

Änderungshistorie: [Deutsch](CHANGELOG.de.md) · [English](CHANGELOG.en.md)

Aktuelle Projektversion: [`VERSION`](VERSION).

INM2 verarbeitet Traefik-Access-Logs und zeigt Requests, Akteure, Hosts, Kategorien, erkannte Bursts und Pfad-Scan-Vorfälle in einem Web-Dashboard. Die Anwendung besteht aus einer React-Oberfläche, einer FastAPI-API und einem Collector. Beide Backend-Dienste lesen und schreiben dieselbe SQLite-Datenbank.

## Voraussetzungen

- Docker Engine mit Docker Compose v2 (`docker compose`)
- Zugriff auf Traefik-Access-Logs im JSON-Zeilenformat
- Für die optionale IP-Geolokalisierung: lokal bereitgestellte MaxMind GeoLite2 City- und/oder ASN-Datenbanken samt Nutzungsberechtigung

Das Compose-Projekt baut alle drei Images lokal. Es veröffentlicht die UI an Host-Port `3000`. Der API-Port `8000` ist nur auf dem Server selbst erreichbar; die UI leitet `/api` intern an die API weiter. Der interne Steuerport des Collectors (`8001`) wird nicht auf dem Host veröffentlicht. Die API verlangt ein eigenes Admin-Passwort und eine signierte Sitzung.

## Installation und erster Start

```sh
git clone <REPOSITORY-URL>
cd <REPOSITORY-ORDNER>
./scripts/setup-linux.sh
```

Das interaktive Linux-Setup prüft Docker Engine mit Compose v2, den Docker-Dienst, Projektdateien und Schreibrechte. Es führt durch Pflichtangaben, Ports, Zugangssicherheit, Erkennung, Import und Wartung. Für die Logquelle prüft es, ob der Pfad auf eine Datei verweist und ob sie leer ist. Die Zugriffsrechte des Collectors und das JSON-Format zeigen sich beim Import. Das Setup prüft, ob der UI-Port belegt ist, und schlägt bei Konflikt einen freien Port vor. OpenSSL wird zum Erzeugen des Sitzungsschlüssels benötigt. Vorhandene `.env`-Dateien werden vor Änderungen gesichert; andere Einträge bleiben erhalten. Das Admin-Passwort kann im Setup geändert werden. Ein eigener Menüpunkt listet `.env.backup.*`-Dateien zur bestätigten Löschung auf.

Das Setup prüft die Logquelle und den UI-Port. Der Port wird lokal auf Belegung geprüft; bei Konflikt schlägt das Setup eine Alternative vor. Es startet die Anwendung nicht automatisch. Nach der Konfiguration erfolgt der Start mit `docker compose up -d --build`.

### Beispiel: Traefik mit Docker-Provider

Bei Verwendung des Traefik-Docker-Providers können Routerlabels für die UI über eine `docker-compose.override.yml` im INM2-Verzeichnis ergänzt werden. Domain, Docker-Netzwerk, Zertifikatsresolver und gegebenenfalls Middleware sind an die vorhandene Traefik-Installation anzupassen:

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
      # Optional, falls Traefik-Middleware eingesetzt wird:
      # - traefik.http.routers.inm2.middlewares=auth-chain@file

networks:
  traefik-proxy:
    external: true
    name: traefik-proxy
```

`traefik-proxy` muss ein bereits vorhandenes Docker-Netzwerk sein, mit dem auch der Traefik-Container verbunden ist. Das Beispiel setzt voraus, dass der Docker-Provider aktiv ist und `websecure` sowie der Zertifikatsresolver `letsencrypt` in Traefik existieren. Middleware ist optional. Die UI lauscht im Container auf Port `80`; `INM2_UI_PORT` ist der zusätzlich veröffentlichte Host-Port und muss für dieses Docker-Netzwerk-Beispiel nicht als Traefik-Ziel verwendet werden. Bei einer dateibasierten Traefik-Konfiguration oder einem anderen Netzwerkmodell ist stattdessen das dort übliche Service-Ziel einzutragen.

Das Setup fragt den vollständigen Hostpfad zu einer Eingabe-Logdatei ab, zum Beispiel `/var/log/my-service/access.log`. Es bindet deren Ordner schreibgeschützt im Collector ein. `LOG_FILES` enthält danach nur den Dateinamen; rotierte Dateien wie `access.log.1` und `access.log.2.gz` werden automatisch mitgelesen. Der Hostordner kann später über `INPUT_LOG_DIR` in `.env` angepasst werden.

```dotenv
INPUT_LOG_DIR=/var/log/my-service
LOG_FILES=access.log
```

Das Admin-Passwort gehört nicht im Klartext in `.env`. Der scrypt-Hash lässt sich verdeckt mit folgendem Befehl erzeugen:

```sh
docker compose run --rm --no-deps --entrypoint python api -m api.password_hash
```

Das Programm fragt das Passwort zweimal ohne Anzeige ab. Trage die ausgegebene Hash-Zeile und einen separaten Sitzungsschlüssel in `.env` ein:

```dotenv
INM2_ADMIN_PASSWORD_HASH='<Hash-Ausgabe>'
INM2_AUTH_SECRET=<ausgabe-von-openssl-rand-hex-32>
INM2_COOKIE_SECURE=true
INM2_TOTP_ENABLED=true
INM2_TOTP_SECRET=<Base32-Schlüssel>
```

Der Sitzungsschlüssel wird mit `openssl rand -hex 32` erzeugt. Die Datei `.env` ist geschützt aufzubewahren. `INM2_COOKIE_SECURE=true` muss bei HTTPS aktiviert bleiben; nur für lokale HTTP-Entwicklung kann der Wert auf `false` gesetzt werden. Beim Start ohne gültigen Hash oder Sitzungsschlüssel verweigert die API den Start. Für einen Passwortwechsel ist ein neuer Hash zu erzeugen und der API-Dienst neu zu starten. Ein Wechsel des Sitzungsschlüssels meldet alle bestehenden Sitzungen ab. Der Hash wird mit scrypt abgeleitet; erforderlich ist ein langes, einzigartiges Passwort.

Für den zweiten Faktor wird ein Schlüssel mit `docker compose run --rm --no-deps --entrypoint python api -m api.totp_secret` erzeugt. Die ausgegebene `INM2_TOTP_SECRET`-Zeile ist in `.env` zu übernehmen. Die Authenticator-App wird mit dem angezeigten Einrichtungsschlüssel oder der URI konfiguriert. `INM2_TOTP_ENABLED=true` verlangt den Code; `false` lässt die Anmeldung passwortbasiert. Ist TOTP aktiviert, verweigert die API den Start ohne gültigen Schlüssel. Die Gerätezeit muss synchronisiert sein. Codes gelten 30 Sekunden und sind während der Laufzeit der API nur einmal verwendbar.

Passwörter mit `$` sind in `.env` in einfache Anführungszeichen zu setzen, damit Compose sie nicht als Variablenreferenz interpretiert.

Der Collector liest die Access-Logdatei und ihre rotierten Segmente schreibgeschützt. Er verändert oder löscht die Quelldateien nicht; Importpositionen speichert er in der SQLite-Datenbank.

Datenverzeichnisse anlegen und Anwendung starten:

```sh
mkdir -p logs databases/geoip
docker compose up -d --build
```

Für lokalen HTTP-Zugriff ist `INM2_COOKIE_SECURE=false` zu setzen; bei HTTPS bleibt der Wert `true`. Die Weboberfläche ist unter `http://localhost:<INM2_UI_PORT>` (Standard `3000`) erreichbar. Die Anmeldung erfolgt mit dem Admin-Passwort. Die Weboberfläche leitet API-Aufrufe intern weiter. Der API-Port (Standard `8000`) ist für lokale Verwaltungszugriffe und Reverse-Proxys auf demselben Server an `127.0.0.1` gebunden. Beim Start werden fällige Collector-Jobs unmittelbar ausgeführt. Der Import verarbeitet nur vollständige JSON-Zeilen im konfigurierten Traefik-Format.

## Konfiguration

Compose lädt Collector- und Authentifizierungseinstellungen aus `.env`. Zusätzlich liest Compose daraus die Hostverzeichnisse für Traefik- und GeoLite-Dateien. Die Datei `.env.example` enthält empfohlene Startwerte. Leere oder nicht gesetzte Collector-Werte greifen auf die in `common/env.py` definierten Standardwerte zurück; Authentifizierungswerte sind erforderlich.

| Variable | Beispielwert / Standard | Bedeutung |
| --- | --- | --- |
| `INPUT_LOG_DIR` | `./logs` | Hostverzeichnis der Traefik-Access-Logs; wird schreibgeschützt unter `/input-logs` eingebunden. |
| `LOG_FILES` | Beispiel `access.log`; Code-Standard leer | Eine oder mehrere Dateinamen in `INPUT_LOG_DIR`, getrennt durch Semikolon. Der Collector liest Traefik-JSON-Zeilen und passende rotierte Dateien. |
| `GEOLITE_DB_DIR` | `./databases/geoip` | Compose-Hostverzeichnis der GeoLite2-Dateien; wird schreibgeschützt unter `/geoip` eingebunden. |
| `INM2_UI_PORT` | `3000` | Host-Port der Weboberfläche; bei belegtem Port anpassen. |
| `INM2_API_PORT` | `8000` | Lokaler Host-Port der API, nur an `127.0.0.1` gebunden; bei belegtem Port anpassen. |
| `INM2_COLLECTOR_PORT` | `8001` | Interner Steuerport im Compose-Netzwerk; nicht auf dem Host veröffentlicht. Nur bei einem Portkonflikt im Container ändern. |
| `INPUT_INTERVAL_SECONDS` | Beispiel `60`; Standard `3600` | Intervall zwischen Importläufen in Sekunden. |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Zeichenpuffer am Dateiende, damit unvollständige Zeilen nicht importiert werden; muss positiv sein. |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Intervall für Wartungsläufe in Tagen. |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Inaktive Akteure und zugehörige Daten werden nach diesem Zeitraum bei der Wartung bereinigt. |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximaler Abstand zwischen Requests im selben Burst. |
| `BURST_MIN_REQUESTS` | Standard `5` | Mindestzahl Requests für einen Burst. |
| `BURST_WINDOW_SECONDS` | Standard `60` | Zeitfenster der Burst-Erkennung. |
| `INCIDENT_MERGE_OVERLAP_PERCENT` | Standard `80` | Führt Kriterien desselben Akteurs zu einem Vorfall zusammen, wenn mehr als dieser Prozentanteil des kürzeren Vorfallszeitraums überlappt (0–100). |
| `LOW_SLOW_SCAN_WINDOW_SECONDS` | `10800` | Rollierendes Zeitfenster für langsame hostübergreifende Pfadscans (3 Stunden). |
| `LOW_SLOW_SCAN_MIN_PATHS` | `12` | Erforderliche unterschiedliche sensible oder fehlerhafte Pfade. Daraus ergibt sich bereits die Mindestzahl an Requests. |
| `LOW_SLOW_SCAN_MIN_HOSTS` | `2` | Erforderliche verschiedene Hosts. |
| `LOW_SLOW_SCAN_MIN_SPAN_SECONDS` | `300` | Mindestdauer zwischen erstem und letztem passenden Request (5 Minuten). |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Containerpfad zur optionalen City-Datenbank. |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Containerpfad zur optionalen ASN-Datenbank. |
| `IGNORE_REQUEST_ROUTES` | leer | Semikolongetrennte `host/pfadpräfix`-Einträge, die beim Import übersprungen werden. Host muss Traefiks `RequestHost` entsprechen. |
| `KNOWN_HOSTS` | leer | Semikolongetrennte eigene Hostnamen; jeder Eintrag gilt auch für alle Subdomains und wird auf der Host-Seite markiert und filterbar. |
| `INM2_ADMIN_PASSWORD_HASH` | erforderlich | scrypt-Hash des Einzel-Admin-Passworts; erzeugt im API-Container mit dem oben gezeigten Befehl. Das Klartextpasswort gehört nicht in `.env`. |
| `INM2_AUTH_SECRET` | erforderlich | Geheimer Sitzungsschlüssel mit mindestens 32 Bytes; Erzeugung mit `openssl rand -hex 32`. |
| `INM2_COOKIE_SECURE` | `true` | Beschränkt das Sitzungs-Cookie auf HTTPS. Für lokale HTTP-Entwicklung ist `false` vorgesehen. |
| `INM2_TOTP_ENABLED` | `false` | Verlangt zusätzlich zum Passwort einen sechsstelligen TOTP-Code, wenn auf `true` gesetzt. |
| `INM2_TOTP_SECRET` | erforderlich, wenn TOTP aktiviert ist | Geheimer Base32-Schlüssel für die Authenticator-App; Erzeugung mit `python -m api.totp_secret`, sichere Aufbewahrung erforderlich. |

### GeoLite2-Datenbanken (optional)

Berechtigungsgemäß bezogene Dateien gehören in das durch `GEOLITE_DB_DIR` angegebene Hostverzeichnis (Standard `databases/geoip/`):

- `databases/geoip/GeoLite2-City.mmdb`
- `databases/geoip/GeoLite2-ASN.mmdb`

Compose bindet diesen Ordner schreibgeschützt nach `/geoip` ein. Fehlt eine Datenbank, läuft der Import weiter; die betreffenden Geo-/ASN-Felder bleiben leer. Das Repository enthält diese Dateien nicht.

### Ports und Daten

| Dienst | Host-Port | Container-Port | Zweck |
| --- | --- | --- | --- |
| UI | `3000` | `80` | Weboberfläche |
| API | nur `127.0.0.1:8000` | `8000` | REST-API und FastAPI-Dokumentation; die UI nutzt das Compose-Netzwerk |
| Collector | nicht veröffentlicht | `INM2_COLLECTOR_PORT` (Standard `8001`) | Interner Steuerdienst im Compose-Netzwerk |

Compose bindet `./databases` für API und Collector nach `/app/databases` und `./logs` für Betriebsprotokolle nach `/logs`. Die durch `INPUT_LOG_DIR` und `GEOLITE_DB_DIR` angegebenen Hostverzeichnisse werden schreibgeschützt unter `/input-logs` beziehungsweise `/geoip` eingebunden. Die SQLite-Datei wird unter `databases/inm2.sqlite3` angelegt. Regelmäßige Sicherungen von `databases/` werden empfohlen.

## Anwendung

Die Oberfläche bietet Dashboard, Statistiken, Bursts, Akteure, Hosts, Kategorien, Requests und Verwaltungsfunktionen. Der Zugriff erfordert das konfigurierte Einzel-Admin-Passwort; die Sitzung läuft nach 12 Stunden ab. Sprache (Deutsch/Englisch), Theme und Zeitraum werden in der gemeinsam genutzten SQLite-Datenbank gespeichert. Einstellungen und Daten sind installationsweit gemeinsam.

Die API-Routen liegen unter `/api/v1`. Nach der Anmeldung kann der Status abgerufen werden mit:

```sh
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

Weitere API-Beschreibung und Beispiele stehen in [docs/API.de.md](docs/API.de.md). Die geplante Wartung entfernt inaktive Akteure und abhängige Daten gemäß `MAINTENANCE_INACTIVE_DAYS`.

## Aktualisieren

Vor dem Update werden Sicherungen von `databases/` und `.env` empfohlen. Die gewünschte Änderung wird im geklonten Repository übernommen; anschließend werden die Images neu gebaut:

```sh
git pull
docker compose up -d --build
```

Das Compose-Setup verwendet keine externen Datenbankdienste oder versionierten Image-Tags; die Images werden aus dem aktuellen Arbeitsbaum erstellt. Nach dem Update sollten UI und Status-Endpunkt geprüft werden.

## Stoppen und Fehlerbehebung

```sh
docker compose ps
docker compose logs --tail=100
docker compose logs --tail=100 collector
docker compose logs --tail=100 api
docker compose logs --tail=100 ui
docker compose down
```

`docker compose down` entfernt Container und Netzwerk; die eingebundenen Datenverzeichnisse bleiben bestehen. `docker compose down -v` ist nicht für das reguläre Stoppen vorgesehen.

- **UI nicht erreichbar:** Belegung von Host-Port `3000` und Status des UI-Containers prüfen.
- **API nicht erreichbar:** Ausgabe von `docker compose logs api` prüfen. Vom Server aus ist die API unter `127.0.0.1:8000` erreichbar; über die Weboberfläche laufen Aufrufe intern.
- **Keine Requests:** `INPUT_LOG_DIR`, die Dateinamen in `LOG_FILES` und die Leserechte auf der Hostdatei prüfen. Die Datei muss Traefik-JSON-Zeilen enthalten. Der Collector überspringt private, Loopback-, Link-Local-, reservierte und ungültige Client-IP-Adressen.
- **Geo-/ASN-Felder leer:** `GEOLITE_DB_DIR` und die Dateinamen `GeoLite2-City.mmdb` und `GeoLite2-ASN.mmdb` prüfen; der Import läuft auch ohne die optionalen Datenbanken.
- **Collector-Status:** `/api/v1/status` sowie Collector- und Datenbankstatus prüfen.

## Lokale UI-Entwicklung

Für die Oberfläche werden Node.js/npm benötigt. Der Vite-Entwicklungsserver leitet `/api` an `http://localhost:8000` weiter. Zunächst ist die API zu starten, zum Beispiel über Compose. Anschließend in `ui/`:

```sh
npm install
npm run dev
```

## Lizenz

INM2 steht unter der [MIT-Lizenz](LICENSE). Die MaxMind-GeoLite2-Dateien sind nicht Teil dieses Repositories und unterliegen den Nutzungsbedingungen von MaxMind.
