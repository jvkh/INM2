# Changelog

[Deutsche Version](CHANGELOG.de.md)

INM2 uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. The canonical version is stored in [`VERSION`](VERSION). The UI footer and API OpenAPI metadata read their runtime version from that file; keep `ui/package.json` set to the same value whenever the version changes.

Record pending changes under **Unreleased**. To publish a release: update `VERSION` and `ui/package.json`, move the entries into a section named `X.Y.Z — YYYY-MM-DD`, create a fresh **Unreleased** section, and tag the release commit in Git as `vX.Y.Z`.

There are no published version tags in the repository yet. No earlier releases are inferred from commit messages. The current working version is `0.1.0`.

## Unreleased

## 0.1.1 - 2026-10.12

### Added

- A canonical version file and a shared version displayed by the UI and API.
- Installation and operation documentation in German and English, including a Docker Compose example configuration.
- English versions of the UI, API, and architecture documentation.
- This changelog and guidance for future releases.

### Changed

- Updated the architecture and API documentation to match the implemented application and configuration.
- Clarified that the UI README covers local UI development.
- Aligned the API version with the existing UI version, `0.1.0`.

### Removed

- Obsolete project status and decision specification files.
