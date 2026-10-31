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
  take `buffer_minutos` and `prazo_inicio_minutos` instead of a timetable;
  `POST`/`PUT /v1/rotas` accept and return them. Defaults and limits are settings:
  `ROTA_BUFFER_MINUTOS_PADRAO` (5), `ROTA_BUFFER_MINUTOS_MAX` (30),
  `ROTA_PRAZO_INICIO_MINUTOS_PADRAO` (10), `ROTA_PRAZO_INICIO_MINUTOS_MAX` (120).
- On-demand trip lifecycle (Plan 2, RF-05/10/11/12/19). Availability windows per
  vehicle with an assigned driver (`/v1/onibus/<id>/janelas`); ride requests
  (`POST /v1/rotas/<id>/solicitacoes`) that open a `SOLICITADA` trip and notify the
  window's driver; driver start (`POST /v1/viagens/<id>/iniciar-percurso`) that opens
  the `BUFFER_ABERTO` window and broadcasts to the organization's students; request
  cancellation (`DELETE /v1/viagens/<id>/solicitacao`), recorded as a no-show once the
  trip is en route; the active round of a route with the buffer countdown
  (`GET /v1/rotas/<id>/viagem-ativa`). Scheduler jobs close expired buffers (`EM_ANDAMENTO`) and alert the
  gestor once when the driver misses the start deadline. Trips now carry `rota_id`,
  `buffer_fim` and the new statuses. New settings
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
  New settings `MOTORISTA_HORAS_MAX_DIRECAO`, `MOTORISTA_DESCANSO_MINUTOS` and `TIMEZONE` (default `America/Sao_Paulo`; also used for the
  availability windows).
- Passenger accessibility needs (`necessidades_acessibilidade`, `observacao_acessibilidade`)
  on registration and `PUT /v1/alunos/me`, shown to the gestor and to the driver of the trip.
- Passenger photo: `PUT /v1/alunos/me/foto` (multipart, JPEG/PNG/WEBP, EXIF/GPS and text
  metadata removed) and `GET /v1/alunos/<id>/foto` for the passenger, the organization's
  gestor, and the driver of a scheduled or in-progress trip the passenger confirmed.
  Photos over `FOTO_ALUNO_MAX_PIXELS` (default 25 MP) are rejected with a 400.
  New settings `FOTOS_ALUNO_DIR`, `FOTO_ALUNO_MAX_BYTES` and `FOTO_ALUNO_MAX_PIXELS`; production keeps photos in the
  `fotos_aluno` volume. Account deletion removes the photo file and the accessibility data.
- Photo check on QR boarding (RF-15/RF-17/RF-18). `POST /v1/embarque/viagens/<id>/checkin`
  checks the credential and returns the passenger with `foto_url`/`sem_foto`, without boarding.
  The driver then calls `POST .../confirmacao` (boards and uses the credential, with row locks so
  two simultaneous confirmations board once) or `POST .../recusa` (`FOTO_NAO_CONFERE`/`SEM_FOTO`:
  no boarding, the credential becomes rejected and boards no one else, an open ocorrência for
  the gestor). The old `POST .../validacao` returns 410 `ENDPOINT_DESCONTINUADO`. A student with
  no photo cannot board by QR (`SEM_FOTO_EXIGE_MANUAL`); the driver uses the manual path.
  Online boarding uses the server clock and ignores `ocorrido_em`.
- Rotating boarding QR (RF-15). The credential keeps a 32-byte secret instead of a static token;
  the student app derives a TOTP code (RFC 6238, HMAC-SHA1, 30 s, 6 digits) and shows
  `<credencial_id>.<codigo>`. New settings `QR_PASSO_SEGUNDOS`, `QR_DIGITOS`, `QR_JANELA_PASSOS`.
  At most one active credential per student and trip; re-issuing for another stop revokes the
  old one, and a credential for a stop that is no longer the student's is refused
  (`CREDENCIAL_DESATUALIZADA`). Migration `c1d2e3f4a5b6`.
- Offline sync: QR boardings use the new event type `EMBARQUE_CONFIRMADO` (the old `EMBARQUE` is
  refused per event with `EVENTO_DESCONTINUADO`), events apply in event-time order, a `RECUSA`
  blocks later boardings with the same QR, and event times are bounded (`EVENTO_NO_FUTURO`,
  `EVENTO_ANTES_DA_CREDENCIAL`, setting `SYNC_TOLERANCIA_SEGUNDOS`).
  **Breaking for both apps:** see `docs/api_contracts.md`.
- Rate limiting with Flask-Limiter: `429` in the standard error body (`RATE_LIMITED`)
  with `Retry-After`. Settings `RATELIMIT_ENABLED`, `RATELIMIT_STORAGE_URI`,
  `RATELIMIT_DEFAULT` (2000/hour), `RATELIMIT_AUTH` (10/min: login, password and
  invitation routes), `RATELIMIT_SENSITIVE` (5/min: PIN check, password reset and
  change) and `RATELIMIT_REALTIME` (120/min: GPS, telemetry, boarding). Counters live
  in Redis, shared by all gunicorn workers: new `redis` service in both compose files
  and `make db-up`; production refuses `memory://`. `/health` and `/ready` are exempt.
  Public auth routes count per e-mail (or per invitation/reset token), not per IP;
  counters are per route and per method; CORS preflight is not counted and CORS
  exposes `Retry-After` and `X-RateLimit-*`. See `docs/api_contracts.md`.

