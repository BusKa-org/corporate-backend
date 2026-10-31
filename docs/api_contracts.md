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
- Window hours are local time in `TIMEZONE` (default `America/Fortaleza`).
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

## Embarque por QR com conferência da foto (RF-15 a RF-18)

### QR dinâmico (RF-15)

`GET /v1/viagens/<id>/credencial-embarque` (aluno) devolve
`{credencial_id, segredo, algoritmo, passo_segundos, digitos, ponto_embarque_id, expira_em, usado}`.
Sai o `token` estático. O app do aluno gera o código sem rede, no padrão TOTP (RFC 6238):
`HMAC-SHA1(segredo, floor(unix_time / passo_segundos))` com truncamento dinâmico, `digitos`
dígitos (padrão 30 s e 6 dígitos; o `segredo` vem em hexadecimal, 32 bytes). O QR desenhado
é `<credencial_id>.<codigo>` e muda a cada passo. O servidor aceita o passo corrente e
`QR_JANELA_PASSOS` passos de cada lado (padrão 1). A credencial continua valendo 4 h e uma vez.
Vale a credencial do ponto em que o aluno está hoje na lista; há no máximo uma ativa por
aluno e viagem (reemitida para outro ponto, a antiga é revogada).

### Embarque (RF-17)

Todas as rotas abaixo são do motorista da viagem, com a viagem `EM_ANDAMENTO`
(outro motorista ou papel: 403). Online vale sempre o relógio do servidor: `ocorrido_em`
saiu dos corpos de `checkin`, `confirmacao`, `recusa` e `manual` e é ignorado se vier.
`qr_token` é o conteúdo lido do QR, `<credencial_id>.<codigo>`. Recusas usam o corpo de erro
padrão com um `code`:

| code | status | quando |
|---|---|---|
| `CREDENCIAL_DESCONHECIDA` | 404 | QR fora do formato ou credencial inexistente |
| `CREDENCIAL_DE_OUTRA_VIAGEM` | 409 | credencial de outra viagem |
| `CREDENCIAL_DE_OUTRO_PONTO` | 409 | o passageiro embarca em outra parada |
| `CREDENCIAL_DESATUALIZADA` | 409 | o ponto do aluno mudou ou a credencial foi reemitida |
| `CREDENCIAL_RECUSADA` | 409 | o motorista já recusou este QR nesta viagem |
| `CREDENCIAL_JA_UTILIZADA` | 409 | o passageiro já embarcou |
| `CREDENCIAL_EXPIRADA` | 409 | passou a validade de 4 h |
| `CODIGO_EXPIRADO` | 409 | código fora da janela (print antigo) ou de outra credencial |
| `PASSAGEIRO_NAO_PREVISTO` | 409 | aluno fora da lista de embarque |
| `SEM_FOTO_EXIGE_MANUAL` | 409 | confirmação de aluno sem foto (só em `confirmacao`) |

O embarque por QR tem dois passos:

1. `POST /v1/embarque/viagens/<id>/checkin` `{qr_token}`: confere a credencial e o código e
   devolve `{viagem_id, aluno_id, nome, foto_url, sem_foto, ponto_embarque_id, ponto_destino_id}`.
   **Não embarca e não consome a credencial.** Credencial inválida: erro, sem foto.
2. O motorista compara a foto com a pessoa e chama um dos dois:
   - `POST /v1/embarque/viagens/<id>/confirmacao` `{qr_token}`: refaz as conferências com as
     linhas travadas, registra o embarque (`embarcado_em`) e marca a credencial como usada.
     Resposta: `{viagem_id, aluno_id, nome, ponto_embarque_id, embarcado_em, manual: false,
     foto_url, sem_foto}`. Duas confirmações ao mesmo tempo: uma embarca, a outra recebe 409
     `CREDENCIAL_JA_UTILIZADA`. Se o código girou além da janela entre os dois passos
     (`CODIGO_EXPIRADO`), o app relê o QR.
   - `POST /v1/embarque/viagens/<id>/recusa` `{qr_token, motivo, observacao?}`,
     `motivo` = `FOTO_NAO_CONFERE` ou `SEM_FOTO`, `observacao` até 500 caracteres: não embarca,
     **recusa a credencial** e abre uma ocorrência (`OUTRO`, `ABERTA`) para o gestor. Resposta:
     `{viagem_id, aluno_id, motivo, ocorrencia_id}`. A recusa não confere o código (ele pode
     ter girado enquanto o motorista olhava a foto). Daí em diante o mesmo QR recebe
     `CREDENCIAL_RECUSADA` em `checkin`, `confirmacao` e na fila offline: a vaga fica
     indisponível para aquela credencial. O passageiro real embarca pelo fallback manual,
     conferido pela foto da lista do ponto. Não há rota para desfazer a recusa.

