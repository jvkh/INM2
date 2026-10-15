# API und Collector verwenden

[English version](API.en.md) · [Installationsanleitung](../README.de.md)

Diese Anleitung richtet sich an Entwickler, die Daten aus dem Internet Noise Monitor abrufen oder einen Import beziehungsweise eine Wartung auslösen möchten.

## Verbindung und interaktive Dokumentation

Alle API-Routen außer `POST /api/v1/auth/login` und `GET /api/v1/auth/session` benötigen eine gültige Admin-Sitzung. Wenn `INM2_TOTP_ENABLED=true` gesetzt ist, muss der Login zusätzlich `totp_code` mit einem aktuellen sechsstelligen Authenticator-Code enthalten. Die Weboberfläche meldet sich an und verwaltet das Sitzungscookie automatisch. Auch `/docs` ist geschützt.

Für Skripte kann das Cookie nach der Anmeldung in einer Cookie-Datei gespeichert werden. Verwende HTTPS und setze beim Login den `Origin`-Header auf dieselbe Adresse:

```sh
curl -c cookies.txt -b cookies.txt \\
  -H 'Origin: https://inm2.example.org' -H 'Content-Type: application/json' \\
  -d '{"password":"DEIN-ADMIN-PASSWORT","totp_code":"123456"}' \\
  https://inm2.example.org/api/v1/auth/login
curl -b cookies.txt https://inm2.example.org/api/v1/status
```

Die Sitzung ist auf 12 Stunden begrenzt. Schreibende `POST`-, `PUT`-, `PATCH`- und `DELETE`-Aufrufe werden zusätzlich nur mit einem passenden `Origin`-Header akzeptiert.

Die folgenden API-Beispiele setzen eine angemeldete Sitzung voraus. Für `curl` ergänze `-b cookies.txt`; bei schreibenden Aufrufen zusätzlich `-H 'Origin: https://inm2.example.org'`. Ersetze die Beispieladresse durch den Host, über den du die API tatsächlich aufrufst.

Beispiel für einen Aufruf:

```sh
curl -b cookies.txt 'https://inm2.example.org/api/v1/status'
```

Die API liefert JSON. `GET`- und `PUT`-Aufrufe verwenden Query-Parameter; `PUT` benötigt keinen JSON-Request-Body.

## Allgemeine Regeln

### Zeiträume

Zeitangaben müssen ISO 8601 entsprechen, zum Beispiel `2026-10-01T00:00:00Z` oder `2026-10-01T02:00:00+02:00`. Zeitangaben ohne Zeitzone werden als UTC interpretiert. Die Parameter `from` und `to` bilden ein halboffenes Intervall: `from` ist eingeschlossen, `to` ausgeschlossen. `from` muss vor `to` liegen.

### Filter und Seitennavigation

Textfilter wie `host`, `country`, `city`, `provider`, `asn`, `ip` und `category` suchen nach einer passenden Teilzeichenfolge. Werden mehrere Filter gesetzt, müssen alle zutreffen (UND-Verknüpfung). IDs, Zeitwerte und Zahlenfilter werden exakt ausgewertet.

Listen mit vielen Ergebnissen verwenden `limit` und `offset`. Wo verfügbar, ist `limit` standardmäßig 100 und höchstens 1000. `offset` beginnt bei 0.

### Einordnung der Requests

- Lesend: `GET`, `HEAD`, `OPTIONS`
- Schreibend: `POST`, `PUT`, `PATCH`, `DELETE`
- Andere: alle übrigen Methoden

Bei HTTP-/HTTPS-Zählungen werden nicht erkannte oder fehlende Schemes separat als `other_scheme_count` gezählt.

## Endpunkte

### Kacheltrends

