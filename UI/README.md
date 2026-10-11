# INM2 UI

React- und TypeScript-Oberfläche für den Internet Noise Monitor. Dashboard,
Bursts, Akteure, Hosts, Kategorien, Requests und Verwaltung laden Live-Daten aus
der API. Die Datenabfragen laufen asynchron und werden beim Verlassen einer
Ansicht abgebrochen.

## Lokal starten

```sh
npm install
npm run dev
```

Die Entwicklungsumgebung leitet API-Aufrufe unter `/api` an den API-Dienst auf
Port 8000 weiter.

## Oberfläche erweitern

- Texte und Übersetzungen liegen zentral in `src/i18n.ts` (`de` und `en`).
- Farbwerte und Themes (`cloud`, `midnight`, `moss`) sind CSS-Variablen in
  `src/styles.css`; ein Theme kann durch Ergänzen einer Variablenpalette
  hinzugefügt werden.
- `src/App.tsx` stellt Navigation, API-Abfragen und Seiten dar.

## Docker

Der UI-Dienst wird über das Compose-Projekt gebaut und unter
`http://localhost:3000` bereitgestellt. Nginx leitet `/api/` an den API-Dienst
im Compose-Netzwerk weiter.
