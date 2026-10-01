# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Initial codebase, copied from `municipal-backend` at `v1.2.0`.
  Shared foundation: authentication, users, fleet, geographic points,
  notifications, tracking, error handling, logging, Docker, CI.
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

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Add on-demand trip lifecycle: `Ociosa → Solicitada → Buffer aberto → Em rota → Finalizada`
- Add segment capacity vector (Redis)
- Add QR boarding credentials and offline-first driver sync
- Refactor `create_app()` for entry-point plugin discovery
