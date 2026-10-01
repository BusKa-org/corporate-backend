# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial codebase, copied from `municipal-backend` at `v1.2.0`.
  Shared foundation: authentication, users, fleet, geographic points,
  notifications, tracking, error handling, logging, Docker, CI.
- LGPD consent: `GET/POST/DELETE /v1/consentimento`, `consentimento_pendente`
  flag on login and `GET /v1/users/me`, and a 403 on trip attendance confirmation
  until the current terms version is accepted.
- Account deletion: `DELETE /v1/users/me` for passengers anonymizes personal
  data, keeps finished-trip history without PII and adds the `DELETED` user status.
  E-mail and CPF are kept in a restricted `retencao_legal` table for 10 years for
  legal purposes. After that a quarterly job replaces them with irreversible hashes (the row
  stays, with nothing sensitive in it).

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Add on-demand trip lifecycle: `Ociosa → Solicitada → Buffer aberto → Em rota → Finalizada`
- Add segment capacity vector (Redis)
- Add QR boarding credentials and offline-first driver sync
- Refactor `create_app()` for entry-point plugin discovery