`GET /api/v1/metric_trends` liefert Kennzahlen für den ausgewählten Zeitraum und den unmittelbar davorliegenden Zeitraum gleicher Länge. Erforderlich sind `from` und `to`; `page` kann `dashboard`, `bursts`, `actors`, `hosts`, `categories` oder `requests` sein. Die Listenansichten akzeptieren ihre jeweiligen aktiven Filter, damit die Tendenz dieselbe Auswahl berücksichtigt. `metrics` enthält je Kennzahl aktuelle und vorherige Werte, Prozentänderung und Richtung (`up`, `down`, `steady`). Änderungen bis einschließlich 5 % gelten als gleichbleibend. Bei einem leeren Vergleichszeitraum wird `0 %` und `steady` zurückgegeben.

### Status

`GET /api/v1/status` meldet den API-/Datenbankstatus, den gespeicherten Collector-Status und die unterstützten, unkritischen Konfigurationswerte. Die Umgebungsvariablen werden mit ihren wirksamen Werten zurückgegeben; Zugangsdaten oder beliebige Prozessvariablen sind nicht Teil dieser Ausgabe.

```sh
curl -b cookies.txt 'https://inm2.example.org/api/v1/status'
```

Bei erfolgreichem Zugriff enthält die Antwort `status: "ok"`, `database: "ok"`, `collector_status` und `environment`. `collector_status.import_file` enthält die gerade verarbeitete Datei; `collector_status.last_import_file` behält den zuletzt begonnenen Dateinamen auch nach Abschluss des Imports bei. Kann die Statusabfrage die Datenbank oder die Einstellungen nicht lesen, liefert sie weiterhin HTTP 200 mit `status: "degraded"`, `database: "unavailable"` und einem nicht verfügbaren Collector-Status.

### Protokolle

`GET /api/v1/logs?service=collector` liest die letzten Protokolleinträge. `service` ist `collector`, `api`, `ui_access` oder `ui_error`; `limit` ist optional (Standard 2000, maximal 10000 Zeilen). Die Ausgabe ist zusätzlich auf 2 MiB begrenzt. `DELETE /api/v1/logs?service=collector` setzt die ausgewählte Protokolldatei zurück. Die Logging-Seite zeigt dieselben Dienste in Registerkarten und aktualisiert die Anzeige automatisch. Der Endpunkt benötigt keine Datenbankverbindung, damit Protokolle auch bei einem Datenbankausfall angezeigt werden können.

### Neue Daten

`GET /api/v1/notifications` liefert Requests und Bursts, deren IDs neuer als die gespeicherten Gesehen-Cursor sind. Die Antwort enthält die Gesamtzahlen, bis zu fünf aktuelle Einträge je Typ sowie die neuesten Cursorwerte. `PUT /api/v1/notifications/seen?request_cursor=…&burst_cursor=…` speichert diese Cursor in der Settings-Tabelle. Beim ersten Abruf werden die aktuellen Höchst-IDs als Ausgangsstand gespeichert, damit bereits vorhandene Datensätze nicht als neu gemeldet werden.

### Requests

`GET /api/v1/requests` liefert paginierte Einzelrequests in einem Pflichtzeitraum. Unterstützte Filter:

| Parameter | Bedeutung |
| --- | --- |
| `from`, `to` | Pflichtzeitraum |
| `host` | Hostname, Teilzeichenfolge |
| `actor`, `ip` | Akteur-IP, Teilzeichenfolge |
| `actor_id` | Akteur-ID, exakt |
| `country`, `city`, `provider`, `asn` | Akteur-Metadaten, Teilzeichenfolge |
| `category` | Request-Kategoriename, Teilzeichenfolge |
| `path` | Request-Pfad, Teilzeichenfolge; mit `path_exact=true` exakt |
| `search` | Teilzeichenfolgensuche in IP, Host, Land, Stadt, Provider, ASN und Request-Pfad |
| `status_class` | HTTP-Statusklasse: `2xx`, `3xx`, `4xx` oder `5xx` |
| `burst_id` | Requests, die dem Burst zugeordnet sind |
| `limit`, `offset` | Seitennavigation |

