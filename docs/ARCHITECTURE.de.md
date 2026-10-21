# Architektur und Datenfluss

[English version](ARCHITECTURE.en.md) · [Zur Installationsanleitung](../README.de.md)

INM2 besteht aus drei per Docker Compose gestarteten Diensten. Der Collector liest Traefik-Access-Logs, erkennt Bursts und Pfad-Scans, die API stellt gespeicherte Daten bereit, und die React-Oberfläche ruft diese API im Browser auf. Collector und API teilen sich eine SQLite-Datenbank.

## Dienste

| Dienst | Implementierung | Aufgabe | Erreichbarkeit im Compose-Setup |
| --- | --- | --- | --- |
| `ui` | React, TypeScript, Nginx | Dashboard und Bedienoberfläche; Nginx leitet `/api/` an die API weiter. | Host-Port `3000`, Container-Port `80` |
| `api` | FastAPI, Uvicorn | REST-Endpunkte unter `/api/v1`, Datenbankzugriff und Weiterleitung manueller Collector-Aufträge. | Nur `127.0.0.1:8000` am Host; Container-Port `8000` im Compose-Netz |
| `collector` | Python, Uvicorn-Steuerdienst | Importiert Logs, ergänzt optionale Geo-/ASN-Daten, erkennt Bursts und führt Wartung aus. | Steuerport `8001` nur intern im Compose-Netz |

Compose baut die Images aus den Dockerfiles im Repository. Die UI ist auf dem Host erreichbar. Der API-Port ist nur an `127.0.0.1` gebunden; die UI erreicht die API über das interne Compose-Netz. Die API erzwingt eine Anmeldung mit Admin-Passwort.

## Datenfluss

1. Der Collector liest die Dateinamen aus `LOG_FILES` im unter `/input-logs` schreibgeschützt eingebundenen Verzeichnis. Unterstützt werden Traefik-JSON-Objekte pro Zeile. Passende rotierte Dateien werden ebenfalls erfasst. Wenn `COWRIE_ENABLED=true` gesetzt ist, liest er zusätzlich `cowrie.json` inkrementell aus `/cowrie-logs` und speichert SSH-Ereignisse separat. Cowries Login-Ereignisse einschließlich Passwortwerten werden übernommen und in `cowrie_event.password` gespeichert.
2. Vollständige verarbeitbare Zeilen werden in Requests, Akteure, Hosts und Kategorien überführt. Die Bursterkennung verarbeitet neue Requests inkrementell und ergänzt bei passendem Abstand den letzten Burst des vorherigen Imports. Nur bei der einmaligen Übernahme vorhandener Daten sowie bei rückdatierten Requests wird die Historie der betroffenen Akteur-/Host-Kombination neu aufgebaut. Nur global routbare Client-IP-Adressen werden importiert; private, Loopback-, Link-Local-, reservierte und ungültige Adressen werden übersprungen.
3. Bei Bedarf ergänzt der Collector City-/Länder- und ASN-/Providerdaten aus lokalen GeoLite2-MMDB-Dateien. Diese Anreicherung ist optional.
4. Collector und API verwenden dieselbe SQLite-Datei unter `databases/inm2.sqlite3`. Die Datenbank nutzt WAL, damit Lesezugriffe der API während eines Imports weiterlaufen können; kurze Schreibkonflikte werden bis zu 30 Sekunden abgewartet. Die UI greift ausschließlich über HTTP auf die API zu.
5. Geplante und manuell ausgelöste Import- und Wartungsläufe teilen eine Sperre. Manuelle Aufträge laufen im Hintergrund; bei belegtem Collector antwortet die API mit `409`.

## Vorfälle

Alle Erkennungen werden gemeinsam in `incident` gespeichert. `incident_criterion` hält alle erfüllten Erkennungskriterien eines Vorfalls fest; ein Vorfall kann also mehrere Typen abdecken. `incident_request` hält die konkreten Request-Zuordnungen für die Vorfallansicht und die gefilterte Requestliste fest. Nach jedem Import werden Vorfälle desselben Akteurs zusammengeführt, wenn sich mehr als `INCIDENT_MERGE_OVERLAP_PERCENT` Prozent des kürzeren Zeitraums überschneiden (Standard 80). Die Zeitgrenzen des zusammengeführten Vorfalls entsprechen dem Minimum und Maximum seiner zugeordneten Requests. Beim Start migriert der Datenbank-Initializer vorhandene `path_scan_incident`-Zeilen samt Request-Zuordnungen. Beim ersten Import nach dem Upgrade prüft ein einmaliger Backfill außerdem das jeweils letzte Aktivitätsfenster jeder Akteur-/Host-Kombination auf die neuen Regeln.

