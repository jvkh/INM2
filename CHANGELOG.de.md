# Änderungshistorie

[English version](CHANGELOG.en.md)

INM2 verwendet [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. Die maßgebliche Versionsnummer steht in [`VERSION`](VERSION). UI-Fußzeile und API-OpenAPI-Metadaten beziehen ihre Laufzeitversion von dort; `ui/package.json` muss bei einer Versionsänderung auf denselben Wert gesetzt werden.

Neue, noch nicht veröffentlichte Änderungen werden unter **Unveröffentlicht** festgehalten. Für ein Release: aktualisiere `VERSION` und `ui/package.json`, verschiebe die Einträge in einen Abschnitt `X.Y.Z — YYYY-MM-DD`, lege danach einen neuen Abschnitt **Unveröffentlicht** an und versehe den Release-Commit mit dem Git-Tag `vX.Y.Z`.

Es sind bislang keine veröffentlichten Versions-Tags vorhanden. Daher werden keine früheren Releases aus Commit-Nachrichten abgeleitet. Die aktuelle Arbeitsversion ist `0.1.0`.

## Unveröffentlicht

- Einzel-Admin-Anmeldung für UI und API mit signiertem, zeitlich begrenztem Sitzungscookie, CSRF-Origin-Prüfung und Drosselung fehlgeschlagener Anmeldungen.
- Klartextpasswort durch einen scrypt-Hash in der Konfiguration ersetzt.
- Optional konfigurierbare TOTP-Zwei-Faktor-Anmeldung für den Einzel-Admin ergänzt.
- API- und UI-Dokumentation um erforderliche Authentifizierungsvariablen und Login-Beispiele ergänzt.


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

### Entfernt

- Veraltete Projektstatus- und Entscheidungsspezifikationsdateien.