Bei `search` kann das Feld mit `feld:begriff` eingeschränkt werden, zum Beispiel `host:inm.jvkh.de`, `path:/login` oder `pfad:/login`. Die englischen Feldnamen funktionieren unabhängig von der Sprache der Oberfläche; zusätzlich werden deutsche Namen wie `pfad`, `land`, `stadt`, `anbieter` und `kategorie` erkannt. Auf der Requests-Seite sind außerdem `ip`, `country`, `city`, `provider`, `asn`, `category`, `method`, `status`, `scheme` und `ua` verfügbar. Unbekannte Feldnamen werden als normale Freitextsuche behandelt. Weitere Oberflächensprachen können ihre Bezeichnungen als Suchalias ergänzen.

`GET /api/v1/request_paths` liefert die häufigsten unterschiedlichen Request-Pfade, die einen Suchbegriff enthalten. Erforderlich sind `from`, `to` und `search`; `limit` ist optional (Standard 100, maximal 500). Die globale Suche nutzt diese Treffer und öffnet den Requests-Bildschirm mit einem exakten Pfadfilter.

Zusätzlich steuern `sort_by` und `sort_order` die Sortierung. Unterstützte Spalten: `start_utc`, `request_method`, `request_path`, `user_agent`, `downstream_status`, `actor_ip`, `host`, `duration` und `downstream_content_size`; Richtung: `asc` oder `desc`.

Die Filter `actor` und `host` suchen standardmäßig nach Teilzeichenfolgen. Mit `actor_exact=true`, `host_exact=true` beziehungsweise `category_exact=true` wird exakt verglichen.

```sh
curl -G 'http://localhost:8000/api/v1/requests' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'actor=203.0.113.' \
  --data-urlencode 'limit=50'
```

Die Antwort enthält `items`, `total`, `limit`, `offset`, `from` und `to`. Ein Item enthält unter anderem Request-ID und -Zeit, Akteur und dessen Geo-/Providerdaten, Host, Methode, Pfad, Scheme, Statuscode, Antwortgröße und Dauer.

`GET /api/v1/requests/{id}` liefert einen Request mit Akteur-, Host- und Kategorieinformationen. Eine unbekannte ID ergibt HTTP 404.

```sh
curl 'http://localhost:8000/api/v1/requests/123'
```

### Akteure

`GET /api/v1/actors` liefert Akteure mit mindestens einem Request im gewählten Zeitraum. Mit `new_only=true` werden nur Akteure aufgenommen, deren `first_time` im Zeitraum liegt. Neben `from` und `to` sind `provider`, `country`, `city`, `asn` und `ip` als Teilzeichenfolgenfilter möglich; `country_exact=true` und `ip_exact=true` schalten den jeweiligen Filter auf exakte Übereinstimmung um. `search` sucht zugleich in IP, Stadt, Provider und ASN. `global_search` durchsucht IP, Land, Stadt und ASN. Dazu kommen `limit` und `offset`. `sort_by` unterstützt `ip`, `first_time`, `last_time`, `provider`, `asn`, `city`, `country` und `request_count`; `sort_order` ist `asc` oder `desc`.

`GET /api/v1/countries` liefert die Länder mit Requests im gewählten Zeitraum und befüllt die Länder-Auswahllisten.

```sh
curl -G 'http://localhost:8000/api/v1/actors' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'country=Germany' \
  --data-urlencode 'new_only=true'
```

`GET /api/v1/actors/{id}` liefert das Akteursprofil einschließlich der Requests- und Burst-Gesamtzahlen über die gesamte gespeicherte Historie. `DELETE /api/v1/actors/{id}` löscht einen Akteur sowie seine Requests und Bursts per Fremdschlüssel-Kaskade. Die Antwort enthält die IP und die Anzahl der gelöschten Requests und Bursts; die Aktion wird im API-Log protokolliert.

### Bursts