Aluno sem foto: `checkin` devolve `sem_foto: true`, `foto_url: null`, e `confirmacao`
recusa com `SEM_FOTO_EXIGE_MANUAL`. O motorista usa o fallback manual (que gera ocorrência) ou
recusa com `SEM_FOTO`.

`POST /v1/embarque/viagens/<id>/validacao`: **descontinuado, responde 410**
`ENDPOINT_DESCONTINUADO` com a mensagem "Esta versão do app do motorista não é mais suportada.
Atualize o app...".

`POST /v1/embarque/viagens/<id>/manual` `{aluno_id}` (falha de leitura do QR, aluno sem foto,
passageiro real depois de uma recusa): o motorista confere o rosto pela foto da lista do ponto.
Gera uma ocorrência (`RESOLVIDA`) por uso. A resposta traz `foto_url` e `sem_foto`.

`GET /v1/embarque/viagens/<id>/roteiro` (e `.../roteiro/avancar`): cada passageiro de
`pontos[].passageiros` traz `foto_url`, `sem_foto`, `credencial_id` e `qr_segredo` (sai
`qr_token`). É a lista do ponto para o fallback manual e o que o app baixa antes de perder a
rede: com o `qr_segredo` o app confere o código do QR sem conexão, e as fotos são lidas em
`GET /v1/alunos/<aluno_id>/foto`, liberado ao motorista enquanto a viagem está em rota.

### Fila offline (RF-18)

`POST /v1/embarque/viagens/<id>/sincronizacao`:

- `EMBARQUE_CONFIRMADO` `{qr_token, ponto_id?}`: o QR conferido e confirmado pelo motorista.
  O código é conferido contra o `ocorrido_em` do evento. Mesmas recusas do online.
- `EMBARQUE` (o tipo antigo): recusado evento a evento com `EVENTO_DESCONTINUADO`; os outros
  eventos do lote seguem.
- `RECUSA` `{qr_token, motivo, observacao?}`: abre a ocorrência uma vez só por `evento_id`
  (reenvio: `ja_aplicado`) e recusa a credencial. Não exige o ponto corrente nem a credencial
  sem uso, porque pode chegar depois do embarque manual do passageiro real.
- `EMBARQUE_MANUAL`, `CHEGADA_PONTO` e `POSICAO` sem mudança.

Os eventos são aplicados em ordem de `ocorrido_em` (empate: ordem da fila) e `resultados` sai
nessa ordem. Uma `RECUSA` bloqueia qualquer embarque posterior do mesmo QR, no mesmo lote ou
num lote seguinte (`CREDENCIAL_RECUSADA`). O `ocorrido_em` é limitado: mais de
`SYNC_TOLERANCIA_SEGUNDOS` (padrão 120) no futuro do relógio do servidor dá
`EVENTO_NO_FUTURO`, e um embarque ou recusa de antes da emissão da credencial (com a mesma
tolerância) dá `EVENTO_ANTES_DA_CREDENCIAL`. A validade é conferida no `ocorrido_em`.

### Mudanças para os apps

App do aluno:

- `GET .../credencial-embarque` não traz mais `token`. O app gera o código TOTP a partir de
  `segredo`, `passo_segundos` e `digitos` e desenha o QR `<credencial_id>.<codigo>`,
  renovando a cada passo. Um QR com o token antigo é recusado (`CREDENCIAL_DESCONHECIDA`).

App do motorista:

- **`POST .../validacao` responde 410** `ENDPOINT_DESCONTINUADO`: o app antigo falha alto e
  pede atualização. A leitura passa a ser `POST .../checkin`, que não embarca; depois o app
  chama `.../confirmacao` ou `.../recusa`.
- `qr_token` é o conteúdo do QR (`<credencial_id>.<codigo>`). `ocorrido_em` saiu das rotas
  online.
- Novos códigos de recusa: `CREDENCIAL_RECUSADA`, `CREDENCIAL_DESATUALIZADA`,
  `CODIGO_EXPIRADO`, `SEM_FOTO_EXIGE_MANUAL`. Aluno sem foto: só pelo fallback manual.
- Roteiro: `qr_token` vira `credencial_id` + `qr_segredo`; com eles o app confere o QR offline.
- Fila offline: o embarque por QR é `EMBARQUE_CONFIRMADO`; `EMBARQUE` é recusado com
  `EVENTO_DESCONTINUADO`. Novos códigos `EVENTO_NO_FUTURO` e `EVENTO_ANTES_DA_CREDENCIAL`.
  Os `resultados` vêm em ordem de `ocorrido_em`; case por `evento_id`.

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
  `AGENDADA` ou `EM_ANDAMENTO` em que o aluno confirmou presença, ou de uma rodada
  `BUFFER_ABERTO` em que o aluno já declarou trajeto. Os demais: 403.
