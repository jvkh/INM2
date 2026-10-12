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
2. Vollständige verarbeitbare Zeilen werden in Requests, Akteure, Hosts, Kategorien und Bursts überführt. Nur global routbare Client-IP-Adressen werden importiert; private, Loopback-, Link-Local-, reservierte und ungültige Adressen werden übersprungen.
3. Bei Bedarf ergänzt der Collector City-/Länder- und ASN-/Providerdaten aus lokalen GeoLite2-MMDB-Dateien. Diese Anreicherung ist optional.
4. Collector und API verwenden dieselbe SQLite-Datei unter `databases/inm2.sqlite3`. Die UI greift ausschließlich über HTTP auf die API zu.
5. Geplante und manuell ausgelöste Import- und Wartungsläufe teilen eine Sperre. Manuelle Aufträge laufen im Hintergrund; bei belegtem Collector antwortet die API mit `409`.

## Importverhalten und Logdateien

`INPUT_SAVE_MARGIN_CHARACTERS` hält einen Puffer am Dateiende zurück, damit unvollständige Logzeilen nicht verarbeitet werden. Nach erfolgreicher Speicherung entfernt der Reader den verarbeiteten Präfix der Eingabedatei und verschiebt den Rest an den Anfang. Eine konfigurierte Logdatei ist daher eine veränderliche Arbeitsdatei und kein Archiv. Logrotation oder Archivierung muss so eingerichtet werden, dass Collector und Rotation nicht gleichzeitig dieselbe Datei verändern.

Im Compose-Setup wird `./logs` nach `/logs` eingebunden. Beispiel:

```dotenv
LOG_FILES=traefik:/logs/access.log
```

Mehrere Einträge können mit Semikolon getrennt werden. `IGNORE_REQUEST_ROUTES` kann Requests für angegebene Host-/Pfadpräfixe auslassen.

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
