# MeBusKá Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `corporate-backend` from a renamed copy of the municipal product into a runnable, testable corporate foundation: a working test harness, a plugin-extensible app factory, tenant model renamed to `Organizacao`, and municipal-only modules removed.

**Architecture:** Sequential refactor of an existing Flask/SQLAlchemy codebase. `create_app()` gains a config-override parameter (fixing the broken test harness) and entry-point plugin discovery (enabling the thin client repo). The `Prefeitura` tenant is renamed to `Organizacao` across 33 files plus a migration. Municipal-only surface (route subscription, batch trip generation) is deleted. No DRT features are built here — this plan only makes the ground stable.

**Tech Stack:** Python 3.12, Flask 3.1, Flask-RESTX, Flask-SQLAlchemy 3.1.1, SQLAlchemy 2.0.48, Alembic, PostgreSQL/PostGIS, pytest, uv.

---

## Prerequisites — read before Task 1

**Docker is required.** The test suite cannot run without a live PostgreSQL. Verified during planning:

```
$ uv run pytest -q --no-cov
14 passed, 39 errors
E  psycopg2.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed
```

**Why the errors happen.** `tests/conftest.py:72` sets `SQLALCHEMY_DATABASE_URI="sqlite://"` *after* `create_app()` returns. Flask-SQLAlchemy 3.1.1 binds engines during `db.init_app(app)`, which runs inside `create_app()`, so the override arrives too late and every integration test hits the real Postgres URI. Confirmed:

```
$ uv run python -c "from app import create_app; from app.models.base import db; \
  app=create_app(); print(list(db._app_engines[app].keys()))"
[None]      # engine already bound at init_app time
```

The SQLite config is dead and has been for a while. It also could never have worked: models use `sqlalchemy.dialects.postgresql.UUID` for every primary key (`app/models/prefeitura.py:12`, `app/models/geo.py:13`, etc.), which SQLite does not support. **Task 1 fixes the harness by passing config into `create_app()`, and the suite keeps running on Postgres.**

Before starting:

```bash
cd corporate-backend
cp .env.example .env
make db-up          # docker compose -f infra/database.yml up -d db
uv sync --frozen
```

Verify the baseline is green before changing anything:

```bash
uv run pytest -q --no-cov
```

Expected: all tests pass. **If tests fail here, stop and fix the baseline first** — TDD is meaningless against a red suite.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `app/__init__.py` | App factory: config, extensions, namespaces, plugins | Modify — add `config_overrides` and `plugins` params |
| `app/models/organizacao.py` | Tenant model | Create (replaces `prefeitura.py`) |
| `app/models/prefeitura.py` | — | Delete |
| `app/models/user.py`, `onibus.py`, `geo.py`, `rota.py` | FK column rename | Modify |
| `migrations/versions/<rev>_rename_prefeitura_to_organizacao.py` | Schema rename | Create |
| `migrations/versions/<rev>_drop_municipal_modules.py` | Drop `rota_aluno` | Create |
| `tests/conftest.py` | Test fixtures | Modify — pass config into `create_app` |
| `tests/factories/organizacao_factory.py` | Tenant factory | Create (replaces `prefeitura_factory.py`) |
| `tests/unit/test_app_factory.py` | Factory contract tests | Create |
| `alembic.ini` | Migration branch config | Modify |

---

## Task 1: Config-injectable app factory (fixes the test harness)

**Files:**
- Modify: `app/__init__.py:44` (the `create_app` signature and config block)
- Modify: `tests/conftest.py:65-79`
- Test: `tests/unit/test_app_factory.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_app_factory.py`:

