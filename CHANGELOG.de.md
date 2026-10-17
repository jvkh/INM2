# Änderungshistorie

[English version](CHANGELOG.en.md)

INM2 verwendet [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. Die maßgebliche Versionsnummer steht in [`VERSION`](VERSION). UI-Fußzeile und API-OpenAPI-Metadaten beziehen ihre Laufzeitversion von dort; `ui/package.json` muss bei einer Versionsänderung auf denselben Wert gesetzt werden.

Neue, noch nicht veröffentlichte Änderungen stehen unter **Unveröffentlicht**. Für ein Release werden `VERSION` und `ui/package.json` aktualisiert, die Einträge in einen Abschnitt `X.Y.Z — YYYY-MM-DD` verschoben, ein neuer Abschnitt **Unveröffentlicht** angelegt und der Release-Commit mit dem Git-Tag `vX.Y.Z` versehen.

Es sind bislang keine veröffentlichten Versions-Tags vorhanden. Daher werden keine früheren Releases aus Commit-Nachrichten abgeleitet. Die aktuelle Arbeitsversion ist `0.1.0`.

## Unveröffentlicht

- Pfad-Scan-Erkennung ergänzt: mindestens acht verschiedene sensible Pfade derselben Quell-IP und desselben Hosts innerhalb von zehn Minuten erzeugen einen Vorfall, der in der Glocke erscheint.
- Langsame, hostübergreifende Pfadscans mit konfigurierbaren Schwellen für Zeitfenster, Pfad- und Hostanzahl sowie Mindestdauer ergänzt.
- Linux-Setup um Menüpunkte für Pflichtangaben, Ports, Zugangssicherheit sowie Burst- und Vorfalleinstellungen ergänzt.
- Menüpunkt zum Löschen von `.env.backup.*`-Dateien mit Sicherheitsabfrage ergänzt.
- Seite „Vorfälle“ mit Zeit-, Status- und Freitextfiltern ergänzt. IPs erscheinen dort und in Vorfallmeldungen mit Provider, ASN, Land und Stadt.
- Status von Vorfällen kann in der Liste dauerhaft auf „Offen“, „Zur Kenntnis genommen“ oder „Erledigt“ gesetzt werden.
- Incident-ID wird angezeigt und führt zu einer nach genau diesem Vorfall gefilterten Requestliste.
- Einzel-Admin-Anmeldung für UI und API mit signiertem, zeitlich begrenztem Sitzungscookie, CSRF-Origin-Prüfung und Drosselung fehlgeschlagener Anmeldungen.
- Klartextpasswort durch einen scrypt-Hash in der Konfiguration ersetzt.
- Optional konfigurierbare TOTP-Zwei-Faktor-Anmeldung für den Einzel-Admin ergänzt.
- API- und UI-Dokumentation um erforderliche Authentifizierungsvariablen und Login-Beispiele ergänzt.
- Linux-Setup ergänzt, das Hostpfade zu Traefik-Logs und GeoLite2-Dateien in `.env` einträgt; Compose bindet diese Verzeichnisse schreibgeschützt ein und `LOG_FILES` kann Dateinamen relativ zum Logverzeichnis enthalten.


## 0.1.1 - 2026-10.12

### Hinzugefügt

- Zentrale Versionsdatei und gemeinsame Versionsanzeige in UI und API.
- Installations- und Betriebsdokumentation auf Deutsch und Englisch, einschließlich Beispielkonfiguration für Docker Compose.
- Englische Fassungen der UI-, API- und Architekturdokumentation.
- Änderungshistorie mit Regeln für künftige Releases.

### Geändert

- Architektur- und API-Dokumentation an die vorhandene Anwendungskonfiguration und Implementierung angepasst.
- UI-README als Anleitung für die lokale UI-Entwicklung präzisiert.
- API-Version an die bestehende UI-Version `0.1.0` angeglichen.
- Vorfälle in einer gemeinsamen Tabelle mit Typ und konkreten Request-Zuordnungen gespeichert; vorhandene Pfad-Scan-Daten werden beim Start migriert.
- Erkennung um Loginfehler, sensible Datei- und Exploit-Antworten, Schreibaktivität, Fehlerhäufungen und Scanner-Signaturen ergänzt.

### Entfernt

- Veraltete Projektstatus- und Entscheidungsspezifikationsdateien.
