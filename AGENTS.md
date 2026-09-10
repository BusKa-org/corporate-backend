# AGENTS.md

Instructions for AI coding agents working in this repository. Read this
first; follow links for anything deeper rather than expecting it duplicated
here.

## What this is

PaqTcPB backend: a Flask API for on-demand corporate transport (DRT) for the
Fundação Parque Tecnológico da Paraíba. A skeleton as of this writing — see
[`docs/adr/0001-produto-do-zero-em-vez-de-fork.md`](docs/adr/0001-produto-do-zero-em-vez-de-fork.md)
for why it starts empty instead of continuing the `municipal-backend` fork.
Full architecture, once there is one to describe: `docs/architecture.md`.

Stack: Flask + Flask-RESTX, PostgreSQL + PostGIS, SQLAlchemy + GeoAlchemy2,
Marshmallow, Flask-JWT-Extended, `uv` as the package manager. Same stack as
`municipal-backend` (`~/Documents/buska-backend`), on purpose: this product
reuses the pipeline, not the code.

## Running things

```bash
make install         # install dependencies (uv)
make run              # run the dev server, port 5000 (also brings up the db container)
make db-create        # create the db + apply Alembic migrations
uv run pytest -m "not e2e" -q   # unit + integration tests (what pre-commit runs)
pre-commit run --all-files      # lint + format + test, same as CI
```

Run `make help` for the full target list.

## Conventions that are enforced, not just suggested

- **Commit messages and PR titles must be Conventional Commits**
  (`feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert: ...`,
  header ≤ 100 chars). Enforced by the `conventional-pre-commit` hook locally
  and by `commitlint`/`action-semantic-pull-request` in CI.
- **Pre-commit runs on every commit**: `black`, `ruff --fix`, `mypy`
  (excludes `migrations/` and `tests/`), and `pytest -m "not e2e"`. Don't
  disable or skip a hook to get a commit through; fix what it flagged.
- **Service layer owns business logic and authorization checks.** Controllers
  parse/validate/serialize only; models are data structure only.
- **Raise typed exceptions from `app/core/exceptions.py`**
  (`NotFoundError`, `ValidationError`, `ForbiddenError`, `UnauthorizedError`,
  `ConflictError`), not raw `Exception` or a bare error dict — the handlers
  registered in `app/core/error_handlers.py` map these to the right HTTP
  status; anything else falls through to a generic 500.
- **No `Aluno`, no `Instituicao` (school sense), no `Organizacao` multi-tenant
  layer.** This product serves one client, one deployment. If you find
  yourself reaching for one of these, check
  `ARQUITETURA_REPOSITORIOS.md` seção 4 first — it is probably municipal
  vocabulary that does not apply here.

## Where to look for more

| Question | Look here |
|---|---|
| Why does this repo start empty instead of forked from municipal-backend? | [`docs/adr/0001-produto-do-zero-em-vez-de-fork.md`](docs/adr/0001-produto-do-zero-em-vez-de-fork.md) |
| What is the ownership/repo split this product sits inside? | [`ARQUITETURA_REPOSITORIOS.md`](ARQUITETURA_REPOSITORIOS.md) |
| What's built, what's left, what's blocked? | [`TODO.md`](TODO.md) |
| Why was a non-obvious decision made? | `docs/adr/` — check the index before assuming something is undocumented |
| CI pipeline details | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |

## Before opening a PR

- [ ] `pre-commit run --all-files` passes
- [ ] Commit message(s) and PR title are Conventional Commits
- [ ] A non-obvious decision (chose X over Y, accepted a known trade-off) gets
      an ADR in `docs/adr/`, not just a commit message