```python
"""Contract tests for create_app(). No DB required."""

from app import create_app


def test_create_app_applies_config_overrides_before_engine_binding():
    """Overrides must reach db.init_app, not arrive after it."""
    app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": "postgresql+psycopg2://x:y@nowhere/z"})
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "postgresql+psycopg2://x:y@nowhere/z"


def test_create_app_override_reaches_the_bound_engine():
    """The engine Flask-SQLAlchemy actually bound must use the overridden URI."""
    from app.models.base import db

    uri = "postgresql+psycopg2://override:pass@127.0.0.1:6543/override_db"
    app = create_app(config_overrides={"SQLALCHEMY_DATABASE_URI": uri})
    engine = db._app_engines[app][None]
    assert "override_db" in str(engine.url)


def test_create_app_without_overrides_still_works():
    app = create_app()
    assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_app_factory.py -v --no-cov`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'config_overrides'`

- [ ] **Step 3: Write minimal implementation**

In `app/__init__.py`, change the signature and add the override application. The override block must sit **after** the `app.config[...]` assignments and **before** `db.init_app(app)`:

```python
def create_app(config_overrides: dict[str, Any] | None = None) -> Flask:
    load_dotenv()
    settings = Settings()
    app = Flask(__name__)
    app.url_map.strict_slashes = False
    # ... existing firebase / config assignments unchanged ...
```

Then locate the line `db.init_app(app)` (currently `app/__init__.py:113`) and insert immediately above it:

```python
    # Test harness and embedding hosts inject config here. Must run before
    # db.init_app(): Flask-SQLAlchemy 3.1 binds engines during init_app, so a
    # later app.config.update() would be silently ignored.
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_app_factory.py -v --no-cov`
Expected: 3 passed

- [ ] **Step 5: Point conftest at the new parameter**

Replace `tests/conftest.py:65-79` with:

```python
@pytest.fixture(scope="session")
def app():
    app = create_app(
        config_overrides={
            "TESTING": True,
            "DEBUG": True,
            "JWT_SECRET_KEY": "change_this_secret_key_use_long_random_string",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        }
    )
    return app
```

Delete the now-unused `from sqlalchemy.pool import StaticPool` import at `tests/conftest.py:8`.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q --no-cov`
Expected: same pass count as the baseline, 0 errors. The suite still uses Postgres — this task removes the dead SQLite config and makes overrides actually work.

- [ ] **Step 7: Commit**

```bash
git add app/__init__.py tests/conftest.py tests/unit/test_app_factory.py
git commit -m "fix: apply config overrides before engine binding in create_app"
```

---

## Task 2: Entry-point plugin discovery

**Files:**
- Modify: `app/__init__.py` (signature + registration loop)
- Test: `tests/unit/test_app_factory.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_app_factory.py`:

```python
def test_create_app_calls_explicit_plugins():
    calls = []

    def fake_plugin(app, api):
        calls.append((app, api))

    create_app(plugins=[fake_plugin])
    assert len(calls) == 1
    app_arg, api_arg = calls[0]
    assert app_arg.name == "app"
    assert hasattr(api_arg, "add_namespace")


def test_create_app_empty_plugin_list_skips_discovery(monkeypatch):
    """plugins=[] means 'no plugins', not 'discover them'."""
    import app as app_module

    monkeypatch.setattr(
        app_module, "_discover_plugins", lambda: (_ for _ in ()).throw(AssertionError("discovery ran"))
    )
    create_app(plugins=[])  # must not raise


def test_plugin_can_register_a_namespace():
    from flask_restx import Namespace, Resource

    ns = Namespace("plugintest", path="/plugintest")

    @ns.route("/ping")
    class Ping(Resource):
        def get(self):
            return {"pong": True}

    def plugin(app, api):
        api.add_namespace(ns, path="/v1/plugintest")

    app = create_app(plugins=[plugin])
    client = app.test_client()
    assert client.get("/v1/plugintest/ping").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_app_factory.py -v --no-cov`
Expected: FAIL with `TypeError: create_app() got an unexpected keyword argument 'plugins'`

- [ ] **Step 3: Write minimal implementation**

At the top of `app/__init__.py`, add to the imports:

```python
from collections.abc import Callable
from importlib.metadata import entry_points
```

Above `create_app`, add:

```python
def _discover_plugins() -> list[Callable[[Flask, Api], None]]:
    """Load registration callables published under the 'mebuska.plugins' group.

    Deployment repos (e.g. mebuska-deploy) declare their plugins in
    pyproject.toml so the product never imports client code by name.
    """
    return [ep.load() for ep in entry_points(group="mebuska.plugins")]
```

Change the signature:

```python
def create_app(
    config_overrides: dict[str, Any] | None = None,
    plugins: list[Callable[[Flask, Api], None]] | None = None,
) -> Flask:
```

After the last `api.add_namespace(...)` call (currently `app/__init__.py:190`, the `dashboard_ns` line), insert:

```python
    # Client-specific extensions. `plugins=[]` disables discovery entirely;
    # `plugins=None` (the default) discovers via entry points.
    for register in (_discover_plugins() if plugins is None else plugins):
        register(app, api)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_app_factory.py -v --no-cov`
Expected: 6 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q --no-cov`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add app/__init__.py tests/unit/test_app_factory.py
git commit -m "feat: discover client plugins via mebuska.plugins entry points"
```

---

## Task 3a: Organizacao model and migration

**Files:**
- Create: `app/models/organizacao.py`
- Delete: `app/models/prefeitura.py`
- Create: `migrations/versions/<rev>_rename_prefeitura_to_organizacao.py`
- Create: `tests/factories/organizacao_factory.py`
- Delete: `tests/factories/prefeitura_factory.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_organizacao_model.py`:

```python
from app.models.organizacao import Organizacao


def test_organizacao_persists_and_defaults_ativo(_db):
    org = Organizacao(nome="Fundação PaqTcPB", sigla="PAQTCPB")
    _db.session.add(org)
    _db.session.commit()

    fetched = _db.session.get(Organizacao, org.id)
    assert fetched.nome == "Fundação PaqTcPB"
    assert fetched.sigla == "PAQTCPB"
    assert fetched.ativo is True
    assert fetched.__tablename__ == "organizacao"


def test_organizacao_sigla_is_unique(_db):
    import pytest
    from sqlalchemy.exc import IntegrityError

    _db.session.add(Organizacao(nome="A", sigla="DUP"))
    _db.session.commit()
    _db.session.add(Organizacao(nome="B", sigla="DUP"))
    with pytest.raises(IntegrityError):
        _db.session.commit()
    _db.session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_organizacao_model.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.organizacao'`

- [ ] **Step 3: Create the model**

Create `app/models/organizacao.py`:

```python
import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Organizacao(db.Model):
    """Tenant: the institution operating a transport service.

    Replaces the municipal `Prefeitura`. `codigo_ibge` is dropped — corporate
    tenants are not municipalities — and `sigla` becomes the stable public key.
    """

    __tablename__ = "organizacao"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = db.Column(db.String(150), nullable=False)
    sigla = db.Column(db.String(20), nullable=False, unique=True, index=True)
    estado = db.Column(db.String(2), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, server_default="true", default=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    usuarios = db.relationship("User", backref=db.backref("organizacao", lazy="joined"), lazy=True)
```

Delete `app/models/prefeitura.py`.

- [ ] **Step 4: Write the migration**

Create `migrations/versions/20260803_0001_a1b2c3d4e5f7_rename_prefeitura_to_organizacao.py`. Replace `<PREVIOUS_HEAD>` with the output of `uv run alembic heads`:

```python
"""rename prefeitura to organizacao

Revision ID: a1b2c3d4e5f7
Revises: <PREVIOUS_HEAD>
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "<PREVIOUS_HEAD>"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("prefeitura", "organizacao")
    op.add_column("organizacao", sa.Column("sigla", sa.String(length=20), nullable=True))
    op.execute("UPDATE organizacao SET sigla = UPPER(LEFT(REPLACE(nome, ' ', ''), 20))")
    op.alter_column("organizacao", "sigla", nullable=False)
    op.create_index("ix_organizacao_sigla", "organizacao", ["sigla"], unique=True)
    op.drop_column("organizacao", "codigo_ibge")
    op.alter_column("organizacao", "estado", nullable=True)

    for table in ("usuario", "onibus", "ponto", "rota"):
        op.alter_column(table, "prefeitura_id", new_column_name="organizacao_id")


def downgrade():
    for table in ("usuario", "onibus", "ponto", "rota"):
        op.alter_column(table, "organizacao_id", new_column_name="prefeitura_id")

    op.alter_column("organizacao", "estado", nullable=False)
    op.add_column("organizacao", sa.Column("codigo_ibge", sa.String(length=10), nullable=True))
    op.execute("UPDATE organizacao SET codigo_ibge = LEFT(sigla, 10)")
    op.alter_column("organizacao", "codigo_ibge", nullable=False)
    op.drop_index("ix_organizacao_sigla", table_name="organizacao")
    op.drop_column("organizacao", "sigla")
    op.rename_table("organizacao", "prefeitura")
```

Before writing, confirm the exact FK-bearing tables and column names:

```bash
uv run python -c "
from app import create_app
from app.models.base import db
app = create_app()
with app.app_context():
    for t in db.metadata.sorted_tables:
        for c in t.columns:
            if 'prefeitura' in c.name:
                print(t.name, c.name)
"
```

Correct the `for table in (...)` tuples in both `upgrade()` and `downgrade()` to match that output exactly.

- [ ] **Step 5: Replace the factory**

Create `tests/factories/organizacao_factory.py`:

```python
import factory

from app.models.organizacao import Organizacao


class OrganizacaoFactory(factory.Factory):
    class Meta:
        model = Organizacao

    nome = factory.Sequence(lambda n: f"Organizacao {n}")
    sigla = factory.Sequence(lambda n: f"ORG{n}")
    estado = "PB"
    ativo = True
```

Delete `tests/factories/prefeitura_factory.py`.

- [ ] **Step 6: Run the model tests**

Run: `uv run pytest tests/integration/test_organizacao_model.py -v --no-cov`
Expected: 2 passed. (Other tests will fail until Task 3b — that is expected.)

- [ ] **Step 7: Commit**

```bash
git add app/models/organizacao.py migrations/versions/ tests/factories/organizacao_factory.py tests/integration/test_organizacao_model.py
git rm app/models/prefeitura.py tests/factories/prefeitura_factory.py
git commit -m "feat: add Organizacao tenant model replacing Prefeitura"
```

---

## Task 3b: Propagate the rename across the codebase

The rename is mechanical: 33 files, four identifier forms. The commands below **are** the implementation — there is no judgement to apply beyond verifying the result.

**Files:** every file listed by the verification command in Step 1.

- [ ] **Step 1: Record the blast radius**

```bash
grep -rli prefeitura app tests | sort | tee /tmp/rename-targets.txt
wc -l /tmp/rename-targets.txt
```

Expected: 33 files (31 after Task 3a deleted two).

- [ ] **Step 2: Apply the mechanical rename**

```bash
xargs -a /tmp/rename-targets.txt sed -i \
  -e 's/PrefeituraFactory/OrganizacaoFactory/g' \
  -e 's/prefeitura_factory/organizacao_factory/g' \
  -e 's/Prefeitura/Organizacao/g' \
  -e 's/prefeitura_id/organizacao_id/g' \
  -e 's/prefeituras/organizacoes/g' \
  -e 's/prefeitura/organizacao/g'
```

- [ ] **Step 3: Verify nothing was missed**

```bash
grep -rni prefeitura app tests && echo "STILL PRESENT — fix manually" || echo "clean"
```

Expected: `clean`

- [ ] **Step 4: Fix the import paths the sed could not know about**

```bash
grep -rn "from app.models.organizacao import\|from .organizacao import" app tests | head
grep -rn "models.organizacao" app/models/__init__.py
```

Confirm `app/models/__init__.py` imports resolve. If `app/models/__init__.py` re-exports the old symbol, update it to:

```python
from .organizacao import Organizacao  # noqa: F401
```

