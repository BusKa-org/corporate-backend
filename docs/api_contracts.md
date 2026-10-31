# API contracts

The Swagger UI at `/docs` (and `/openapi.json`) is the full reference. This file
documents the rules that don't fit in Swagger descriptions. Errors use the standard body `{"error": {"code", "message"}}`.

## On-demand trip lifecycle (RF-05, RF-10 to RF-19)

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

### Active round of a route (RF-12, secondary flow)

`GET /v1/rotas/<id>/viagem-ativa`: student, gestor or driver of the route's
organization. Lets a student who missed the push see the round and its countdown.
Always 200; an idle vehicle is `"viagem": null` (no 404, so the app needs no error path
for the normal idle case).

```json
{
  "viagem": {"id", "status", "rota_id", "created_at", "inicio_real", "buffer_fim",
             "segundos_restantes_buffer", "motorista": {"id", "nome"},
             "veiculo": {"id", "placa", "modelo"}} | null,
  "minha_solicitacao": {"id", "status"} | null,
  "janelas_hoje": [{"hora_inicio": "08:00", "hora_fim": "12:00"}]
}
```

- `segundos_restantes_buffer` comes from the server clock, is never negative, and is
  `null` outside `BUFFER_ABERTO`.
- `minha_solicitacao` is the caller's active request (students only), so the app can cancel it.
- A vehicle busy with another route counts as no round for this route.

| Status | When |
|---|---|
| 400 | fixed route; malformed id |
| 403 | other organization; role without access |
| 404 | route not found |

Every on-demand endpoint returns 400 for a malformed id in the path.

### Route declaration (RF-13, RF-14)

`POST /v1/viagens/<id>/declaracao`: student with current consent, while the trip is
`BUFFER_ABERTO` and before `buffer_fim`.
Body: `{"ponto_origem_id": uuid, "ponto_destino_id": uuid}`, both stops of the route
circuit, origin before destination. Returns 200 with the request (same shape as the ride
request, plus `ponto_embarque_id`, `ponto_destino_id`, `declarada_em`).

- A student who only got the buffer broadcast and has no request yet is first registered
  as in `POST /v1/rotas/<id>/solicitacoes` (same rules and errors).
- Capacity is per segment: with `n` ordered stops there are `n-1` segments, and the route
  `Pi -> Pj` is accepted when the busiest of its segments is below the vehicle capacity.
  Seats free up after drop-off, so disjoint routes share a seat.
- Declaring again replaces the route without competing with your own seat. If the new
  route does not fit, the previous one is kept (409).
- A first declaration that does not fit marks the request `NEGADA` (counted per stop in
  `/v1/dashboard/indicadores`) and returns 409 asking to try the next round. The student
  can request again.

| Status | When |
|---|---|
| 400 | trip not in `BUFFER_ABERTO`; buffer over; stop not in the circuit; origin not before destination; same stop twice |
| 403 | no consent; not a student; other organization |
| 404 | trip not found |
| 409 | no seat on the requested segments |

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
  notified. The seat is not reopened, and the student leaves the driver's boarding list.
- A cancelled request no longer counts in the segment load, so the seat goes back
  to whoever declares next.

| Status | When |
|---|---|
| 400 | trip `FINALIZADA` / `CANCELADA` |
| 403 | not a student |
| 404 | trip not found, or the student has no active request on it |

### Scheduler jobs

Only run in the scheduler process (`RUN_SCHEDULER`).

- `job_fechar_buffers`, every `JOB_BUFFER_INTERVALO_SEGUNDOS` (30): closes trips
  `BUFFER_ABERTO` whose `buffer_fim` has passed (RF-15). Active requests without a
  declared route become `CANCELADA`. If at least one route was declared, the trip goes
  to `EM_ANDAMENTO` with `inicio_real = buffer_fim`; each declared request becomes a
  passenger (`alunos_confirmados`) with a QR boarding credential, the circuit stops are
  copied to the itinerary, and the driver and those students are notified. With no
  declared route the trip becomes `CANCELADA` and the driver is notified.
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

### Replaced endpoints from dev's first on-demand version

Never released. App clients built against `dev` must move to:

