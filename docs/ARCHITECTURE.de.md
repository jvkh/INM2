# Architektur und Datenfluss

[English version](ARCHITECTURE.en.md) · [Zur Installationsanleitung](../README.de.md)

INM2 besteht aus drei per Docker Compose gestarteten Diensten. Der Collector liest Traefik-Access-Logs, die API stellt gespeicherte Daten bereit, und die React-Oberfläche ruft diese API im Browser auf. Collector und API teilen sich eine SQLite-Datenbank.

## Dienste

| Dienst | Implementierung | Aufgabe | Erreichbarkeit im Compose-Setup |
| --- | --- | --- | --- |
| `ui` | React, TypeScript, Nginx | Dashboard und Bedienoberfläche; Nginx leitet `/api/` an die API weiter. | Host-Port `3000`, Container-Port `80` |
| `api` | FastAPI, Uvicorn | REST-Endpunkte unter `/api/v1`, Datenbankzugriff und Weiterleitung manueller Collector-Aufträge. | Host-Port `8000`, Container-Port `8000` |
| `collector` | Python, Uvicorn-Steuerdienst | Importiert Logs, ergänzt optionale Geo-/ASN-Daten, erkennt Bursts und führt Wartung aus. | Steuerport `8001` nur intern im Compose-Netz |

Compose baut die Images aus den Dockerfiles im Repository. UI und API sind auf Host-Ports veröffentlicht; das Compose-Setup richtet selbst keine Anmeldung oder Zugriffskontrolle ein.

## Datenfluss

1. Der Collector liest die in `LOG_FILES` angegebenen Dateien. Unterstützt ist der Reader-Typ `traefik` mit JSON-Objekten pro Zeile.
2. Vollständige verarbeitbare Zeilen werden in Requests, Akteure, Hosts und Kategorien überführt. Die Bursterkennung verarbeitet neue Requests inkrementell und ergänzt bei passendem Abstand den letzten Burst des vorherigen Imports. Nur bei der einmaligen Übernahme vorhandener Daten sowie bei rückdatierten Requests wird die Historie der betroffenen Akteur-/Host-Kombination neu aufgebaut. Nur global routbare Client-IP-Adressen werden importiert; private, Loopback-, Link-Local-, reservierte und ungültige Adressen werden übersprungen.
3. Bei Bedarf ergänzt der Collector City-/Länder- und ASN-/Providerdaten aus lokalen GeoLite2-MMDB-Dateien. Diese Anreicherung ist optional.
4. Collector und API verwenden dieselbe SQLite-Datei unter `databases/inm2.sqlite3`. Die UI greift ausschließlich über HTTP auf die API zu.
5. Geplante und manuell ausgelöste Import- und Wartungsläufe teilen eine Sperre. Manuelle Aufträge laufen im Hintergrund; bei belegtem Collector antwortet die API mit `409`.

## Importverhalten und Logdateien

`INPUT_SAVE_MARGIN_CHARACTERS` hält bei der aktiven Datei einen Puffer am Dateiende zurück, damit unvollständige Logzeilen nicht verarbeitet werden. Neben der konfigurierten Datei liest der Collector passende rotierte Segmente (`access.log.*`, einschließlich `.gz`) in zeitlicher Reihenfolge. Abgeschlossene Segmente werden bis zum Ende gelesen. Positionen sind an Geräte- und Inode-Identität gebunden und bleiben daher beim Umbenennen durch logrotate erhalten. Zusätzlich speichert der Collector einen SHA-256-Fingerabdruck der ersten vollständigen Logzeile (höchstens 64 KiB). Ändert sich der Fingerabdruck bei gleicher Geräte-/Inode-Kennung, beginnt er die Datei erneut bei Byte 0. Offset, Fingerabdruck und Request werden gemeinsam gespeichert. Der Collector verändert oder löscht keine Logdateien; Rotation und Aufbewahrung übernimmt logrotate.

Im Compose-Setup wird `./logs` nach `/logs` eingebunden. Beispiel:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Mehrere Einträge können mit Semikolon getrennt werden. `IGNORE_REQUEST_ROUTES` kann Requests für angegebene Host-/Pfadpräfixe auslassen. `KNOWN_HOSTS` enthält eigene Hostnamen; der Collector synchronisiert sie beim Start in die Tabelle `known_host`. Nur beim Abgleich und in der Bekannte-Hosts-Zusammenfassung gelten `www.example.org` und `example.org` als derselbe Eintrag. Die eigentlichen Hosts und ihre Bursts bleiben getrennt.

Die Bursterkennung trennt Folgen, sobald der Abstand zwischen zwei Requests `BURST_MAX_GAP_SECONDS` überschreitet. Eine Folge gilt als Burst, sobald mindestens `BURST_MIN_REQUESTS` Requests innerhalb von `BURST_WINDOW_SECONDS` liegen; ab dem ersten qualifizierenden Request wird die Folge bis zur nächsten Lücke gezählt. Im laufenden Betrieb werden nur neue Requests und das kurze Zeitfenster zur Qualifizierung betrachtet. Passt ein neuer Request zum letzten Burst derselben Akteur-/Host-Kombination, wird dieser Burst fortgesetzt. Die Tabelle `burst_request` speichert die eindeutige Zuordnung; ihre eindeutige Request-ID verhindert, dass ein Request mehreren Bursts angehört. Vorhandene Daten werden beim ersten Collector-Start mit diesem Schema einmal neu aufgebaut; rückdatierte Requests lösen nur für die betroffene Akteur-/Host-Kombination eine vollständige Neuberechnung aus.

## Zeitsteuerung und Wartung

Der Scheduler startet fällige Jobs beim Start des Collectors und plant den nächsten Lauf jeweils nach Abschluss des aktuellen Laufs. `INPUT_INTERVAL_SECONDS` steuert das Importintervall; `MAINTENANCE_INTERVAL_DAYS` das Wartungsintervall. Wartung entfernt Akteure, die länger als `MAINTENANCE_INACTIVE_DAYS` inaktiv waren, einschließlich zugehöriger abhängiger Daten.

## Persistenz und Mounts

- `./databases` wird für API und Collector nach `/app/databases` eingebunden und enthält die SQLite-Datenbank.
- `./logs` wird für den Collector nach `/logs` eingebunden.
- `./databases/geoip` wird schreibgeschützt nach `/geoip` eingebunden.

Die Compose-Datei bindet Verzeichnisse vom Host ein. Sichern und überwachen Sie die Datenbank daher auf dem Host. Die importierte Logdatei ist wegen des Präfix-Verbrauchs nicht als Backup oder Archiv geeignet.

## Konfiguration

Die Collector-Umgebungsvariablen werden von Compose aus `.env` eingelesen. Unterstützte Variablen und Code-Standardwerte sind in [API.de.md – Collector-Konfiguration](API.de.md#konfiguration) dokumentiert; Beispielwerte für einen Start stehen in [`../.env.example`](../.env.example). Änderungen an `.env` erfordern einen Neustart des Collectors, damit sie wirksam werden.

Die API erhält `COLLECTOR_CONTROL_URL` über Compose; standardmäßig verweist diese Variable auf `http://collector:8001`. Datenbankpfade sind in `common/database.py` festgelegt.

## Verwandte Dokumentation

- [Installation, Betrieb und Fehlerbehebung](../README.de.md)
- [API und Collector verwenden](API.de.md)
- [API und Collector verwenden (English)](API.en.md)
