# TODO — MeBusKá Corporate Backend

Status as of 2026-08-03. Foundation complete (57 tests green, single Alembic
head, linters clean). This file tracks what remains and the debt the foundation
work left or uncovered.

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

| Plan | Scope | Requirements | Depends on | Parallel? |
|---|---|---|---|---|
| 2. Trip lifecycle | `StatusViagem` → `OCIOSA→SOLICITADA→BUFFER_ABERTO→EM_ROTA→FINALIZADA`, availability windows, ride request, buffer timer, broadcast, cancellation | RF-05, 10, 11, 12, 19 | Foundation | Partially |
| 3. Capacity engine | Segment load vector in Redis, `PicoTrecho` validation, origin/destination declaration, ordered circuit stops | RF-04, 13, 14 | Foundation | **Yes** |
| 4. Boarding | Dynamic QR bound to passenger photo, driver itinerary, QR + photo validation with manual fallback | RF-15, 16, 17 | Plans 2, 3 | Partially |
| 5. LGPD | Versioned consent capture, account deletion with history anonymisation | RF-09, 20 | Foundation | **Yes** |
| 6. Institution signup | Signup bound to an institution with manager approval | RF-02 | Foundation | **Yes** |
| 7. Dashboard | IPK, denials per stop, per-segment timing, exportable period reports | RF-21 | Plans 2, 3 | No |
| 8. Telemetry | Ingestion endpoint, time-series storage, `TelemetrySource` interface (vehicle adapter lives in `mebuska-deploy`) | RF-22 | Foundation | **Yes** |
| 9. Frontend | Student app, driver app (offline-first), manager dashboard | RF-07, 18, all UI | Plans 2–8 APIs | Separate repo |

RF-01, 03, 06, 07, 08 already exist in the inherited codebase. They need
**verification after the `Organizacao` rename**, not construction — add that as a
task in Plan 2.

### Suggested agent waves

- **Wave 1 (3 parallel):** Plans 3, 5, 8 — disjoint file sets
- **Wave 2 (2 parallel):** Plans 2, 6
- **Wave 3 (serial):** Plan 4, then Plan 7

Two agents can only run concurrently in the same repo if they don't share a git
index or a test database. Give each its own `TEST_DATABASE_URI` (the guard in
`tests/conftest.py` accepts any name ending `_test`), or use worktrees.

---

## Code debt

### 1. `RotaAluno` has readers but no writer — Plan 2 must resolve

**Severity: high.** Task 4 removed route join/leave management but deliberately
kept the `RotaAluno` roster, because it is load-bearing well beyond subscription
bookkeeping. Rows now only arrive via provisioning or seed data.

Plan 2 replaces standing enrollment with per-trip declaration (RF-13/RF-14) and
must own all four dependent call sites:

- `viagens_service.confirmar_presenca_aluno` — the enrollment check is the
  authorisation gate ("Você não está inscrito na rota desta viagem")
- `notificacao_service.notificar_por_gestor` — resolves which students to notify
- `tasks/notificacao_tasks.verificar_viagens_24h` — same resolution
- `schemas/viagem_schema.get_total_alunos` — occupancy count
- `viagens_service._popular_dados_da_viagem` — passenger population

Do not delete `RotaAluno` before the successor exists. Deleting it is a
business-logic decision, not a cleanup.

### 2. `alembic downgrade base` does not work

**Severity: medium.** Inherited from the municipal product.
`20260408_0237_dcc0d379db3c_expand_instituicao_for_external_catalog_.py` calls
`op.create_foreign_key(None, ...)` and `op.drop_constraint(None, ...)` — an
autogenerate artifact with no real constraint name:

```
CompileError: Can't emit DROP CONSTRAINT for constraint ForeignKeyConstraint(...); it has no name
```

Stepwise downgrades work; only a full unwind fails. This repo has no
deployments, so it is cheap to fix here. `municipal-backend` *does* have
deployments, so fixing it there needs care. Workaround documented in
`docs/migrations.md`.

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

### 6. `docs/openapi.json` is stale

Still contains `prefeitura` and the old API title. It is a generated artifact —
regenerate rather than hand-edit. Note that `municipal-frontend`'s `api:generate`
consumes it from a sibling path; the durable fix is publishing it as a release
artifact (see `ARQUITETURA_REPOSITORIOS.md`).

### 7. Ansible playbooks carry a developer's absolute path

`ansible/setup-dev.yml` and `ansible/run-docker.yml` default `project_dir` to
`/Users/julio/Documents/25.2/projeto1/...`. Pre-existing, inherited.

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
