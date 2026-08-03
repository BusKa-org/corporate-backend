# Plugins — the client extension contract

Client deployment repos extend this product **without editing it**. They declare
registration callables under the `mebuska.plugins` entry-point group; the app
factory discovers and invokes them at startup.

This document is the contract. If you are building a deployment repo, this is
the whole interface you get.

---

## Declaring a plugin

In the deployment repo's `pyproject.toml`:

```toml
[project.entry-points."mebuska.plugins"]
telemetria = "paqtcpb.plugins.telemetria_van:register"
sap = "paqtcpb.plugins.sap:register"
```

Each target is a callable with this signature:

```python
def register(app: Flask, api: Api) -> None: ...
```

That is the entire contract. Everything else you need, you import from the
product: `from app.models.base import db`, `from app.extensions import scheduler`,
`app.config` for settings.

---

## Route namespacing — required

**Every company gets its own route namespace, keyed on the organisation's
`sigla`:**

```
/v1/<sigla>/<resource>
```

| Client | `Organizacao.sigla` | Namespace |
|---|---|---|
| Fundação Parque Tecnológico da Paraíba | `PAQTCPB` | `/v1/paqtcpb/...` |
| *(next corporate client)* | `ACME` | `/v1/acme/...` |

```python
# paqtcpb/plugins/telemetria_van.py
from flask_restx import Namespace, Resource

ns = Namespace("telemetria", path="/telemetria")


@ns.route("/bateria")
class Bateria(Resource):
    def post(self):
        ...


def register(app, api):
    api.add_namespace(ns, path="/v1/paqtcpb/telemetria")
```

### Why this is required, not a style preference

Plugins register **after** the product's own namespaces. Flask matches the first
registered rule, so on an exact path collision **the product wins and the plugin
route is silently dead** — no error, no warning, no log line. The plugin appears
to load fine and its endpoint simply never answers.

That precedence is deliberate and correct: a client must not be able to hijack a
product endpoint such as `/v1/auth/login`. But it means a colliding plugin route
fails in the most confusing way possible. Namespacing under `/v1/<sigla>/` makes
collision structurally impossible, both against the product and against any
future co-installed plugin.

Product-owned prefixes you must never register under: `/v1/auth`, `/v1/users`,
`/v1/notificacoes`, `/v1/onibus`, `/v1/rotas`, `/v1/pontos`, `/v1/routing`,
`/v1/viagens`, `/v1/instituicoes`, `/v1/alunos`, `/v1/ocorrencias`,
`/v1/dashboard`.

### If a route should not be client-specific

Then it is not a plugin. A capability the *next* corporate client would also
want belongs in this product, not in a deployment repo — see
`ARQUITETURA_REPOSITORIOS.md` §7 for where the line sits. Raise it as a product
issue rather than shipping it under your namespace.

---

## Discovery, ordering, and failure

**Discovery.** `plugins=None` (the default) discovers via entry points.
`plugins=[...]` uses the given list verbatim and skips discovery entirely —
including `plugins=[]`, which means "no plugins", not "go find them". Tests use
the explicit form.

**Ordering.** Plugins are sorted by entry-point name before loading, so
registration order is deterministic across environments. Do not rely on that
order for correctness — plugins must not depend on each other.

**Failure is loud.** A plugin that raises during import or during `register()`
aborts application startup, and the traceback names the offending module. This
is intentional: a half-registered API that silently lacks routes is worse than a
process that refuses to start.

**Discovery is logged.** `_discover_plugins()` emits an INFO record naming every
entry point it found, *before* loading any of them:

```
INFO  app  - Plugins discovered  {"plugins": ["sap", "telemetria"]}
```

The structured `plugins` field renders in the production JSON log; the
development console formatter shows only the message text. If your plugin is not
behaving, check this line first — an empty list means the entry point was never
declared or the package is installed in a different virtualenv, which is a
packaging problem, not a code problem.

---

## Migrations

Plugins that add tables own their own Alembic lineage. See `docs/migrations.md`.
Never write revisions into the product's `migrations/versions/`.

---

## Testing your plugin

Use the explicit form so your test does not depend on the package being
installed:

```python
from app import create_app
from paqtcpb.plugins.telemetria_van import register


def test_plugin_registers_route():
    app = create_app(plugins=[register])
    assert app.test_client().post("/v1/paqtcpb/telemetria/bateria").status_code != 404
```

Assert `!= 404` rather than a specific success code — a 404 is exactly the
signature of the silent-collision failure this document exists to prevent.