Die Regeln prüfen pro Quell-IP und Host rollierende 10-Minuten-Fenster: Pfad-Scan (mindestens 8 unterschiedliche sensible Pfade), fehlgeschlagene Logins (mindestens 5 Antworten 401/403 auf Login-/Auth-Pfaden), Fehlerhäufung (mindestens 20 Antworten ab 400), Schreibaktivität (mindestens 5 POST/PUT/PATCH/DELETE-Requests auf Admin-/Auth-/API-Pfaden), Scanner-Aktivität (mindestens 5 Requests mit bekannten Scanner-Signaturen im User-Agent) und Request-Spitzen (mindestens 50 Requests). Drei Requests nach mindestens 30 Tagen ohne Host-Aktivität erzeugen ebenfalls einen Hinweis. Fehlerhäufungen zeigen Fehleranzahl und Anteil der Nicht-Fehlerantworten; Request-Spitzen zeigen durchschnittliche, minimale und maximale Requests pro Sekunde. Ein langsamer, hostübergreifender Pfad-Scan wird standardmäßig über ein rollierendes 3-Stunden-Fenster erkannt, wenn mindestens 12 sensible oder fehlerhafte Pfade auf mindestens 2 Hosts über wenigstens 5 Minuten auftreten. Zeitfenster, Mindestzahl der Pfade und Hosts sowie die Mindestdauer sind über `LOW_SLOW_SCAN_WINDOW_SECONDS`, `LOW_SLOW_SCAN_MIN_PATHS`, `LOW_SLOW_SCAN_MIN_HOSTS` und `LOW_SLOW_SCAN_MIN_SPAN_SECONDS` konfigurierbar; eine separate Mindest-Requestzahl ist nicht nötig, da jeder unterschiedliche Pfad mindestens einen Request voraussetzt. Eine 2xx-Antwort auf eine sensible Datei- oder Exploit-Probe wird einzeln markiert. URL- und User-Agent-Regeln sind Heuristiken; die Antwort belegt nicht, dass Inhalte offengelegt oder Exploits erfolgreich waren. Fehlende Logs und falsch zugeordnete Proxy-IPs beeinflussen die Ergebnisse.

## Importverhalten und Logdateien

`INPUT_SAVE_MARGIN_CHARACTERS` hält bei der aktiven Datei einen Puffer am Dateiende zurück, damit unvollständige Logzeilen nicht verarbeitet werden. Neben der konfigurierten Datei liest der Collector passende rotierte Segmente (`access.log.*`, einschließlich `.gz`) in zeitlicher Reihenfolge. Abgeschlossene Segmente werden bis zum Ende gelesen. Positionen sind an Geräte- und Inode-Identität gebunden und bleiben daher beim Umbenennen durch logrotate erhalten. Zusätzlich speichert der Collector einen SHA-256-Fingerabdruck der ersten vollständigen Logzeile (höchstens 64 KiB). Ändert sich der Fingerabdruck bei gleicher Geräte-/Inode-Kennung, beginnt er die Datei erneut bei Byte 0. Offset, Fingerabdruck und Request werden gemeinsam gespeichert. Der Collector verändert oder löscht keine Logdateien; Rotation und Aufbewahrung übernimmt logrotate.

Compose bindet das durch `INPUT_LOG_DIR` angegebene Hostverzeichnis nach `/input-logs` ein. `LOG_FILES` enthält darin nur den Dateinamen:

```dotenv
INPUT_LOG_DIR=/var/log/my-service
LOG_FILES=access.log
```

Die Betriebsprotokolle liegen ebenfalls in `./logs`, aber in getrennten Dateien pro Dienst: `collector.log`, `api.log`, `ui-access.log` und `ui-error.log`. Eine gemeinsame Datei wird vermieden, weil unabhängige Container gleichzeitig schreiben und Rotation auslösen können. Collector und API rotieren ihre Dateien; Nginx protokolliert UI-Zugriffsfehler und Nginx-Fehler separat. Die Seite **Logging** zeigt sie in Registerkarten, aktualisiert die Anzeige automatisch und kann die ausgewählte Datei zurücksetzen. API und Collector begrenzen die Dateigröße durch Rotation; die Nginx-Dateien können über die Logging-Seite zurückgesetzt werden.

