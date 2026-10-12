# INM2 UI: Entwicklung

[English version](README.en.md) · [Installations- und Betriebsanleitung](../README.de.md)

Diese Datei beschreibt ausschließlich die eigenständige Entwicklung der Weboberfläche. Für Installation und Betrieb der gesamten Anwendung ist die README im Repository-Stamm maßgeblich.

## Voraussetzungen

- Node.js und npm
- Laufende INM2-API unter `http://localhost:8000` (zum Beispiel über Docker Compose aus dem Repository-Stamm)

## Entwicklungsserver

```sh
npm install
npm run dev
```

Vite startet die Oberfläche auf Port `5173` und leitet Anfragen unter `/api` an `http://localhost:8000` weiter. Die genaue lokale URL zeigt Vite beim Start an.

## Build und Vorschau

```sh
npm run build
npm run preview
```

`build` führt TypeScript-Prüfung und Vite-Build aus. `preview` startet Vites lokale Vorschau des erzeugten Builds.

## Aufbau der Oberfläche

- `src/App.tsx`: Navigation, API-Abfragen und Ansichten.
- `src/i18n.ts`: deutsche und englische UI-Texte.
- `src/styles.css`: Layout, Farbvariablen und Themes (`auto`, `cloud`, `midnight`, `moss`).

Der Docker-Build baut die UI mit Node.js und liefert die statischen Dateien über Nginx aus. Im Compose-Betrieb ist die UI unter `http://localhost:3000` erreichbar; Nginx leitet `/api/` an den API-Dienst weiter.