### Removed
- dev's first on-demand implementation, replaced by the one above before any release:
  `POST /v1/viagens/solicitar`, `GET /v1/viagens/rodada-ativa`, `DELETE /v1/viagens/<id>/declaracao`
  and `/v1/janelas` (see `docs/api_contracts.md` for the replacements), the `OCIOSA` and
  `EM_ROTA` trip statuses and the request status on `alunos_confirmados`.
- Passenger self-signup (`POST /v1/alunos/signup`), the guardian consent endpoints, the
  single and batch approval endpoints (`POST /v1/alunos/<id>/aprovar`, `POST /v1/alunos/aprovar`)
  and the gestor-creates-account-with-password endpoint (`POST /v1/users/alunos`).
  Invitations replace all of them: nobody signs up on their own.
- The `aluno.guardian_token` column, dead since the guardian consent endpoints went away.
  CI now runs the Alembic migrations on an empty database and fails on model drift.

### Fixed
- Rate limit keys no longer hold the raw password reset / invitation token, the
  e-mail or the client IP: all are stored as an HMAC-SHA256 keyed with
  `JWT_SECRET_KEY`, so they no longer appear in Redis key names.
- After `DELETE /v1/users/me` the old JWT kept working for up to 2 hours. Every authenticated
  request now loads the user and returns 401 `TOKEN_REVOKED` when the user no longer exists or
  has a status login refuses (`DELETED`, `DISABLED`, `PENDING_APPROVAL`). The rate limiter
  counts such a token by IP. `POST /v1/viagens/<id>/declaracao` also checks, after its locks,
  that the student account is active (403), so a deleted student cannot join a trip in the buffer.
- `PUT /v1/viagens/<id>/confirmacao`: a double tap on the first attendance confirmation of a
  fixed-route trip returned 409 (primary key) for the second tap. The student row is now locked
  before reading the confirmation, so the second tap gets 200 with the same result. Confirming
  while already in another trip en route still returns 409.
- `POST /v1/convites/pin` sent twice at the same time e-mailed two PINs and only the second one
  worked. The invitation row is now locked, so the second request sees the 60-second interval
  between PINs and sends nothing: one valid PIN, one e-mail. Asking again after the interval
  still sends a new PIN.
- `DELETE /v1/users/me` cancels the student's active ride request with the same rules as
  `DELETE /v1/viagens/<id>/solicitacao` (the segment is given back, a trip left with nobody is
  cancelled). Before, the request kept its seat and could become a passenger with a boarding
  credential at buffer close. With an on-demand trip already en route it returns 409, and a
  deleted account can no longer request rides.
- `POST /v1/auth/reset-password`: the same link used twice at the same time changed the
  password twice (or failed with 500). The token row is locked, so the second use gets 400.
- `PUT /v1/alunos/me/foto`: a PNG and a JPEG uploaded at the same time could delete each
  other and leave the student with no photo file. Uploads of the same student now run one at a time.
- `DELETE /v1/users/me` sent twice at the same time returned 500 for one of them; the account
  row is now locked and the second request gets 401.
- `POST /v1/convites/pin/validar` locks the invitation. Parallel wrong guesses were counted as
  one attempt (the 5-attempt limit could be bypassed) and the right PIN could be used twice.
- `POST /v1/embarque/viagens/<id>/sincronizacao`: the same offline queue sent twice at the
  same time answered `recusado`/`CONFLICT` for `RECUSA` and `POSICAO` events instead of
  `ja_aplicado`. The duplicate check now runs after the row lock.
- `POST /v1/embarque/viagens/<id>/sincronizacao`: `RECUSA` and `POSICAO` were deduplicated by
  `evento_id` across all trips, so a `RECUSA` "1" on one trip came back `ja_aplicado` when
  another trip already had a "1": the QR was not closed and no incident reached the gestor
  (same for GPS points). The dedupe key now includes the trip; `evento_id` only needs to be
  unique within the trip's queue.
- `POST /v1/viagens/<id>/declaracao` reloads the trip after taking its lock, so a declaration
  that waited for the buffer close job sees the new status (400) instead of a stale one (404).
- The buffer close job locks the trips it closes. Before, a cancellation running at the same
  time could still turn the student into a confirmed passenger with a boarding credential.
- `DELETE /v1/viagens/<id>/solicitacao` now locks the vehicle and the trip. Before, cancelling
  the last request while another student joined left that student in a cancelled trip, and
  cancelling while the driver started the route overwrote the open buffer with `CANCELADA`.
- A ride request and `POST /v1/viagens/<id>/iniciar-percurso` at the same time deadlocked
  and one of them returned 500. The serialization locks on vehicle, student and trip are now
  `FOR NO KEY UPDATE`, which does not block the foreign key checks of the other request.
- `POST /v1/rotas/<id>/solicitacoes`: a student requesting two routes served by different
  vehicles at the same time ended up with two active requests. The student row is now locked.
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
