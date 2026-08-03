# TODO — MeBusKá Corporate Backend

Status as of 2026-08-03. **Plans 2–8 are implemented** — 233 tests green, single
Alembic head, linters clean. Every RF in the requirements document is covered
except RF-07/RF-18's client side and all of RF-09/RF-13/RF-16/RF-17's UI, which
live in the frontend repo (plan 9).

This file tracks what remains and the debt the work left or uncovered.

---

## Blocking on someone else — needs a decision or data

These are not code problems. Each one is a question I cannot answer from the
repository.

1. **PaqTcPB and CITTA are not seeded.** RF-02 names four served institutions;
   only UFCG and UEPB exist. Real CNPJ, coordinates and `codigo_externo` are
   needed — inventing institutional records was not an option.
2. **`seed.py` and `scripts/seeds/` are broken and were never fixed by the
   rename.** They resolve the tenant by IBGE code `2504009` (Campina Grande)
   and require a municipalities CSV import; `Organizacao` dropped `codigo_ibge`
   on purpose. This is not a rename miss — the corporate demo data has to be
   re-authored around a tenant that is a foundation, not a municipality, and it
   needs item 1 first. They are also the only source of the repo's remaining
   ruff/black failures, which is why `make lint` (scoped to `app/`) looks clean.
3. **No device identity for telemetry ingestion (RF-22).** Ingestion
   authenticates as a driver or manager, so `mebuska-deploy` must provision an
   account and store a long-lived token on the vehicle reader. Rotation and
   revocation for a headless device are unsolved. Cheaper to settle before the
   van is in service.
4. **CPF is mandatory at signup and RF-02 never asks for it.** `usuario.cpf` is
   `NOT NULL UNIQUE`. Dropping it is a small migration, but whether to collect
   the identifier at all is a data-minimisation question under the LGPD, not a
   technical one.
5. **Boarding is bearer-only.** The passenger photograph in RF-15/RF-17 was
   descoped by the sponsor, so the visual check that RF-17 describes as the
   anti-fraud mechanism does not exist. A forwarded or screenshotted token is
   indistinguishable from the real passenger, and the manual fallback has no
   identity check whatsoever. Every manual boarding writes an `Ocorrencia` so a
   manager can audit after the fact — that is mitigation, not the control the
   requirement specifies. Worth re-confirming with the sponsor in writing.

---

## Blocking — settle before WP2 starts

### IP clause with PaqTcPB

The Plano de Trabalho does not define intellectual property, and its language
points away from BusKa ownership. §8.2 says the Foundation *"fortalece **seu
portfólio** de soluções voltadas ao setor de GovTech"* and contemplates
*"adaptar e expandir a plataforma a outros municípios e governos estaduais"* —
which is product 1's market. §1 describes *"um núcleo algorítmico inteiramente
novo"*, and §7 funds six developers for five months via bolsas.

Needed in writing, standard R&D split:

- **Background IP** — `municipal-backend` and anything extracted from it. BusKa
  property, licensed to the project. Name it explicitly with version and date.
- **Foreground IP** — the DRT algorithm, buffer window, capacity vector, QR
  boarding, offline sync. Titularity assigned by agreement.

Proposed settlement: BusKa owns Foreground IP; PaqTcPB gets a perpetual,
irrevocable, royalty-free licence for its own operations, the right to publicise
the case, and a revenue share on future municipal/state sales.

Also review the existing incubation agreement — it may already carry standing IP
terms.

**Until this is signed**, the copy-with-clean-history approach keeps both
products separable whichever way it lands.

### Naming decision

Is *MeBuska* the company rebrand or the name of product 2? The requirements doc
uses "MeBusKa" for the PaqTcPB system, which reads like product 2. This blocks
final repo naming; renaming twice is the expensive part.

---

## Remaining plans

Each produces working, testable software on its own. See
`docs/superpowers/plans/2026-08-03-foundation.md` for the full roadmap.

