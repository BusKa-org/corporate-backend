# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial codebase, copied from `municipal-backend` at `v1.2.0`.
  Shared foundation: authentication, users, fleet, geographic points,
  notifications, tracking, error handling, logging, Docker, CI.
- Trip types (`TipoViagem`: `FIXA`, `SOB_DEMANDA`) on `Rota`. On-demand routes
  take `buffer_minutos` (1–30, default 5) and `prazo_inicio_minutos` (1–120,
  default 10) instead of a timetable; `POST`/`PUT /v1/rotas` accept and return them.

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Add on-demand trip lifecycle: `Ociosa → Solicitada → Buffer aberto → Em rota → Finalizada`
- Add segment capacity vector (Redis)
- Add QR boarding credentials and offline-first driver sync
- Refactor `create_app()` for entry-point plugin discovery
