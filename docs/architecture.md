# BusKá Backend Architecture

## Overview

BusKá is a school transport management system built with Flask. It manages routes, trips, students, drivers, and vehicles for municipal school transportation.

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
├── __init__.py          # Flask app factory + error handlers
├── core/
│   ├── config.py        # Environment settings
│   └── exceptions.py    # Custom exception classes
├── models/
│   ├── base.py          # SQLAlchemy db instance
│   ├── enum.py          # Enums (UserRole, StatusViagem, etc.)
│   ├── user.py          # User + polymorphic subtypes (Aluno, Motorista, Gestor)
│   ├── rota.py          # Rota, RotaPonto, HorarioRota, RotaAluno
│   ├── viagem.py        # Viagem, ViagemPonto, ViagemAluno
│   ├── geo.py           # Ponto, Endereco (PostGIS geometry)
│   ├── onibus.py        # Onibus (vehicle)
│   ├── prefeitura.py    # Prefeitura (municipality)
│   └── notificacao.py   # Notificacao
├── schemas/
│   ├── *_schema.py      # Marshmallow schemas for validation + serialization
├── services/
│   ├── *_service.py     # Business logic layer
├── api/
│   └── controllers/
│       └── *_controller.py  # Flask-RESTX endpoints
└── utils/
    └── __init__.py
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

### Layer Responsibilities

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
├── Aluno (aluno)      - Student, can subscribe to routes
├── Motorista (motorista) - Driver, operates trips
└── Gestor (gestor)    - Manager, full access to prefeitura data
```

## Key Domain Concepts

| Entity | Description |
|--------|-------------|
| **Prefeitura** | Municipality that owns all resources |
| **Rota** | Route template with stops and schedules |
| **Viagem** | Actual trip instance generated from a route |
| **Ponto** | Geographic stop point (PostGIS) |
| **Instituicao** | School/institution destination |
| **Onibus** | Vehicle in the fleet |

## Error Handling

Custom exceptions are raised in services and caught by global Flask error handlers:

```python
# Service raises
raise NotFoundError("Usuário não encontrado")

# Global handler returns
{"error": "Usuário não encontrado"}, 404
```

Available exceptions:
- `NotFoundError` (404)
- `ValidationError` (400)
- `ForbiddenError` (403)
- `UnauthorizedError` (401)
- `ConflictError` (409)

## Database

- **PostgreSQL** with **PostGIS** extension for geospatial queries
- UUIDs as primary keys (`uuid-ossp` extension)
- Automatic `updated_at` timestamps via trigger

## Running Locally

```bash
# Start database
make run

# Initialize schema
make initdb

# Seed data
make seed

# Connect to database
make bdcon
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DB_USER` | Database user | No (default: buska_user) |
| `DB_PASSWORD` | Database password | No (default: buska_pass) |
| `DB_HOST` | Database host | No (default: localhost) |
| `DB_PORT` | Database port | No (default: 5432) |
| `DB_NAME` | Database name | No (default: buska_db) |
| `JWT_SECRET_KEY` | Secret for JWT signing | **Yes** |
| `JWT_EXPIRES_HOURS` | Token expiration | No (default: 2) |
