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
- Passenger invitations: the gestor invites people by e-mail, one by one or in a JSON
  batch (`POST /v1/convites`), and lists, resends or cancels them. The person finishes
  the registration from the e-mailed link (`/v1/convites/aceite/<token>`). The invitation
  counts as the gestor's approval, so the account is created active. E-mails are sent in
  the background by a scheduler job. New optional setting `APP_DOWNLOAD_URL`.
  A person who types an enabled e-mail straight into the app gets a 10-minute PIN by e-mail
  (`POST /v1/convites/pin`, `POST /v1/convites/pin/validar`) instead of using the link.

### Removed
- Passenger self-signup (`POST /v1/alunos/signup`), the guardian consent endpoints, the
  single and batch approval endpoints (`POST /v1/alunos/<id>/aprovar`, `POST /v1/alunos/aprovar`)
  and the gestor-creates-account-with-password endpoint (`POST /v1/users/alunos`).
  Invitations replace all of them: nobody signs up on their own.

### Fixed
- `PUT /v1/alunos/me` is a partial update again: omitted fields are left alone. Before,
  the schema defaulted every omitted field to `None`, so sending only the address wiped
  `nome` and `matricula` and ended in a 500. `nome` and `endereco_casa` now return 400
  when sent as null.

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Add on-demand trip lifecycle: `Ociosa → Solicitada → Buffer aberto → Em rota → Finalizada`
- Add segment capacity vector (Redis)
- Add QR boarding credentials and offline-first driver sync
- Refactor `create_app()` for entry-point plugin discovery
