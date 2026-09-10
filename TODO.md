# TODO — PaqTcPB Backend

Status as of 2026-09-09: skeleton commit. Pipeline works (`make run` serves
`/health`), no domain code yet. See
`docs/adr/0001-produto-do-zero-em-vez-de-fork.md` for why this replaces the
`corporate-backend` fork instead of continuing it — that decision also
retired most of what used to be tracked here as code debt (`RotaAluno`,
the `alembic downgrade base` bug, municipal concepts on the wire): all of it
lived in code that no longer exists in this repo.

---

## Blocking — settle before building on top of this skeleton

### IP clause with PaqTcPB

The Plano de Trabalho does not define intellectual property, and its language
points away from BusKa ownership. §8.2 says the Foundation *"fortalece **seu
portfólio** de soluções voltadas ao setor de GovTech"* and contemplates
*"adaptar e expandir a plataforma a outros municípios e governos estaduais"* —
which is product 1's market. §1 describes *"um núcleo algorítmico inteiramente
novo"*, and §7 funds six developers for five months via bolsas.

Needed in writing, standard R&D split:

- **Background IP** — `municipal-backend` and anything extracted from it. BusKa
  property, licensed to the project.
- **Foreground IP** — the DRT algorithm, buffer window, capacity vector, QR
  boarding, offline sync, and now the whole domain of this repo (`Passageiro`,
  `Projeto`, the routing engine). Titularity assigned by agreement.

Proposed settlement (see `ARQUITETURA_REPOSITORIOS.md` seção 2 for the
architectural reasoning): PaqTcPB owns Foreground IP, since it was built
specifically for and funded by this engagement. BusKa owns Background IP —
`municipal-backend` and anything generalized from it into `buska-core` —
regardless of how seção 2 lands, since that predates this contract.

Also review the existing incubation agreement — it may already carry standing
IP terms.

### Naming decision

Is *MeBuska* the company rebrand or the name of product 2? This blocks final
repo naming; renaming twice is the expensive part. `pyproject.toml`'s
`name` field is left as `mebuska-corporate` until this is settled.

---

## Remaining plans

Each produces working, testable software on its own. RF numbers refer to the
PaqTcPB requirements doc.

| Plan | Scope | Requirements | Depends on |
|---|---|---|---|
| 1. Foundation | Auth, `User`/`Motorista`/`Gestor`, `Ponto`/`Endereco`, error handling — the base every other plan needs | RF-01, 03, 06, 08 | — |
| 2. Trip lifecycle | `StatusViagem` → `OCIOSA→SOLICITADA→BUFFER_ABERTO→EM_ROTA→FINALIZADA`, availability windows, ride request, buffer timer, broadcast, cancellation | RF-05, 10, 11, 12, 19 | Plan 1 |
| 3. Capacity engine | Segment load vector, capacity validation, origin/destination declaration, ordered circuit stops | RF-04, 13, 14 | Plan 1 |
| 4. Boarding | Dynamic QR bound to passenger photo, driver itinerary, QR + photo validation with manual fallback | RF-15, 16, 17 | Plans 2, 3 |
| 5. LGPD | Versioned consent capture, account deletion with history anonymisation | RF-09, 20 | Plan 1 |
| 6. Passageiro + Projeto signup | Signup bound to a Projeto, manager approval | RF-02 | Plan 1 |
| 7. Dashboard | IPK, denials per stop, per-segment timing, exportable period reports | RF-21 | Plans 2, 3 |
| 8. Telemetry | Ingestion endpoint, time-series storage, battery SoC/autonomy | RF-22 | Plan 1 |
| 9. Routing engine | The on-demand routing algorithm (modo B). A reference implementation already exists, written by the team — see `app/services/routing/` | RF (modo B, see artefato de arquitetura) | Plan 1 |
| 10. Frontend | Rider app, driver app (offline-first), manager dashboard | RF-07, 18, all UI | Plans 1–9 APIs, separate repo |

---

## Repository state

Skeleton commit on branch `WendellTMO/parque-tecnologico-backend`. `app/`
has the app factory, core infra (config, exceptions, error handlers,
utils) and empty domain packages (`models`, `schemas`, `services`, `api`,
`tasks`). One test (`tests/integration/test_health.py`). No Alembic
migrations yet — `migrations/versions/` is empty, first migration comes with
Plan 1.
