# AGENTS.md

Instructions for AI coding agents working in this repository. Read this
first. Follow links for anything deeper; this file does not duplicate that
material.

## What this is

MeBusKá Corporate Backend: a Flask API for demand responsive transport (DRT),
built for the PaqTcPB engagement. It started as a fork of `municipal-backend`,
BusKá's fixed route school transport product, with the tenant model
generalized from `Prefeitura` to `Organizacao`. Full architecture, layering,
and domain model: [`docs/architecture.md`](docs/architecture.md). The
reasoning behind the fork and the IP ownership split with PaqTcPB:
[`ARQUITETURA_REPOSITORIOS.md`](ARQUITETURA_REPOSITORIOS.md).

Stack: Flask + Flask-RESTX, PostgreSQL + PostGIS, SQLAlchemy + GeoAlchemy2,
Marshmallow, Flask-JWT-Extended, `uv` as the package manager.

## The fork strategy, decided in PR #2

[PR #2](https://github.com/BusKa-org/corporate-backend/pull/2) proposed
rebuilding this repo as a generic skeleton, stripped of every BusKá concept
before any PaqTcPB requirement was implemented. The team closed that PR
without merging it and picked a different approach instead, called "option A"
in the discussion:

1. Implement the PaqTcPB requirements (trip lifecycle, capacity engine,
   buffer window, QR boarding) directly against the inherited
   `municipal-backend` code, keeping its existing structure and patterns.
2. Once the requirements are implemented, run an AI pass to remove what
   turned out to be BusKá specific from what got built.

The reasoning on record: building against real BusKá patterns keeps both
products maintainable together during implementation, and an AI doing the
generalization pass afterward has full context on what actually needs
genericizing. Deciding that upfront, on an empty skeleton, was PR #2's
original proposal, and the team judged it as guesswork before any real
requirement existed to inform it.

Practical consequence for anyone working here now: match `municipal-backend`'s
structure and naming for anything that is not clearly PaqTcPB-specific. Do not
pre-emptively genericize code while implementing a feature. The generalization
pass is its own deliberate step, done later, not a side effect of feature
work.

## Running things

```bash
make install         # install dependencies (uv)
make run              # run the dev server, port 5000 (also brings up the db container)
make db-create        # create the db + apply Alembic migrations
make seed             # populate it with seed data (seed.py)
uv run pytest -m "not e2e" -q   # unit + integration tests (what pre-commit runs)
uv run pytest -m e2e            # e2e tests, needs the full stack up
pre-commit run --all-files      # lint + format + test, same as CI
```

Run `make help` for the full target list. Integration and e2e tests need
Postgres/PostGIS reachable (`make db-up`, or `make run` if already
configured); a `pytest` connection error in pre-commit almost always means a
missing local database, not a code problem.

Full local setup options: [`README.md`](README.md).

## Conventions enforced by tooling

- **Pre-commit runs on every commit**: `black`, `ruff --fix`, `mypy`
  (excludes `migrations/` and `tests/`), and `pytest -m "not e2e"`. Fix what a
  hook flags; do not disable or skip it to get a commit through. Note for
  anyone coming from `municipal-backend`: this repo has no conventional-commit
  hook, so its commit message format is not enforced here.
- **Service layer owns business logic and authorization checks.** Controllers
  parse, validate, and serialize only; models are data structure only. See
  "Architecture Pattern" in [`docs/architecture.md`](docs/architecture.md).
- **Raise typed exceptions from `app/core/exceptions.py`**
  (`NotFoundError`, `ValidationError`, `ForbiddenError`, `UnauthorizedError`,
  `ConflictError`), not raw `Exception` or a bare error dict. The handlers in
  `app/core/error_handlers.py` map these to the right HTTP status; anything
  else falls through to a generic 500.
- **Client-specific work never goes directly under `app/`.** It registers
  through the plugin mechanism documented in
  [`docs/plugins.md`](docs/plugins.md).

## Code style: write for a junior developer

Optimize every change for a junior developer reading it for the first time.
Prefer linear procedural code, with loops and `if` statements, over chained
comprehensions, `map`/`filter`, or other clever one-liners. A senior developer
reads the loop just as fast, and a junior developer can actually step through
it.

Bad:

```python
result = [x * 2 for x in dict.fromkeys(items) if x * 2 > 10]
```

Good:

```python
result: list[int] = []
seen: set[int] = set()
for item in items:
    if item in seen:
        continue
    seen.add(item)
    doubled = item * 2
    if doubled > 10:
        result.append(doubled)
```

This applies across services, schemas, tasks, and tests. A one-line
comprehension that filters, transforms, and dedupes in the same expression is
exactly the kind of clever code this rule targets.

## Where to look for more

| Question | Look here |
|---|---|
| How is the app structured and layered? | [`docs/architecture.md`](docs/architecture.md) |
| Where does the product/client IP boundary sit, and where is this repo headed? | [`ARQUITETURA_REPOSITORIOS.md`](ARQUITETURA_REPOSITORIOS.md) |
| What does the plugin contract look like? | [`docs/plugins.md`](docs/plugins.md) |
| What remains to build, and what debt exists? | [`TODO.md`](TODO.md) |
| CI pipeline details | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |

## Before opening a PR

- [ ] `pre-commit run --all-files` passes
- [ ] New or changed endpoints reflected in `docs/api_contracts.md` or
      `docs/endpoints/` if applicable
- [ ] Nothing that implements a PaqTcPB-specific requirement got quietly
      promoted into a shared-core file; see
      [`ARQUITETURA_REPOSITORIOS.md`](ARQUITETURA_REPOSITORIOS.md) section 5