| Plan | Scope | Requirements | Status |
|---|---|---|---|
| 2. Trip lifecycle | `OCIOSA→SOLICITADA→BUFFER_ABERTO→EM_ROTA→FINALIZADA`, availability windows, ride request, buffer timer, broadcast, cancellation | RF-05, 10, 11, 12, 19 | **Done** |
| 3. Capacity engine | Segment load vector, `PicoTrecho` validation, origin/destination declaration, ordered circuit stops | RF-04, 13, 14 | **Done** |
| 4. Boarding | Dynamic QR credential, driver itinerary, validation with manual fallback, offline sync | RF-15, 16, 17, 18 | **Done** (photo descoped) |
| 5. LGPD | Versioned consent capture, account deletion with history anonymisation | RF-09, 20 | **Done** |
| 6. Institution signup | Signup bound to an institution with manager approval | RF-02 | **Done** |
| 7. Dashboard | IPK, denials per stop, per-segment timing, exportable period reports | RF-21 | **Done** |
| 8. Telemetry | Ingestion endpoint, time-series storage | RF-22 | **Done** |
| 9. Frontend | Student app, driver app (offline-first), manager dashboard | RF-07, 18, all UI | Separate repo |

RF-01, 03, 06, 07, 08 were inherited and needed verification, not construction,
after the `Organizacao` rename. `tests/integration/test_requisitos_herdados.py`
asserts all five still work.

### Two decisions taken during implementation

**The load vector lives in Postgres, not Redis.** RF-14 names Redis. The vector
is instead derived from the `CONFIRMADO` rows, with concurrent declarations
serialising on a `SELECT … FOR UPDATE` of the trip row. It is exact,
transactional, and adds no infrastructure; the ceiling is serialisation per
trip. `tests/integration/test_capacidade_concorrencia.py` proves the lock holds
under two real connections — and was verified failing with the lock removed,
because a sequential test would pass either way.

**`AlunosConfirmados` is the ride-request row**, rather than a new
`SolicitacaoViagem` table. It was already `(viagem_id, aluno_id)` carrying
origin and destination stops, which is the exact shape RF-13/RF-14 need.

### How the parallel run actually went

Waves as suggested, except plans 4 and 7 ran concurrently rather than serially —
their file sets are disjoint. What made it work was fixing the shared contract
*first*: enums, models, migrations, `conftest.py` and the namespace registrations
in `app/__init__.py` were written up front and declared off-limits, so no two
agents could collide on them. Each agent got its own `TEST_DATABASE_URI` and none
of them ran git commands.

---

## Code debt

### 1. ~~`RotaAluno` has readers but no writer~~ — RESOLVED in plan 2

The five call sites now branch on whether the trip is a DRT round (`rota_id`)
or an inherited scheduled trip (`horario_rota_id`):

- `confirmar_presenca_aluno` — a DRT round rejects and points at `/declaracao`;
  the scheduled path keeps the enrollment gate, which is its only authorisation
- `_popular_dados_da_viagem` — roster-based passenger pre-population removed;
  rows are created per trip by confirmation or declaration
- `viagem_schema.get_total_alunos` — DRT counts the round's rows, legacy counts
  the roster
- `notificacao_service.notificar_por_gestor` — the `viagem_id` branch targets by
  `StatusSolicitacao` so `INTERESSADO` students are reached

**Two readers deliberately still use the roster**, documented in code:
`notificar_por_gestor`'s `rota_id` branch (route-level broadcast only means
something in the scheduled flow) and `verificar_viagens_24h` (it filters on
`AGENDADA` + `horario_rota`, which no round ever satisfies — and its purpose is
to nudge people who have *not* confirmed).

The model and table remain. Deleting them is still a business decision, and
still blocked on retiring the inherited scheduled flow.

### 2. ~~`alembic downgrade base` does not work~~ — FIXED on `dev`

Two inherited defects, both now corrected:

- `expand_instituicao` passed `None` as the constraint name to
  `create_foreign_key` *and* `drop_constraint`. Named explicitly as
  `instituicao_prefeitura_id_fkey` — the name Postgres already generates, so it
  works against existing databases as well as fresh ones.
- `add_ocorrencia` created `tipo_ocorrencia` / `status_ocorrencia` via
  `sa.Enum` inside `create_table`, but its downgrade only dropped the table.
  The orphaned types made the next `upgrade` fail with *"type tipo_ocorrencia
  already exists"*.

Verified `base → head → base → head`, clean each way, zero orphaned types.

**Still open in `municipal-backend`**, which *does* have deployments — port
both fixes there with care. The FK fix is safe (it uses the name Postgres
already assigned); the enum fix only affects downgrade.

### 3. Municipal concepts still in the API surface

**Severity: low — wire-format-breaking to change, so left alone.**

- `schemas/user_schema.py` and `schemas/rota_schema.py` expose `municipio_nome`
  / `municipio_uf`, now sourced from `organizacao.nome` / `organizacao.estado`
