# INM2 UI: Development

[Deutsche Version](README.de.md) · [Installation and operation guide](../README.en.md)

This file covers standalone development of the web interface only. For installing and running the complete application, use the README in the repository root.

## Prerequisites

- Node.js and npm
- A running INM2 API at `http://localhost:8000` (for example, through Docker Compose from the repository root)

## Development server

```sh
npm install
npm run dev
```

Vite starts the UI on port `5173` and proxies requests under `/api` to `http://localhost:8000`. Vite prints the exact local URL when it starts.

## Build and preview

```sh
npm run build
npm run preview
```

`build` runs the TypeScript check and Vite build. `preview` starts Vite's local preview of the generated build.

## UI structure

- `src/App.tsx`: navigation, API requests, and views.
- `src/i18n.ts`: German and English UI text.
- `src/styles.css`: layout, color variables, and themes (`auto`, `cloud`, `midnight`, `moss`).

The Docker build compiles the UI with Node.js and serves the static files through Nginx. In Compose, the UI is available at `http://localhost:3000`; Nginx forwards `/api/` to the API service.
