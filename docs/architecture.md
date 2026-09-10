# PaqTcPB Backend — Architecture

Skeleton state: this document describes the pipeline and layering, not a
domain that exists yet. See
[`adr/0001-produto-do-zero-em-vez-de-fork.md`](adr/0001-produto-do-zero-em-vez-de-fork.md)
for why this repo starts here instead of continuing the `corporate-backend`
fork of `municipal-backend`, and [`../ARQUITETURA_REPOSITORIOS.md`](../ARQUITETURA_REPOSITORIOS.md)
for where this product sits relative to the rest of the BusKá org's repos.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Flask + Flask-RESTX |
| Database | PostgreSQL + PostGIS |
| ORM | SQLAlchemy + GeoAlchemy2 |
| Serialization | Marshmallow |
| Authentication | Flask-JWT-Extended |
| Package Manager | uv |

Same stack as `municipal-backend`, so the pipeline (linting, tests, CI,
Docker) transfers without translation. Nothing else does.

## Project Structure

```
app/
├── __init__.py            # Flask app factory: config, extensions, error handlers, /health, /ready
├── core/
│   ├── config.py            # Environment settings
│   ├── exceptions.py        # Typed exception classes
│   ├── error_handlers.py    # Maps exceptions to HTTP responses
│   └── transaction.py       # Transaction helper
├── models/                  # empty — see each file's docstring for what lands there
│   ├── base.py               # SQLAlchemy db instance
│   ├── enum.py                # shared vocabulary (roles, status)
│   ├── user.py                 # User, Motorista, Gestor
│   ├── passageiro.py            # Passageiro: vigência, foto, sem responsável legal
│   ├── projeto.py                # Projeto + Funcionário responsável
│   ├── instituicao_parceira.py    # UFCG, UEPB, PaqTcPB, CITTA
│   ├── geo.py                      # Ponto, Endereco (PostGIS)
│   ├── rota.py                      # Rota, HorarioRota (modo A)
│   ├── viagem.py                     # Viagem, embarque, telemetria
│   ├── reserva.py                     # reserva de vaga, capacidade por trecho
│   ├── onibus.py                       # Onibus + telemetria de bateria
│   └── notificacao.py                   # Notificacao
├── schemas/                # empty — Marshmallow schemas, one per resource
├── services/               # empty — business logic, one module per resource
│   └── routing/              # o motor de rota sob demanda (modo B)
├── api/controllers/        # empty — Flask-RESTX endpoints
├── tasks/                  # empty — background jobs (APScheduler)
└── utils/                  # logging, security headers, validators — carried over as-is
```

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

## User Roles

```
User (usuario)
├── Motorista — inicia percurso, valida embarque, executa o roteiro
└── Gestor    — acesso completo: pontos, janelas, frota, relatórios
```

No `Aluno`. PaqTcPB's rider is `Passageiro`, a top-level model tied to
`Projeto`, not a `User` subtype tied to a school.

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

## No multi-tenancy

There is no `Organizacao` model here. `ARQUITETURA_REPOSITORIOS.md` seção 4
is explicit: a corporate client gets its own deployment, not a shared
runtime — a government SaaS pattern that does not apply to a company. One
deployment, one client, no tenant column on every table.

## Database

PostgreSQL with the PostGIS extension for geospatial queries. UUIDs as
primary keys (`uuid-ossp` extension).

## Running Locally

```bash
make run      # start the database + dev server
make db-create  # create schema and apply migrations
```

`make seed` has no `seed.py` behind it yet — the old one was
`municipal-backend`'s student/school data, which does not apply here.

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