- `user_service.get_motoristas_by_municipio()` actually filters by
  `organizacao_id`
- `models/organizacao.py` keeps `estado = String(2)`, a Brazilian UF, on a
  tenant that may not be Brazilian

**Client-visible behaviour change:** `municipio_uf` now returns `null` whenever
`estado` is unset, since corporate tenants aren't required to have a state code.
Belongs in the changelog.

### 4. Left-behind constraint names

**Severity: cosmetic — deliberately not fixed.** After `rename_table`, the
primary key is still `prefeitura_pkey` and five foreign keys are still
`*_prefeitura_id_fkey`. Nothing references constraints by name and autogenerate
does not compare them, so renaming is churn.

The *index* names were renamed explicitly, because autogenerate **does** compare
those — see `docs/migrations.md`.

### 5. `setup_logging` churns root handlers on every `create_app`

**Severity: low.** Each `create_app()` call removes and re-adds root logging
handlers, so tests that construct multiple apps reset global logging mid-session.
Harmless today; will bite the first test that uses `caplog` alongside factory
tests. Fix only if a logging test goes flaky.

### 6. ~~`docs/openapi.json` is stale~~ — FIXED on `dev`

Regenerated with `make docs-openapi`: now `MeBusKá API`, 45 paths, zero
`prefeitura` references, removed subscription/batch endpoints gone.

**Still open:** it is regenerated by hand, so it drifts silently whenever the
API changes. `municipal-frontend`'s `api:generate` consumes it from a sibling
path. The durable fix is publishing it as a release artifact and generating
frontend types from the pinned version, plus running `api:generate` in CI so
drift fails the build. See `ARQUITETURA_REPOSITORIOS.md`.

Regenerated after plans 2–8: 68 paths, 23 of them new, zero `prefeitura`
references. It drifted three times during this work and had to be regenerated
at the end — which is the argument for the CI check, not against the spec.

### 8. `StatusViagem` carries two lifecycles

**Severity: medium — deliberate, needs a business decision.** The enum holds the
four DRT states *and* the inherited `AGENDADA`/`EM_ANDAMENTO` scheduled flow,
which still has live controllers, services and tests. Every function that serves
both branches on `rota_id` vs `horario_rota_id`. That branching is the price of
keeping the municipal flow alive in the corporate product.

Retiring the scheduled flow would delete that branching, `RotaAluno`, and a
meaningful amount of `viagens_service`. It is the single largest simplification
available here — and it is a product decision, not a refactor.

### 7. ~~Ansible playbooks carry a developer's absolute path~~ — FIXED on `dev`

`project_dir` now derives from `{{ playbook_dir | dirname }}`, correct for any
checkout and any working directory. Both playbooks pass
`ansible-playbook --syntax-check`.

Note the original was doubly broken: `lookup('env','PWD') | default(...)` never
fell back, because `lookup('env', ...)` returns an empty string when unset
rather than being undefined, so `default` was skipped.

---

## Cross-repo follow-ups

- **`municipal-backend`** — branch `fix/test-isolation` has two unmerged commits
  (Compose project pinning, destructive-test-DB fence). Needs review and merge.
- **`municipal-backend`** — has no plugin discovery; deliberately not ported,
  since only the corporate product needs it.
- **`municipal-frontend`** — `npm install` is required; `swagger2openapi` and
  `openapi-typescript` are declared in `devDependencies` but absent from
  `node_modules`, so `npm run typecheck` fails. Unrelated to the rename.
- **`mebuska-deploy`** — not yet created. Contract documented in
  `docs/plugins.md`; every client plugin must register under `/v1/<sigla>/`,
  because plugins load after product namespaces and an exact path collision
  leaves the plugin route silently dead.

---

## Repository state

`main` carries the foundation as 13 commits, tagged `0.1.0`. Nothing is pushed —
`origin` is still empty.

History is bisect-clean: every commit builds and passes its suite. The rename
was originally split across two commits, the first of which did not run
(`user_schema.py` read `obj.prefeitura` after the backref had been renamed);
they were squashed into `refactor: rename tenant Prefeitura to Organizacao`,
which passes 61 tests on its own.

There is no `municipal-backend` lineage in this repo — the initial import used
`git archive`, which carries no history. That is deliberate: the PaqTcPB team
has write access here and must not receive product 1's commit history. Keep it
that way if the repo is ever re-imported.