`GET /api/v1/bursts` fasst Bursts zusammen, deren Startzeit im Zeitraum liegt. Filter: `actor` (IP-Teilzeichenfolge), `actor_id` (exakt), `host`, `country`, `provider`, `asn` und `city` (jeweils Teilzeichenfolge), `search` (Teilzeichenfolge in Burst-ID, IP, Provider, ASN oder Stadt), `limit` und `offset`. Mit `host_exact=true` beziehungsweise `country_exact=true` werden Host- und Länderfilter exakt ausgewertet. Mit `sort_by` (`burst_id`, `start_time`, `actor_ip`, `host`, `country`, `duration`, `requests` oder `avg_count`) und `sort_order` (`asc` oder `desc`) lässt sich die Sortierung festlegen. Die Antwort enthält `summary` sowie die paginierte Liste `items`. Die Zusammenfassung enthält Gesamtzahlen für Bursts, Akteure und Requests, Methodenzählungen sowie Durchschnitts-, Median- und Höchstwerte für Requests, Burst-Dauer und Bursts je Akteur.

```sh
curl -G 'http://localhost:8000/api/v1/bursts' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'country=Germany'
```

`GET /api/v1/bursts/{id}` liefert die Burstinformationen. `GET /api/v1/burst_requests/{id}` liefert zusätzlich die zugeordneten Requests und deren Anzahl (`total`).

`GET /api/v1/hosts` akzeptiert `host` als Teilzeichenfolgenfilter sowie `known=own|foreign`, um auf konfigurierte eigene bzw. fremde Hosts einzuschränken. Die Antwort enthält außerdem `known` je Host und `known_count` für die konfigurierte Anzahl. `sort_by` unterstützt `host`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count` und `https_share`; `sort_order` nimmt `asc` oder `desc` an. `GET /api/v1/categories` akzeptiert `category` als Teilzeichenfolgenfilter; `sort_by` unterstützt `category_name`, `total_count`, `read_count`, `write_count`, `other_count`, `http_count`, `https_count`, `other_scheme_count`, `traffic_share` und `https_share`. `sort_order` nimmt `asc` oder `desc` an.

```sh
curl 'http://localhost:8000/api/v1/burst_requests/42'
```

### Zeitreihe der Requestzahlen

`GET /api/v1/request_counts` liefert gleich breite Zeitintervalle für Diagramme. Pflichtparameter: `from`, `to` und `bars` (1 bis 500). Optionale Filter: `host`, `actor_ip`, `actor_id`, `category`, `path`, `path_exact`, `burst_id`, `search` und `status_class`.

```sh
curl -G 'http://localhost:8000/api/v1/request_counts' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'bars=24' \
  --data-urlencode 'host=example.org' \
  --data-urlencode 'category=CMS'
```

Die Antwort enthält `items` mit `from`, `to`, `read_count`, `write_count`, `other_count` und `total_count` je Zeitintervall sowie die verwendeten Grenzen und die Anzahl der Intervalle. Leere Intervalle werden mit Zählwerten 0 ausgegeben.

### Kategorien und Hosts

`GET /api/v1/categories` zählt Requests je Kategorie. Pflichtparameter: `from`, `to`; optional `category` als Teilzeichenfolge. Neben der Request-Einordnung nach Methode enthält jedes Element `http_count`, `https_count` und `other_scheme_count`.

```sh
curl -G 'http://localhost:8000/api/v1/categories' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'category=CMS'
```

`GET /api/v1/hosts` liefert dieselben Zählarten gruppiert nach Host. `host` ist ein optionaler Teilzeichenfolgefilter.

```sh
curl -G 'http://localhost:8000/api/v1/hosts' \
  --data-urlencode 'from=2026-10-01T00:00:00Z' \
  --data-urlencode 'to=2026-10-02T00:00:00Z' \
  --data-urlencode 'host=example.org'
```

### Parameter lesen und ändern

`GET /api/v1/params` benötigt `group_name`. Mit `name` wird ein einzelner Eintrag abgefragt, ohne `name` die ganze Gruppe.

```sh
curl -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector'