- [ ] **Step 5: Run the full suite**

```bash
uv run alembic upgrade head
uv run pytest -q --no-cov
```

Expected: same pass count as the Task 1 baseline, 0 errors.

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check app tests
uv run black --check app tests
uv run mypy app
```

Expected: all clean. Fix any line-length breaks the sed introduced with `uv run black app tests`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename Prefeitura to Organizacao across app and tests"
```

---

## Task 4: Remove municipal-only modules

> **CORRECTION (2026-08-03, found during execution).** This task originally called for deleting the `RotaAluno` model outright. That was wrong. `RotaAluno` has 17 references across `notificacao_service`, `notificacao_tasks`, `viagem_schema`, `rotas_service` and `viagens_service` — it is the **enrollment roster** backing trip confirmation authorisation, notification targeting, and occupancy counts, not merely subscription bookkeeping. Deleting it here would have required redesigning confirmation auth and notification targeting with no specified successor, inside a task titled "remove modules".
>
> **Revised scope:** delete subscription *management* (join/leave) and batch trip generation. **Keep the `RotaAluno` roster** until Plan 2 replaces standing enrollment with per-trip declaration (RF-13/RF-14). No migration in this task — `rota_aluno` stays, so the head is unchanged.
>
> **Plan 2 must own the replacement**, including: `confirmar_presenca_aluno`'s enrollment check, `notificar_por_gestor` and `verificar_viagens_24h` student resolution, `_popular_dados_da_viagem` passenger population, and `get_total_alunos`. Also note the API surface this task removes includes `POST /v1/viagens/gerar-lote`, which the original plan missed.

Route subscription management and batch trip generation have no corporate equivalent — the DRT flow replaces both. Deleting them now keeps them from being carried through the Plan 2 refactor.

**Files:**
- Modify: `app/models/rota.py` (remove `RotaAluno`)
- Delete: `app/tasks/agendamento_tasks.py`
- Modify: `app/services/rotas_service.py`, `app/api/controllers/rotas_controller.py`
- Delete: `tests/integration/test_agendamento.py`, `tests/integration/test_viagens_aluno_agenda.py`
- Create: `migrations/versions/<rev>_drop_rota_aluno.py`

- [ ] **Step 1: Inventory exactly what depends on them**

```bash
grep -rn "RotaAluno\|rota_aluno\|inscrever\|agendamento_tasks\|gerar_lote\|gerar_viagens" app tests | tee /tmp/municipal-refs.txt
cat /tmp/municipal-refs.txt
```

Record every hit. Each one is either deleted or, if it also serves a corporate need, kept and noted in the commit message.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_municipal_modules_removed.py`:

```python
"""Guards against municipal-only surface reappearing in the corporate product."""

import pytest


def test_rota_aluno_model_is_gone():
    with pytest.raises(ImportError):
        from app.models.rota import RotaAluno  # noqa: F401


def test_agendamento_tasks_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import app.tasks.agendamento_tasks  # noqa: F401


