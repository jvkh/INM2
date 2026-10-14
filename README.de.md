# Internet Noise Monitor (INM2)

[English version](README.en.md)

Änderungshistorie: [Deutsch](CHANGELOG.de.md) · [English](CHANGELOG.en.md)

Aktuelle Projektversion: [`VERSION`](VERSION).

INM2 verarbeitet Traefik-Access-Logs und zeigt Requests, Akteure, Hosts, Kategorien und erkannte Bursts in einem Web-Dashboard. Die Anwendung besteht aus einer React-Oberfläche, einer FastAPI-API und einem Collector. Beide Backend-Dienste lesen und schreiben dieselbe SQLite-Datenbank.

## Voraussetzungen

- Docker Engine mit Docker Compose v2 (`docker compose`)
- Zugriff auf Traefik-Access-Logs im JSON-Zeilenformat
- Für die optionale IP-Geolokalisierung: lokal bereitgestellte MaxMind GeoLite2 City- und/oder ASN-Datenbanken samt Nutzungsberechtigung

Das Compose-Projekt baut alle drei Images lokal. Es veröffentlicht die UI an Host-Port `3000` und die API an Host-Port `8000`. Der interne Steuerport des Collectors (`8001`) wird nicht auf dem Host veröffentlicht. Es sind keine Benutzerkonten oder Zugangsschutz konfiguriert; betreibe die veröffentlichten Ports daher nur in einem entsprechend geschützten Netzwerk.

## Installation und erster Start

```sh
git clone <REPOSITORY-URL>
cd <REPOSITORY-ORDNER>
cp .env.example .env
```

Bearbeite `.env` und setze `LOG_FILES` auf den Pfad zur Traefik-Access-Logdatei **im Collector-Container**. Das Projektverzeichnis `./logs` wird als `/logs` eingebunden. Beispiel für eine Datei unter `./logs/access.log`:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Die Logdatei muss für den Collector lesbar und beschreibbar sein: Erfolgreich importierte Zeilen werden aus dem Dateipräfix entfernt. Richte bei Bedarf eine separate Archivierung außerhalb dieser Arbeitsdatei ein.

Lege die Datenverzeichnisse an und starte die Anwendung:

```sh
mkdir -p logs databases/geoip
docker compose up -d --build
```