- `aluno_id` que não é UUID: 400. Aluno inexistente ou sem foto: 404.

## Acessibilidade do aluno

`necessidades_acessibilidade` (lista de `CADEIRA_DE_RODAS`, `MOBILIDADE_REDUZIDA`,
`DEFICIENCIA_VISUAL`, `DEFICIENCIA_AUDITIVA`, `DEFICIENCIA_INTELECTUAL`, `OUTRA`) e
`observacao_acessibilidade` (texto, até 500 caracteres) são aceitos em
`PUT /v1/alunos/me` e no aceite do convite (`POST /v1/convites/aceite/<token>`). Valor fora
da lista ou texto acima do limite: 400. Itens repetidos são guardados uma vez só, na ordem
em que vieram. Aparecem para o gestor (`GET /v1/alunos/<id>`) e para o motorista na lista
de passageiros da viagem. A exclusão da conta apaga os dois campos.

## Rate limit

Every route is limited by Flask-Limiter. Over the limit, the API answers `429`
with the standard error body (`code: "RATE_LIMITED"`, `details.limit` is the
limit that was hit) and a `Retry-After` header in seconds. Every limited
response also carries `X-RateLimit-Limit`, `X-RateLimit-Remaining` and
`X-RateLimit-Reset`.

Counting key depends on the route:

- Login and the other public auth routes count **per e-mail**, never per IP:
  campus Wi-Fi and mobile carrier NAT put many students behind one IP, so a
  per-IP limit blocked whole classes and let one person lock everyone out. The
  key is the `email` from the JSON body, trimmed and lowercased, for
  `POST /v1/auth/login`, `POST /v1/auth/forgot-password`,
  `POST /v1/convites/pin` and `POST /v1/convites/pin/validar`. A body without
  a valid e-mail (missing, not a string, no `@`, over 254 chars, not JSON)
  counts in one shared `sem-email` bucket; those requests fail validation
  anyway. Known trade-off: anyone can use up a victim's e-mail bucket and block
  that one user's login for up to a minute.
- `POST /v1/auth/reset-password`: the body's e-mail if it has one, otherwise
  the reset `token` (JSON or form). `GET /v1/auth/reset-password` and
  `GET`/`POST /v1/convites/aceite/<token>`: the token. No token: one shared
  `sem-token` bucket.
- Every other route (`change-password`, realtime and the default limit): the JWT
  identity when the request has a valid token, otherwise the connection IP
  (`request.remote_addr`). IP is only left as the key for anonymous routes with
  no e-mail or token. The app has no `ProxyFix`, so `X-Forwarded-For` is
  ignored; behind a reverse proxy every client would share the proxy's IP, so
  add `ProxyFix` before putting one in front.

Each route and each HTTP method counts on its own (`GET` and `POST` on the
same path have separate counters). CORS preflight (`OPTIONS`) is never
counted, and CORS exposes `Retry-After` and `X-RateLimit-*` to the browser.

| Setting | Default | Routes |
|---|---|---|
| `RATELIMIT_SENSITIVE` | `5 per minute` | `POST /v1/convites/pin/validar`, `POST /v1/auth/reset-password`, `POST /v1/users/change-password` |
| `RATELIMIT_AUTH` | `10 per minute` | `POST /v1/auth/login`, `POST /v1/auth/forgot-password`, `GET /v1/auth/reset-password`, `GET`/`POST /v1/convites/aceite/<token>`, `POST /v1/convites/pin` |
| `RATELIMIT_REALTIME` | `120 per minute` | `GET`/`POST /v1/viagens/<id>/localizacao`, `POST /v1/viagens/<id>/localizacao-aluno`, `POST /v1/telemetria/ingestao`, `POST /v1/embarque/viagens/<id>/` `roteiro/avancar`, `checkin`, `confirmacao`, `recusa`, `manual`, `sincronizacao` |
| `RATELIMIT_DEFAULT` | `2000 per hour` | every other route |
| (none) | | `/health`, `/ready` (probes are never limited) |

Other settings: `RATELIMIT_ENABLED` (default `true`; the test suite turns it off)
and `RATELIMIT_STORAGE_URI` (default `memory://`).

Storage: with `memory://` each gunicorn worker keeps its own counters, so the
real limit is N times the setting with N workers. Production must use Redis
(`redis://redis:6379/0` in `docker-compose.prod.yml`, no persistence: counters are
ephemeral, so a restart just resets them); with `FLASK_ENV=production`
and the limiter on, `memory://` makes the app refuse to start. If Redis goes
down at request time the API keeps answering: each worker falls back to
in-memory counters (logged as a warning by `flask-limiter`) and goes back to
Redis once it answers again.
