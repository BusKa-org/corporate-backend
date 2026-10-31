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
- Trip types (`TipoViagem`: `FIXA`, `SOB_DEMANDA`) on `Rota`. On-demand routes
  take `buffer_minutos` (1–30, default 5) and `prazo_inicio_minutos` (1–120,
  default 10) instead of a timetable; `POST`/`PUT /v1/rotas` accept and return them.
- On-demand trip lifecycle (Plan 2, RF-05/10/11/12/19). Availability windows per
  vehicle with an assigned driver (`/v1/onibus/<id>/janelas`); ride requests
  (`POST /v1/rotas/<id>/solicitacoes`) that open a `SOLICITADA` trip and notify the
  window's driver; driver start (`POST /v1/viagens/<id>/iniciar-percurso`) that opens
  the `BUFFER_ABERTO` window and broadcasts to the organization's students; request
  cancellation (`DELETE /v1/viagens/<id>/solicitacao`), recorded as a no-show once the
  trip is en route; the active round of a route with the buffer countdown
  (`GET /v1/rotas/<id>/viagem-ativa`). Scheduler jobs close expired buffers (`EM_ANDAMENTO`) and alert the
  gestor once when the driver misses the start deadline. Trips now carry `rota_id`,
  `buffer_fim` and the new statuses. New settings `FUSO_HORARIO`,
  `JOB_BUFFER_INTERVALO_SEGUNDOS`, `JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS`.
- On-demand capacity and boarding on top of that lifecycle (RF-13 to RF-18, RF-21, RF-22).
  During the buffer the student declares origin and destination
  (`POST /v1/viagens/<id>/declaracao`, which also joins the trip if the student only got
  the broadcast); the segment load vector accepts it or marks the request `NEGADA`.
  When the buffer closes, each declared request becomes a passenger with a QR boarding
  credential and the driver's itinerary is built; with no declared route the trip is
  cancelled. Driver itinerary, QR/manual boarding and offline sync (`/v1/embarque/...`),
  gestor indicators and CSV export (`/v1/dashboard/indicadores`) and battery telemetry
  (`/v1/telemetria`) work on these trips. Cancelling during the buffer gives the segment
  back; after departure it is a no-show and leaves the driver's boarding list.
- Circuit editing (`DELETE /v1/rotas/<id>/pontos/<ponto_id>`, gap-free stop order) is
  blocked while a trip that uses the circuit is active.
- Driver working hours and state: the gestor sets `horario_inicio`, `horario_fim` and
  `dias_trabalho` (`PATCH /v1/users/motoristas/<id>`). User responses show the driver's
  `status_motorista` (`ATIVO`, `EM_ROTA`, `EM_DESCANSO_OBRIGATORIO`) and `descanso_ate`. The
  state is computed, not stored: `EM_ROTA` while a trip is `EM_ANDAMENTO`, otherwise
  `EM_DESCANSO_OBRIGATORIO` while `descanso_ate` is in the future, otherwise `ATIVO`.
  Finishing or cancelling a started trip stores `descanso_ate` when the max continuous
  driving time was reached. Starting a trip returns 409 if the driver is `EM_ROTA` and 403
  during rest or outside working hours. It locks the trip and driver rows, so two
  simultaneous starts can't both pass.
  New settings `MOTORISTA_HORAS_MAX_DIRECAO`, `MOTORISTA_DESCANSO_MINUTOS` and `TIMEZONE`.
- Passenger accessibility needs (`necessidades_acessibilidade`, `observacao_acessibilidade`)
  on registration and `PUT /v1/alunos/me`, shown to the gestor and to the driver of the trip.
- Passenger photo: `PUT /v1/alunos/me/foto` (multipart, JPEG/PNG/WEBP, EXIF/GPS and text
  metadata removed) and `GET /v1/alunos/<id>/foto` for the passenger, the organization's
  gestor, and the driver of a scheduled or in-progress trip the passenger confirmed.
  Photos over `FOTO_ALUNO_MAX_PIXELS` (default 25 MP) are rejected with a 400.
  New settings `FOTOS_ALUNO_DIR`, `FOTO_ALUNO_MAX_BYTES` and `FOTO_ALUNO_MAX_PIXELS`; production keeps photos in the
  `fotos_aluno` volume. Account deletion removes the photo file and the accessibility data.

### Removed
- dev's first on-demand implementation, replaced by the one above before any release:
  `POST /v1/viagens/solicitar`, `GET /v1/viagens/rodada-ativa`, `DELETE /v1/viagens/<id>/declaracao`
  and `/v1/janelas` (see `docs/api_contracts.md` for the replacements), the `OCIOSA` and
  `EM_ROTA` trip statuses and the request status on `alunos_confirmados`.
- Passenger self-signup (`POST /v1/alunos/signup`), the guardian consent endpoints, the
  single and batch approval endpoints (`POST /v1/alunos/<id>/aprovar`, `POST /v1/alunos/aprovar`)
  and the gestor-creates-account-with-password endpoint (`POST /v1/users/alunos`).
  Invitations replace all of them: nobody signs up on their own.

### Fixed
- `PUT /v1/rotas/<id>` with a different `tipo` returns 400 instead of 200 doing nothing; the
  route type can't be changed (send the current one or leave it out).
- `PUT /v1/viagens/<id>/cancelar` checks that the trip belongs to the gestor's
  organization (403 otherwise). Before, any gestor could cancel any trip.
- `POST /v1/viagens/` returns the created trip serialized; it returned the raw ORM object.
- Malformed ids on the `/v1/onibus` routes return 400 instead of 500.
- `PUT /v1/alunos/me` is a partial update again: omitted fields are left alone. Before,
  the schema defaulted every omitted field to `None`, so sending only the address wiped
  `nome` and `matricula` and ended in a 500. `nome` and `endereco_casa` now return 400
  when sent as null.

### To do
- Remove municipal-specific modules (route subscription, batch trip generation)
- Rename `Prefeitura` → `Organizacao`
- Refactor `create_app()` for entry-point plugin discovery