def test_subscription_endpoints_are_gone(client):
    """Route subscription has no corporate equivalent; DRT replaces it."""
    for path in ("/v1/rotas/inscrever", "/v1/rotas/sair"):
        assert client.post(path).status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_municipal_modules_removed.py -v --no-cov`
Expected: FAIL — `RotaAluno` and `agendamento_tasks` still import successfully.

- [ ] **Step 4: Delete the modules**

```bash
git rm app/tasks/agendamento_tasks.py
git rm tests/integration/test_agendamento.py tests/integration/test_viagens_aluno_agenda.py
```

Remove the `RotaAluno` class from `app/models/rota.py`, and remove every reference recorded in `/tmp/municipal-refs.txt` from `app/services/rotas_service.py`, `app/api/controllers/rotas_controller.py`, `app/utils/scheduler_setup.py`, and `tests/factories/rota_factory.py`.

- [ ] **Step 5: Write the migration**

Create `migrations/versions/20260803_0002_b2c3d4e5f6a8_drop_rota_aluno.py`:

```python
"""drop rota_aluno (municipal route subscription)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("rota_aluno")


def downgrade():
    op.create_table(
        "rota_aluno",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("rota_id", UUID(as_uuid=True), sa.ForeignKey("rota.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aluno_id", UUID(as_uuid=True), sa.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
```

Before writing `downgrade()`, dump the real DDL so the recreation is faithful:

```bash
uv run python -c "
from app import create_app
from app.models.base import db
app = create_app()
with app.app_context():
    t = db.metadata.tables['rota_aluno']
    for c in t.columns:
        print(c.name, c.type, 'nullable=', c.nullable, [str(f.target_fullname) for f in c.foreign_keys])
"
```

- [ ] **Step 6: Run the tests**

```bash
uv run alembic upgrade head
uv run pytest -q --no-cov
```

Expected: `tests/unit/test_municipal_modules_removed.py` passes; the rest of the suite passes with a lower total (two integration files were deleted).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove route subscription and batch trip generation"
```

---

## Task 5: Migration branch labels for the client repo

`mebuska-deploy` needs its own Alembic lineage so client migrations never renumber product ones.

**Files:**
- Modify: `alembic.ini`
- Modify: `migrations/env.py`
- Create: `docs/migrations.md`

- [ ] **Step 1: Label the product lineage**

In the earliest revision file (`migrations/versions/20260127_1246_e1d4dadb9200_initial_schema.py`), set:

```python
branch_labels = ("product",)
```

- [ ] **Step 2: Declare multiple version locations**

In `alembic.ini`, add below `script_location`:

```ini
version_locations = %(here)s/migrations/versions
```

- [ ] **Step 3: Verify heads are unambiguous**

Run: `uv run alembic heads`
Expected: exactly one head, labelled `product`.

- [ ] **Step 4: Document the client contract**

Create `docs/migrations.md`:

```markdown
# Migrations

## Product (this repo)

Revisions live in `migrations/versions/` and carry the `product` branch label.
Create them with `uv run alembic revision --autogenerate -m "description"`.

## Client deployments (mebuska-deploy)

Client repos add their own directory and never write into `migrations/versions/`:

    # mebuska-deploy/alembic.ini
    version_locations = %(here)s/migrations/paqtcpb <path-to-installed-product>/migrations/versions

Client revisions set `down_revision` to a *product* revision ID and their own
`branch_labels = ("paqtcpb",)`. New product migrations then merge in without
touching client migrations.

Check for accidental head splits with `alembic heads` — more than one head per
branch label means someone branched by mistake.
```

- [ ] **Step 5: Commit**

```bash
git add alembic.ini migrations/ docs/migrations.md
git commit -m "chore: label product migration branch and document client lineage"
```

---

## Task 6: Verify the foundation end to end

- [ ] **Step 1: Full check**

```bash
uv run alembic downgrade base && uv run alembic upgrade head
uv run pytest -q --no-cov
uv run ruff check app tests && uv run black --check app tests && uv run mypy app
```

Expected: migrations round-trip cleanly, suite green, all linters clean.

- [ ] **Step 2: Verify the plugin seam works from outside**

```bash
mkdir -p /tmp/plugin-smoke && cat > /tmp/plugin-smoke/smoke_plugin.py <<'EOF'
from flask_restx import Namespace, Resource

ns = Namespace("smoke", path="/smoke")


@ns.route("/ping")
class Ping(Resource):
    def get(self):
        return {"pong": True}


def register(app, api):
    api.add_namespace(ns, path="/v1/smoke")
EOF

PYTHONPATH=/tmp/plugin-smoke uv run python -c "
from smoke_plugin import register
from app import create_app
app = create_app(plugins=[register])
r = app.test_client().get('/v1/smoke/ping')
print('status', r.status_code, r.get_json())
assert r.status_code == 200
print('PLUGIN SEAM OK')
"
```

Expected: `status 200 {'pong': True}` then `PLUGIN SEAM OK`

- [ ] **Step 3: Tag the foundation**

```bash
git tag -a v0.2.0 -m "Foundation: Organizacao tenant, plugin factory, municipal modules removed"
```

---

## Self-review notes

- **Spec coverage:** This plan covers no `RF-xx` requirement directly. That is intentional — it is prerequisite work. Requirement coverage begins in Plan 2. See the roadmap below for the RF-to-plan mapping.
- **Type consistency:** `Organizacao.sigla` (String(20), unique) is introduced in Task 3a and used by `OrganizacaoFactory` in the same task. `create_app(config_overrides, plugins)` is defined in Task 1, extended in Task 2, and exercised in Task 6 with the same signature.
- **Known risk:** Task 3b's `sed` runs `s/prefeitura/organizacao/g` last, after the more specific patterns, so ordering matters — do not reorder the `-e` flags. Step 3 is the guard.

---

# Roadmap — remaining plans

The requirements document spans 22 functional requirements across a backend, two mobile apps, a web dashboard, and vehicle IoT. That is far too much for one plan. Each plan below produces working, testable software on its own.

| Plan | Scope | Requirements | Depends on | Parallelizable? |
|---|---|---|---|---|
| **1. Foundation** (this doc) | Test harness, plugin factory, `Organizacao`, module removal | — | — | **No** — one rename touching 33 files; inherently serial |
| **2. Trip lifecycle** | New `StatusViagem` (`OCIOSA→SOLICITADA→BUFFER_ABERTO→EM_ROTA→FINALIZADA`), availability windows, ride request, buffer timer, broadcast, cancellation | RF-05, RF-10, RF-11, RF-12, RF-19 | Plan 1 | Partially — timer/scheduler work splits from state machine |
| **3. Capacity engine** | Segment load vector in Redis, `PicoTrecho` validation, origin/destination declaration, ordered circuit stops | RF-04, RF-13, RF-14 | Plan 1 | **Yes** — pure algorithm + Redis, no overlap with Plan 2 files |
| **4. Boarding** | Dynamic QR credentials bound to passenger photo, driver itinerary, QR + photo validation with manual fallback | RF-15, RF-16, RF-17 | Plans 2, 3 | Partially |
| **5. LGPD** | Versioned consent capture, account deletion with history anonymisation | RF-09, RF-20 | Plan 1 | **Yes** — touches `user`/`auth` only |
| **6. Institution signup** | Signup bound to an institution with manager approval | RF-02 | Plan 1 | **Yes** — touches `user`/`auth` only |
| **7. Dashboard** | IPK, denials per stop, per-segment timing, exportable period reports | RF-21 | Plans 2, 3 | No |
| **8. Telemetry** | Ingestion endpoint, time-series storage, `TelemetrySource` interface (adapter lives in `mebuska-deploy`) | RF-22 | Plan 1 | **Yes** — new module, no shared files |
| **9. Frontend** | Student app, driver app (offline-first), manager dashboard | RF-01…RF-22 UI, RF-07, RF-18 | Plans 2–8 APIs | Separate repo — `corporate-frontend` |

RF-01, RF-03, RF-06, RF-07, RF-08 are already implemented in the inherited codebase and need verification, not construction. Add a task to Plan 2 that asserts each still works after the `Organizacao` rename.

## On parallel agents

Parallelism helps where plans touch disjoint files. Realistic grouping:

- **Wave 1 (serial):** Plan 1. A 33-file rename cannot be parallelised — concurrent agents would collide on every file. One agent, this plan, start to finish.
- **Wave 2 (3 parallel agents):** Plan 3 (capacity engine), Plan 5 (LGPD), Plan 8 (telemetry). Disjoint file sets, all depend only on Plan 1.
- **Wave 3 (2 parallel agents):** Plan 2 (lifecycle) and Plan 6 (institution signup).
- **Wave 4 (serial):** Plan 4, then Plan 7 — both integrate the earlier work.

Running agents in parallel across Plan 1 would produce merge conflicts, not speed.