Öffne anschließend [http://localhost:3000](http://localhost:3000). Die API ist unter [http://localhost:8000](http://localhost:8000) erreichbar; ihre interaktive Dokumentation steht unter [http://localhost:8000/docs](http://localhost:8000/docs). Beim Start werden fällige Collector-Jobs unmittelbar ausgeführt. Der Import verarbeitet nur vollständige JSON-Zeilen im konfigurierten Traefik-Format.

## Konfiguration

Compose lädt die Collector-Einstellungen aus `.env`. Die Datei `.env.example` enthält die empfohlenen Startwerte dieses Repositorys. Leere oder nicht gesetzte Werte greifen auf die in `common/env.py` definierten Standardwerte zurück; diese können von den Beispielwerten abweichen.

| Variable | Beispielwert / Standard | Bedeutung |
| --- | --- | --- |
| `LOG_FILES` | Beispiel: `traefik:/logs/access.log`; Code-Standard leer | Eine oder mehrere Eingaben im Format `typ:pfad`, getrennt durch Semikolon. Der Collector liest Traefik-JSON-Zeilen. |
| `INPUT_INTERVAL_SECONDS` | Beispiel `60`; Standard `3600` | Intervall zwischen Importläufen in Sekunden. |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Zeichenpuffer am Dateiende, damit unvollständige Zeilen nicht importiert werden; muss positiv sein. |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Intervall für Wartungsläufe in Tagen. |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Inaktive Akteure und zugehörige Daten werden nach diesem Zeitraum bei der Wartung bereinigt. |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximaler Abstand zwischen Requests im selben Burst. |
| `BURST_MIN_REQUESTS` | Standard `5` | Mindestzahl Requests für einen Burst. |
| `BURST_WINDOW_SECONDS` | Standard `60` | Zeitfenster der Burst-Erkennung. |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Containerpfad zur optionalen City-Datenbank. |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Containerpfad zur optionalen ASN-Datenbank. |
| `IGNORE_REQUEST_ROUTES` | leer | Semikolongetrennte `host/pfadpräfix`-Einträge, die beim Import übersprungen werden. Host muss Traefiks `RequestHost` entsprechen. |
| `KNOWN_HOSTS` | leer | Semikolongetrennte eigene Hostnamen; jeder Eintrag gilt auch für alle Subdomains und wird auf der Host-Seite markiert und filterbar. |

### GeoLite2-Datenbanken (optional)

Lege berechtigungsgemäß bezogene Dateien unter `databases/geoip/` ab:

- `databases/geoip/GeoLite2-City.mmdb`
- `databases/geoip/GeoLite2-ASN.mmdb`

Compose bindet diesen Ordner schreibgeschützt nach `/geoip` ein. Fehlt eine Datenbank, läuft der Import weiter; die betreffenden Geo-/ASN-Felder bleiben leer. Das Repository enthält diese Dateien nicht.

### Ports und Daten

| Dienst | Host-Port | Container-Port | Zweck |
| --- | --- | --- | --- |
| UI | `3000` | `80` | Weboberfläche |
| API | `8000` | `8000` | REST-API und FastAPI-Dokumentation |
| Collector | nicht veröffentlicht | `8001` | Interner Steuerdienst im Compose-Netzwerk |

Compose bindet `./databases` für API und Collector nach `/app/databases`, `./logs` für den Collector nach `/logs` und `./databases/geoip` schreibgeschützt nach `/geoip`. Die SQLite-Datei wird unter `databases/inm2.sqlite3` angelegt. Sichern Sie `databases/` regelmäßig; die Access-Logdatei unter `logs/` ist eine veränderliche Import-Arbeitsdatei und kein Archiv.

## Anwendung

Die Oberfläche bietet Dashboard, Bursts, Akteure, Hosts, Kategorien, Requests und Verwaltungsfunktionen. Sprache (Deutsch/Englisch), Theme und Zeitraum werden in der gemeinsam genutzten SQLite-Datenbank gespeichert. Es gibt keine Benutzerkonten; Einstellungen und Daten sind installationsweit gemeinsam.

Die API-Routen liegen unter `/api/v1`. Der Status kann abgerufen werden mit:

```sh
curl http://localhost:8000/api/v1/status
```

Weitere API-Beschreibung und Beispiele stehen in [docs/API.de.md](docs/API.de.md). Die geplante Wartung entfernt inaktive Akteure und abhängige Daten gemäß `MAINTENANCE_INACTIVE_DAYS`.

## Aktualisieren

Sichere vor dem Update mindestens `databases/` und `.env`. Hole im geklonten Repository die gewünschte Änderung und baue die Images neu:

```sh
git pull
docker compose up -d --build
```

Das Compose-Setup verwendet keine externen Datenbankdienste oder versionierten Image-Tags; die Images werden aus dem aktuellen Arbeitsbaum erstellt. Prüfe nach dem Update UI und Status-Endpunkt.

## Stoppen und Fehlerbehebung

```sh
docker compose ps
docker compose logs --tail=100
docker compose logs --tail=100 collector
docker compose logs --tail=100 api
docker compose logs --tail=100 ui
docker compose down
```

`docker compose down` entfernt Container und Netzwerk, die eingebundenen Datenverzeichnisse bleiben bestehen. Verwende `docker compose down -v` nicht als normale Stoppmaßnahme.

- **UI nicht erreichbar:** Prüfe, ob Host-Port `3000` belegt ist und ob der UI-Container läuft.
- **API nicht erreichbar:** Prüfe Host-Port `8000` und `docker compose logs api`.
- **Keine Requests:** Prüfe `LOG_FILES`, den Containerpfad und Lese-/Schreibrechte auf der Logdatei. Sie muss Traefik-JSON-Zeilen enthalten. Der Collector überspringt private, Loopback-, Link-Local-, reservierte und ungültige Client-IP-Adressen.
- **Geo-/ASN-Felder leer:** Prüfe Dateinamen und Mount unter `databases/geoip`; der Import läuft auch ohne die optionalen Datenbanken.
- **Collector-Status prüfen:** Rufe `/api/v1/status` auf und prüfe Collector- sowie Datenbankstatus.

## Lokale UI-Entwicklung

Für die Oberfläche werden Node.js/npm benötigt. Der Vite-Entwicklungsserver leitet `/api` an `http://localhost:8000` weiter. Starte zunächst die API, zum Beispiel über Compose, und führe dann in `ui/` aus:

```sh
npm install
npm run dev
```

## Lizenz

INM2 steht unter der [MIT-Lizenz](LICENSE). Die MaxMind-GeoLite2-Dateien sind nicht Teil dieses Repositories und unterliegen den Nutzungsbedingungen von MaxMind.
