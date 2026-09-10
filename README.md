# PaqTcPB Backend

API Flask para transporte corporativo sob demanda (DRT), Fundação Parque
Tecnológico da Paraíba.

Esqueleto inicial: pipeline funcionando, sem domínio ainda. Ver
[`docs/adr/0001-produto-do-zero-em-vez-de-fork.md`](docs/adr/0001-produto-do-zero-em-vez-de-fork.md).

## Setup local

```bash
# 1. Instalar dependências
make install

# 2. Subir o banco e aplicar migrações
make db-create

# 3. Rodar o servidor
make run
```

API em **http://localhost:5000** · Swagger em **http://localhost:5000/docs**.

## Comandos disponíveis

Lista completa: `make help`. Os principais:

```bash
make run              # servidor de desenvolvimento
make test             # suíte de testes (unit + integration)
make lint             # ruff
make format           # black + ruff --fix
make typecheck        # mypy
make migrate-create   # nova migração Alembic (autogenerate)
```

## Estrutura do projeto

```
app/
├── core/          # config, exceptions, error handlers
├── models/        # vazio — ver docstring de cada arquivo
├── schemas/       # vazio — Marshmallow, um por recurso
├── services/      # vazio — lógica de negócio, um módulo por recurso
├── api/controllers/  # vazio — endpoints Flask-RESTX
└── utils/         # logging, security headers, validadores
docs/adr/          # decisões de arquitetura registradas
tests/             # conftest mínimo + teste de /health
```

## Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste. Ver `docs/architecture.md`
para a lista completa.

## Segurança

- **JWT** com expiração configurável (padrão: 2 horas)
- **Security headers**: CSP, XSS Protection, HSTS
- **Audit logging** e **request ID tracking** já vêm de `app/utils/`
