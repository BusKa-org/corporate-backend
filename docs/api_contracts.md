# API contracts

The Swagger UI at `/docs` (and `/openapi.json`) is the full reference. This file
documents the on-demand trip lifecycle (Plan 2), whose rules don't fit in Swagger
descriptions. Errors use the standard body `{"error": {"code", "message"}}`.

## On-demand trip lifecycle (RF-05, RF-10, RF-11, RF-12, RF-19)

Trip states for `SOB_DEMANDA` routes:

```
(no active trip = "Ociosa") -> SOLICITADA -> BUFFER_ABERTO -> EM_ANDAMENTO ("em rota") -> FINALIZADA
                                    \-> CANCELADA
```

- A vehicle has at most one active trip (`SOLICITADA`, `BUFFER_ABERTO`, `EM_ANDAMENTO`).
- The trip "time" is `created_at` (request time) until it starts, then `inicio_real`.
  `horario_saida` / `horario_inicio` / `sentido` are `null` for on-demand trips.
- Trip responses carry `rota_id`, `status` and `buffer_fim`.
- Window hours are local time in `FUSO_HORARIO` (default `America/Fortaleza`).
  A window is `[hora_inicio, hora_fim)`: the start minute is inside, the end minute is not.

### Availability windows (RF-05)

| Method | Path | Who |
|---|---|---|
| `GET` | `/v1/onibus/<id>/janelas` | any user of the vehicle's organization |
| `POST` | `/v1/onibus/<id>/janelas` | gestor |
| `DELETE` | `/v1/onibus/<id>/janelas/<janela_id>` | gestor |

`POST` body: `{"motorista_id": uuid, "dia": "SEG".."DOM", "hora_inicio": "HH:MM", "hora_fim": "HH:MM"}`.
Response: `{id, onibus_id, motorista_id, motorista_nome, dia, hora_inicio, hora_fim, created_at}`.
`GET` returns `{items, total}`, ordered by weekday, then `hora_inicio`.

| Status | When |
|---|---|
| 400 | `hora_fim <= hora_inicio`; driver not active; driver from another organization |
| 403 | not a gestor (POST/DELETE); vehicle from another organization |
| 404 | vehicle, driver or window (for that vehicle) not found |
| 409 | overlaps another window of the same vehicle that day, or of the same driver on any vehicle that day |

### Ride request (RF-10)

`POST /v1/rotas/<id>/solicitacoes`: student with current LGPD consent. No body.
Returns 201 with `{id, viagem_id, status, created_at, viagem: {id, status, rota_id, motorista_id, buffer_fim}}`.

- No active trip: creates a `SOLICITADA` trip whose driver is the window's driver,
  and notifies that driver.
- Trip already `SOLICITADA` / `BUFFER_ABERTO` on this route: registers the student
  in the same trip, without notifying the driver again.

| Status | When |
|---|---|
| 400 | fixed route; route without a default vehicle; outside the window (the message lists today's hours, or says there is no operation today) |
| 403 | no consent; not a student; route from another organization |
| 404 | route not found |
| 409 | student already has an active request (also the same trip twice) or is in a trip en route; vehicle en route; vehicle serving another route |

### Driver start (RF-11, RF-12)

`POST /v1/viagens/<id>/iniciar-percurso`: only the trip's driver. No body. Returns 200
with the trip. `SOLICITADA -> BUFFER_ABERTO`, `buffer_fim = now + rota.buffer_minutos`.
It then notifies every student of the organization with an active account, current
consent and notifications on, with the minutes left in the buffer.

| Status | When |
|---|---|
| 403 | not the trip's driver |
| 404 | trip not found |
| 409 | trip is not `SOLICITADA` |

### Request cancellation (RF-19)

`DELETE /v1/viagens/<id>/solicitacao`: student, own request. Consent not required.
Returns 200 with the request (same shape as above).

- `SOLICITADA` / `BUFFER_ABERTO`: request becomes `CANCELADA`. If it was the last active
  request of a `SOLICITADA` trip, the trip becomes `CANCELADA` and the driver is notified.
- `EM_ANDAMENTO`: request becomes `DESISTENCIA` (expected no-show) and the driver is
  notified. The seat is not reopened.

| Status | When |
|---|---|
| 400 | trip `FINALIZADA` / `CANCELADA` |
| 403 | not a student |
| 404 | trip not found, or the student has no active request on it |

### Scheduler jobs

Only run in the scheduler process (`RUN_SCHEDULER`).

- `job_fechar_buffers`, every `JOB_BUFFER_INTERVALO_SEGUNDOS` (30): trips
  `BUFFER_ABERTO` whose `buffer_fim` has passed go to `EM_ANDAMENTO` with
  `inicio_real = buffer_fim`. The driver and the requesting students are notified.
- `job_prazo_inicio`, every `JOB_PRAZO_INICIO_INTERVALO_SEGUNDOS` (60): trips still
  `SOLICITADA` after `rota.prazo_inicio_minutos` notify the organization's gestores
  once (`aviso_prazo_enviado`).

### Changes to existing endpoints

- `POST /v1/viagens/` on an on-demand route returns 400 (trips come from requests).
  On success it now returns 201 with the serialized trip (before, it returned the raw ORM object).
- `PUT /v1/viagens/<id>/confirmacao` on an on-demand trip returns 400.
- `PUT /v1/viagens/<id>/cancelar` returns 403 for a trip of another organization, and
  also cancels and notifies the active requests of the trip.
- Trip listings, the student agenda and the dashboard include on-demand trips.