| Removed | Use instead |
|---|---|
| `POST /v1/viagens/solicitar` | `POST /v1/rotas/<id>/solicitacoes` |
| `GET /v1/viagens/rodada-ativa` | `GET /v1/rotas/<id>/viagem-ativa` |
| `POST /v1/viagens/<id>/iniciar-percurso` (returned the round) | same path, now returns the trip |
| `POST /v1/viagens/<id>/declaracao` (201, `CONFIRMADO`/`NEGADO`) | same path, 200 with the request (`ATIVA`; 409 means `NEGADA`) |
| `DELETE /v1/viagens/<id>/declaracao` | `DELETE /v1/viagens/<id>/solicitacao` |
| `GET`/`POST /v1/janelas` | `GET`/`POST /v1/onibus/<id>/janelas` |
| `PATCH /v1/janelas/<id>` | delete and create again (`DELETE`/`POST /v1/onibus/<id>/janelas...`) |
| `DELETE /v1/janelas/<id>` | `DELETE /v1/onibus/<id>/janelas/<janela_id>` |
| `GET /v1/janelas/vigente` | `janelas_hoje` in `GET /v1/rotas/<id>/viagem-ativa` |

Trip statuses `OCIOSA` and `EM_ROTA` are gone: "ociosa" is no active trip and "em rota"
is `EM_ANDAMENTO`. The buffer end is `buffer_fim` (was `buffer_expira_em`), and the buffer
length is set per route (`buffer_minutos`), not per window.

## Foto do aluno

### `PUT /v1/alunos/me/foto`

Aluno envia a própria foto, usada pelo motorista na conferência do embarque (RF-15/RF-17).

- `multipart/form-data`, campo `foto`. Sem o campo: 400.
- Tipo decidido pelos primeiros bytes, não pelo nome nem pelo `Content-Type`: JPEG, PNG
  ou WEBP. Outro tipo, arquivo corrompido ou acima de `FOTO_ALUNO_MAX_BYTES`
  (padrão 5 MB): 400.
- Largura x altura acima de `FOTO_ALUNO_MAX_PIXELS` (padrão 25 milhões): 400, com a
  mensagem "A foto deve ter no máximo N megapixels". As dimensões vêm do cabeçalho (IHDR
  no PNG, SOFn no JPEG, VP8X/VP8/VP8L no WEBP); sem dimensões ou com dimensão 0: 400.
  A conferência acontece antes de gravar, então a foto anterior fica.
- Metadados são removidos antes de gravar: EXIF/GPS, XMP e comentários (JPEG), `eXIf`,
  `tEXt`, `zTXt`, `iTXt` e `tIME` (PNG), `EXIF` e `XMP ` (WEBP). O perfil de cor fica.
- A foto nova substitui a anterior. Se a gravação falhar (500), a anterior continua.
- Só aluno: outro papel recebe 404.
- 200: o perfil do aluno, com `foto_url` = `/v1/alunos/<id>/foto`.

### `GET /v1/alunos/<aluno_id>/foto`

Devolve a imagem (`image/jpeg`, `image/png` ou `image/webp`).

- Podem ver: o próprio aluno; o gestor da organização do aluno; o motorista de uma viagem
  `AGENDADA` ou `EM_ANDAMENTO` em que o aluno confirmou presença. Os demais: 403.
- `aluno_id` que não é UUID: 400. Aluno inexistente ou sem foto: 404.

## Acessibilidade do aluno

`necessidades_acessibilidade` (lista de `CADEIRA_DE_RODAS`, `MOBILIDADE_REDUZIDA`,
`DEFICIENCIA_VISUAL`, `DEFICIENCIA_AUDITIVA`, `DEFICIENCIA_INTELECTUAL`, `OUTRA`) e
`observacao_acessibilidade` (texto, até 500 caracteres) são aceitos em
`PUT /v1/alunos/me` e no aceite do convite (`POST /v1/convites/aceite/<token>`). Valor fora
da lista ou texto acima do limite: 400. Itens repetidos são guardados uma vez só, na ordem
em que vieram. Aparecem para o gestor (`GET /v1/alunos/<id>`) e para o motorista na lista
de passageiros da viagem. A exclusão da conta apaga os dois campos.
