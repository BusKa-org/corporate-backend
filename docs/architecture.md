# MeBusKá Corporate Backend — Architecture

This document describes `corporate-backend` as it stands today: a fork of
`municipal-backend` renamed to a generic tenant model, with a plugin
mechanism added for client-specific extensions. For the reasoning behind the
fork, the ownership split, and where this repo is headed, see
[`../ARQUITETURA_REPOSITORIOS.md`](../ARQUITETURA_REPOSITORIOS.md). For the
plugin contract itself, see [`plugins.md`](plugins.md).

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Flask + Flask-RESTX |
| Database | PostgreSQL + PostGIS |
| ORM | SQLAlchemy + GeoAlchemy2 |
| Serialization | Marshmallow |
| Authentication | Flask-JWT-Extended |
| Package Manager | uv |

## Project Structure

```
app/
├── __init__.py          # Flask app factory: extensions, product namespaces, plugin discovery
├── core/
│   ├── config.py         # Environment settings
│   ├── exceptions.py     # Typed exception classes
│   ├── error_handlers.py # Maps exceptions to HTTP responses
│   └── transaction.py    # Transaction helper
├── models/
│   ├── base.py            # SQLAlchemy db instance
│   ├── enum.py            # Shared-core enums (DiaDaSemana, StatusViagem, UserRole, ...)
│   ├── organizacao.py      # Organizacao (tenant) — shared core
│   ├── user.py             # User, Motorista, Gestor — shared core
│   ├── aluno.py            # Aluno — BusKá-only, subclasses User
│   ├── geo.py               # Ponto, Endereco (PostGIS) — shared core
│   ├── instituicao.py       # Instituicao, TipoInstituicao — BusKá-only
│   ├── rota.py               # Rota, RotaPonto, HorarioRota, DiasOperacao, RotaAluno
│   ├── viagem.py              # Viagem, ViagemPonto, AlunosConfirmados, TelemetriaViagem
│   ├── onibus.py               # Onibus (vehicle)
│   ├── notificacao.py          # Notificacao
│   └── password_reset.py        # PasswordResetToken
├── schemas/
│   └── *_schema.py       # Marshmallow schemas for validation + serialization
├── services/
│   └── *_service.py      # Business logic layer
├── api/
│   └── controllers/
│       └── *_controller.py  # Flask-RESTX endpoints
└── utils/
```

`aluno.py` and `instituicao.py` were split out of `user.py` and `geo.py`
respectively: they are BusKá-specific (school transport), not something
PaqTcPB or a future corporate client needs. See
[`../ARQUITETURA_REPOSITORIOS.md`](../ARQUITETURA_REPOSITORIOS.md) section 2
for the ownership rule this split follows, and section 5 for the test that
decides what belongs in a shared core versus a product module.

## Architecture Pattern

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Controller │ ──▶ │   Service   │ ──▶ │    Model    │ ──▶ │  Database   │
│  (Routes)   │     │  (Logic)    │     │   (ORM)     │     │ (PostgreSQL)│
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │
       ▼                   ▼
┌─────────────┐     ┌─────────────┐
│   Schema    │     │  Exception  │
│ (Validate)  │     │  (Errors)   │
└─────────────┘     └─────────────┘
```

| Layer | Responsibility |
|-------|----------------|
| **Controller** | HTTP handling, request parsing, schema validation, response serialization |
| **Service** | Business logic, authorization checks, database transactions |
| **Model** | Data structure, relationships, ORM mapping |
| **Schema** | Input validation, output serialization (single source of truth) |
| **Exception** | Typed errors with HTTP status codes |

## User Roles (Polymorphic Inheritance)

```
User (usuario)
├── Motorista (motorista) — driver, operates trips
├── Gestor (gestor)       — manager, full access to the organizacao's data
└── Aluno (aluno)         — BusKá-only: student, subscribes to routes
```

Joined-table inheritance on `usuario_id`. `Aluno` staying a `User` subclass
is a file-organization split, not a data-model change — see the docstring on
`app/models/aluno.py`.

## Extending this product

Client-specific work does not get added directly to `app/`. It registers
through the plugin mechanism in [`plugins.md`](plugins.md):
`_discover_plugins()` in `app/__init__.py` loads `register(app, api)`
callables published under the `mebuska.plugins` entry-point group by a
deployment repo (e.g. `mebuska-deploy` for PaqTcPB), and every client's
routes live under its own `/v1/<sigla>/` namespace so they cannot collide
with the product's own or with each other.

## Multi-tenancy

Every tenant-scoped table carries `organizacao_id`, a foreign key to
`Organizacao`. `Organizacao` replaced the municipality-only `Prefeitura`
model so the same primitive serves a city government or a private client —
see `TODO.md`'s code-debt section 3 for what's still municipality-shaped on
the wire (`municipio_nome`/`municipio_uf` in a couple of schemas, kept for
backward compatibility).

## Error Handling

Custom exceptions are raised in services and caught by global Flask error
handlers:

```python
# Service raises
raise NotFoundError("Usuário não encontrado")

# Global handler returns
{"error": "Usuário não encontrado"}, 404
```

Available exceptions: `NotFoundError` (404), `ValidationError` (400),
`ForbiddenError` (403), `UnauthorizedError` (401), `ConflictError` (409).

## Database

PostgreSQL with the PostGIS extension for geospatial queries. UUIDs as
primary keys (`uuid-ossp` extension). Automatic `updated_at` timestamps via
trigger.

## Running Locally

```bash
make run      # start the database + dev server
make initdb   # create schema and apply migrations
make seed     # populate seed data
make bdcon    # connect to the database via psql
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DB_USER` | Database user | No (default: buska_user) |
| `DB_PASSWORD` | Database password | No (default: buska_pass) |
| `DB_HOST` | Database host | No (default: localhost) |
| `DB_PORT` | Database port | No (default: 5432) |
| `DB_NAME` | Database name | No (default: buska_db) |
| `JWT_SECRET_KEY` | Secret for JWT signing | Yes |
| `JWT_EXPIRES_HOURS` | Token expiration | No (default: 2) |