Mehrere Einträge können mit Semikolon getrennt werden. `IGNORE_REQUEST_ROUTES` kann Requests für angegebene Host-/Pfadpräfixe auslassen. `KNOWN_HOSTS` enthält eigene Hostnamen; der Collector synchronisiert sie beim Start in die Tabelle `known_host`. Ein Eintrag wie `jvkh.de` kennzeichnet sowohl `jvkh.de` als auch beliebige Subdomains wie `inm.jvkh.de` als eigene Hosts. `www.example.org` und `example.org` gelten beim Abgleich ebenfalls als derselbe Host. Gespeicherte Hosts und ihre Bursts bleiben getrennt.

Die Bursterkennung trennt Folgen, sobald der Abstand zwischen zwei Requests `BURST_MAX_GAP_SECONDS` überschreitet. Eine Folge gilt als Burst, sobald mindestens `BURST_MIN_REQUESTS` Requests innerhalb von `BURST_WINDOW_SECONDS` liegen; ab dem ersten qualifizierenden Request wird die Folge bis zur nächsten Lücke gezählt. Im laufenden Betrieb werden nur neue Requests und das kurze Zeitfenster zur Qualifizierung betrachtet. Passt ein neuer Request zum letzten Burst derselben Akteur-/Host-Kombination, wird dieser Burst fortgesetzt. Die Tabelle `burst_request` speichert die eindeutige Zuordnung; ihre eindeutige Request-ID verhindert, dass ein Request mehreren Bursts angehört. Vorhandene Daten werden beim ersten Collector-Start mit diesem Schema einmal neu aufgebaut; rückdatierte Requests lösen nur für die betroffene Akteur-/Host-Kombination eine vollständige Neuberechnung aus.

## Zeitsteuerung und Wartung

Der Scheduler startet fällige Jobs beim Start des Collectors und plant den nächsten Lauf jeweils nach Abschluss des aktuellen Laufs. `INPUT_INTERVAL_SECONDS` steuert das Importintervall; `MAINTENANCE_INTERVAL_DAYS` das Wartungsintervall. Wartung entfernt Akteure, die länger als `MAINTENANCE_INACTIVE_DAYS` inaktiv waren, einschließlich zugehöriger abhängiger Daten. Zusätzlich löscht sie Web-/Cowrie-Ereignisse und rotierte Cowrie-JSON-/Diagnoselogs, die älter als `MAINTENANCE_LOG_RETENTION_DAYS` sind; `0` deaktiviert diese Bereinigung.

## Persistenz und Mounts

- `./databases` wird für API und Collector nach `/app/databases` eingebunden und enthält die SQLite-Datenbank.
- `./logs` wird für Collector, API und UI nach `/logs` eingebunden; Betriebsprotokolle sind je Dienst getrennt.
- Das Verzeichnis aus `INPUT_LOG_DIR` wird schreibgeschützt nach `/input-logs` eingebunden.
- Das Verzeichnis aus `GEOLITE_DB_DIR` wird schreibgeschützt nach `/geoip` eingebunden.
- Cowries `var/` liegt unter `./cowrie-data/var`; `var/log/cowrie` ist für den Collector nach `/cowrie-logs` eingebunden, damit er datierte Rotationen nach `MAINTENANCE_LOG_RETENTION_DAYS` löschen kann. Der aktive Log bleibt erhalten.

Die Compose-Datei bindet Verzeichnisse vom Host ein. Sichern und überwachen Sie die Datenbank daher auf dem Host. Der Collector liest Access-Logs und Rotationen schreibgeschützt und verändert oder löscht sie nicht. Die Web-Honeypot-Warteschlange wird nach erfolgreichem Import bis zur letzten vollständigen gelesenen Zeile gekürzt.

## Konfiguration

Die Collector-Umgebungsvariablen werden von Compose aus `.env` eingelesen. Unterstützte Variablen und Code-Standardwerte sind in [API.de.md – Collector-Konfiguration](API.de.md#konfiguration) dokumentiert; Beispielwerte für einen Start stehen in [`../.env.example`](../.env.example). Änderungen an `.env` erfordern einen Neustart des Collectors, damit sie wirksam werden.

Die API erhält `COLLECTOR_CONTROL_URL` über Compose; standardmäßig verweist diese Variable auf `http://collector:8001`. Datenbankpfade sind in `common/database.py` festgelegt.

## Verwandte Dokumentation

- [Installation, Betrieb und Fehlerbehebung](../README.de.md)
- [API und Collector verwenden](API.de.md)
- [API und Collector verwenden (English)](API.en.md)
