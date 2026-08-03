# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial codebase, copied from `municipal-backend` at `v1.2.0`.
  Shared foundation: authentication, users, fleet, geographic points,
  notifications, tracking, error handling, logging, Docker, CI.

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Add on-demand trip lifecycle: `Ociosa → Solicitada → Buffer aberto → Em rota → Finalizada`
- Add segment capacity vector (Redis)
- Add QR boarding credentials and offline-first driver sync
- Refactor `create_app()` for entry-point plugin discovery