curl -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector' \
  --data-urlencode 'name=last_import'
```

`PUT /api/v1/params` benötigt immer `group_name` und `name`. Ist `value` angegeben, wird der Wert gespeichert oder aktualisiert. Fehlt `value`, wird der Eintrag gelöscht. Ein ausdrücklich leerer Wert lässt sich mit `value=` speichern.

Die UI speichert Sprache, Farbschema und Zeitraum in der Gruppe `ui_preferences`. Das Einzel-Admin-Login schützt den Zugriff; Einstellungen gelten weiterhin installationsweit gemeinsam.

```sh
curl -X PUT -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector' \
  --data-urlencode 'name=example' \
  --data-urlencode 'value=enabled'

curl -X PUT -G 'http://localhost:8000/api/v1/params' \
  --data-urlencode 'group_name=collector' \
  --data-urlencode 'name=example'
```

Das Ändern der Settings-Tabelle setzt keine Docker-Umgebungsvariablen neu. Konfigurationswerte aus `.env` werden beim Start der Container eingelesen; Änderungen an `.env` erfordern daher einen Neustart des betroffenen Dienstes.

### Collector-Import und Wartung auslösen

`PUT /api/v1/import` stößt unabhängig vom eingestellten Zeitintervall einen Import an. `PUT /api/v1/maintenance` stößt unabhängig vom Zeitintervall eine Wartung an. Beide Aufrufe haben keine Parameter und keinen Request-Body.

```sh
curl -X PUT 'http://localhost:8000/api/v1/import'
curl -X PUT 'http://localhost:8000/api/v1/maintenance'
```

Bei Annahme antwortet die API mit HTTP 202 und etwa `{"status":"accepted","activity":"Import"}`. Die Arbeit läuft im Hintergrund; den Fortschritt liest man über `/api/v1/status`.

## Fehlerantworten

| HTTP-Status | Bedeutung |
| --- | --- |
| 404 | Angefragte Request-/Akteurs-/Burst-ID oder Parametergruppe bzw. -eintrag fehlt |
| 422 | Ungültige oder fehlende Parameter, zum Beispiel `from >= to` |
| 409 | Collector ist bereits mit Import oder Wartung beschäftigt (`collector_busy`) |
| 502 | Collector hat die Aktion abgelehnt oder eine ungültige Antwort geliefert (`collector_error`) |
| 503 | Datenbank oder Collector momentan nicht erreichbar |
| 500 | Unerwarteter API-Fehler (`internal_server_error`) |

Fehler der API-Infrastruktur verwenden das Format `{"error":{"code":"…","message":"…"}}`. FastAPI-Validierungs- und 404-Fehler verwenden weiterhin das FastAPI-Format mit `detail`. Der Status-Endpunkt ist eine Ausnahme: Er fängt Fehler ab und liefert seinen Degradationsstatus als HTTP 200.

## Collector und Datenfluss

Der Collector liest die in `LOG_FILES` eingetragenen Dateien, wertet Traefik-Access-Logs im JSON-Zeilenformat aus und schreibt Requests, Akteure, Hosts, Kategorien und Bursts in dieselbe Datenbank, die die API liest. Im Compose-Netz ist sein interner Steuerdienst auf Port 8001 erreichbar. Dieser Port ist nicht auf dem Host veröffentlicht; Nutzer rufen ausschließlich die API auf Port 8000 auf.

Die geplanten Import- und Wartungsläufe teilen sich eine Sperre mit den manuell ausgelösten Läufen. Ist der Collector beschäftigt, wird ein manueller Auftrag mit HTTP 409 abgelehnt, statt parallel gestartet zu werden. Ein akzeptierter Auftrag läuft im Hintergrund. Beim Collector-Start startet der Scheduler seine fälligen Jobs unmittelbar und führt sie danach im konfigurierten Intervall aus.

### Eingabedateien und Aufbewahrung

`LOG_FILES` enthält eine oder mehrere durch Semikolon getrennte Angaben der Form `typ:pfad`, zum Beispiel:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Der Traefik-Reader verarbeitet in der aktiven Datei nur vollständige JSON-Zeilen vor dem durch `INPUT_SAVE_MARGIN_CHARACTERS` definierten Dateiende-Puffer. Der Wert muss größer als 0 sein. Zusätzlich werden passende rotierte Segmente (`access.log.*`, auch `.gz`) automatisch in zeitlicher Reihenfolge gelesen; bei diesen wird bis zum Ende gelesen. Positionen sind an Geräte- und Inode-Identität gebunden und folgen daher umbenannten Segmenten. Ein SHA-256-Fingerabdruck der ersten vollständigen Logzeile (maximal 64 KiB) erkennt eine neue Datei, falls eine Inode-Kennung wiederverwendet wird. Fingerabdruck, Position und Request werden gemeinsam gespeichert. Der Collector verändert und löscht keine Logdateien. Rotation und Aufbewahrung übernimmt logrotate.

### Konfiguration

Die folgenden Variablen werden vom Collector unterstützt und erscheinen mit ihren effektiven Werten auch im Status:

| Variable | Standardwert | Zweck |
| --- | --- | --- |
| `LOG_FILES` | leer | Semikolongetrennte Liste von `typ:pfad`-Eingabedateien |
| `INPUT_INTERVAL_SECONDS` | `3600` | Abstand zwischen Importläufen in Sekunden |
| `INPUT_SAVE_MARGIN_CHARACTERS` | `4096` | Puffer am Dateiende, der beim Einlesen ausgespart wird; muss positiv sein |
| `MAINTENANCE_INTERVAL_DAYS` | `1` | Abstand zwischen Wartungsläufen |
| `MAINTENANCE_INACTIVE_DAYS` | `90` | Inaktivitätszeitraum für die Bereinigung alter Akteure |
| `BURST_MAX_GAP_SECONDS` | `5` | Maximaler Abstand zwischen Requests im selben Burst |
| `BURST_MIN_REQUESTS` | `5` | Mindestzahl Requests für einen Burst |
| `BURST_WINDOW_SECONDS` | `60` | Zeitfenster für die Burst-Erkennung |
| `GEOLITE_CITY_DB` | `/geoip/GeoLite2-City.mmdb` | Pfad zur GeoLite City-Datenbank im Container |
| `GEOLITE_ASN_DB` | `/geoip/GeoLite2-ASN.mmdb` | Pfad zur GeoLite ASN-Datenbank im Container |
| `IGNORE_REQUEST_ROUTES` | leer | Semikolongetrennte Host-/Pfadpräfixe, die beim Import ausgeschlossen werden |
| `KNOWN_HOSTS` | leer | Semikolongetrennte Liste eigener Hostnamen |

Ein Host-/Pfadpräfix wird nur für den angegebenen Host ausgeschlossen. Der Pfad muss exakt passen oder mit einem `/`-Segment beginnen; `assets` schließt also `/assets/app.js`, aber nicht `/assets-old/app.js` aus. Beispiel für `.env`:

```dotenv
IGNORE_REQUEST_ROUTES=inm2.example.de/api;inm2.example.de/assets
```

Im Compose-Setup kommen die Collector-Variablen aus `.env`. Die Verzeichnisse `./logs` und `./databases` werden in den Collector-Container eingebunden; die GeoIP-Dateien unter `./databases/geoip` werden schreibgeschützt eingebunden. Die API teilt sich das Datenbankverzeichnis mit dem Collector.

Die Wartung entfernt Akteure, die länger als `MAINTENANCE_INACTIVE_DAYS` inaktiv sind. Zugehörige Daten werden entsprechend den Datenbankbeziehungen mitbereinigt. API-Nutzer sollten daher nicht davon ausgehen, dass alle einmal importierten Akteure dauerhaft gespeichert bleiben.
