# BusKá Backend

Flask API for on-demand corporate transport (DRT).

## Local Setup

### Prerequisites
- Python 3.12+
- Docker + Docker Compose
- Ansible (for automation)

### Option 1: Automated Setup (Recommended)

```bash
# Clone the repo and enter the directory
git clone https://github.com/BusKa-org/corporate-backend.git
cd corporate-backend

# Full setup (venv + dependencies + database), then starts the server
chmod +x setup.sh
./setup.sh

# To reset the database
./setup.sh -e clean_database=true
```

The API will be available at: **http://localhost:5000/docs**

---

### Option 2: Manual Setup

```bash
# 1. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
make install

# 3. Start the database and Redis (rate limit counters)
make db-up

# 4. Create the database and apply migrations
make db-create

# 5. (Optional) Seed sample data
make seed

# 6. Run the server
make run
```

The API will be at: **http://localhost:5000** | Swagger: **http://localhost:5000/docs**

#### Verify Installation

```bash
# Check dependencies
pip list | grep -E "python-json-logger"

# Check security headers
curl -I http://localhost:5000/v1/auth/login | grep -E "X-Content-Type|X-Frame|X-XSS|X-Request-ID"
```

---

## Available Commands

### Local Development

```bash
make install        # Install dependencies
make run            # Run the server (port 5000), bringing up db + redis
make db-up          # Start the database and Redis (localhost:6380) containers
make db-create      # Start the database and apply migrations
make seed           # Seed sample data
make db-reset       # Wipe the database
make db-shell       # Connect to the database via psql
make scheduler      # Run the scheduler jobs in a separate process (next to `make run`)
make docs-openapi   # Export the OpenAPI spec to docs/openapi.json
```

Run `make help` for the full list.

### Docker (Production)

```bash
make docker-build   # Build the image
make docker-up      # Bring up containers (port 5000)
make docker-down    # Stop containers
make docker-logs    # Tail logs
make docker-init-db # Extension + migrations + seed (idempotent)
make docker-clean   # Clean up everything (volumes + images)
```

## 📁 Project Structure

```
mebuska-corporate/
├── app/                    # Application code
│   ├── api/
│   │   ├── controllers/    # Flask-RESTX endpoints
│   │   └── contracts/      # Swagger models (documentation only)
│   ├── core/
│   │   ├── config.py       # Configuration
│   │   ├── exceptions.py   # Typed exceptions
│   │   └── error_handlers.py
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Marshmallow validation + serialization
│   ├── services/           # Business logic services
│   └── tasks/              # Scheduler jobs
├── database/               # SQL scripts
│   ├── init.sql            # Schema and extensions
├── docs/                   # API documentation
│   ├── openapi.json        # Exported spec (`make docs-openapi`)
│   └── endpoints/          # Legacy YAML specs, not loaded by the app
├── infra/
│   ├── database.yml        # Docker Compose (dev)
│   └── terraform/          # Infrastructure (OpenStack)
├── ansible/                # Automation playbooks
│   ├── setup-dev.yml       # Local setup
│   ├── run-docker.yml      # Docker deploy
│   └── deploy-prod.yml     # OpenStack deploy
├── tests/                  # Automated tests
├── Dockerfile              # Production build
├── docker-compose.prod.yml # Orchestration (prod)
├── Makefile                # Command automation
├── setup.sh                # Automated setup
└── pyproject.toml          # Python dependencies
```

## Environment Variables

Copy `.env.example` to `.env.prod` and configure:

```bash
# Database
DB_USER=buska_user
DB_PASSWORD=your_secure_password
DB_NAME=buska_db

# API
API_PORT=5000
FLASK_ENV=production
JWT_SECRET_KEY=a_long_random_jwt_secret
JWT_EXPIRES_HOURS=2
```

Every setting, with its default, is in `.env.example` (read by `app/core/config.py`).

### Deploy (GitHub Actions)

The deploy job writes `.env.prod` from repository **secrets** (`DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `JWT_SECRET`, `MAIL_*`, `FRONTEND_URL`, `CORS_ORIGINS`, `FIREBASE_CREDENTIALS`)
and these optional repository **variables** (Settings > Secrets and variables > Actions >
Variables). An unset variable is left out, so the default applies:

| Variable | Default |
|----------|---------|
| `TIMEZONE` | `America/Sao_Paulo` |
| `ROTA_BUFFER_MINUTOS_PADRAO` / `ROTA_BUFFER_MINUTOS_MAX` | `5` / `30` |
| `ROTA_PRAZO_INICIO_MINUTOS_PADRAO` / `ROTA_PRAZO_INICIO_MINUTOS_MAX` | `10` / `120` |

Lowering a `MAX` below its `PADRAO` requires setting the `PADRAO` too, or the API
refuses to start.

## 📚 Documentation

### API Documentation
Full interactive API documentation is available at:
- **Swagger UI**: http://localhost:5000/docs
- **OpenAPI JSON**: http://localhost:5000/openapi.json

Main endpoints:
- `POST /v1/auth/login` - Authenticate
- `POST /v1/convites/aceite/<token>` - Create an account from an invitation
- `GET /v1/rotas/` - List routes
- `GET /v1/viagens/` - List trips
- `GET /v1/users/me` - Authenticated user's data

## 🔒 Security

The backend implements multiple layers of security:

### Authentication & Authorization
- **JWT** with configurable expiration (default: 2 hours)
- **RBAC** (Role-Based Access Control): ALUNO, MOTORISTA, GESTOR
- **Tenant isolation** per Organizacao (organization)

### Protections in Place
- ✅ **Security Headers**: CSP, XSS Protection, HSTS, etc.
- ✅ **Audit Logging**: logs every sensitive operation
- ✅ **Request ID Tracking**
- ✅ **Rate limiting** (Flask-Limiter, counters in Redis): limits per route and
  setting in [`docs/api_contracts.md`](docs/api_contracts.md#rate-limit). Local
  dev uses `RATELIMIT_STORAGE_URI=redis://localhost:6380/0` (see `.env.example`);
  `docker-compose.prod.yml` runs its own `redis` service.

## 🚢 Deployment

### OpenStack (Terraform + Ansible)

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply

# Then, deploy via Ansible
ansible-playbook ansible/deploy-prod.yml
```

### Local Docker

```bash
ansible-playbook -i ansible/hosts.ini ansible/run-docker.yml
```

Containers started:
- `buska_api` - Flask API with Gunicorn (port 5000)
- `buska_scheduler` - scheduler jobs
- `buska_db_prod` - PostgreSQL + PostGIS (port 5432)
- `buska_redis` - rate limit counters

## 🐛 Troubleshooting

### Error: import errors for new utilities
```bash
# Reinstall dependencies
pip install -e "."
```

### Logs aren't in a readable format
```bash
# Readable logs are the development format: set FLASK_ENV=development in .env
echo "FLASK_ENV=development" >> .env

# Clear cache and restart
find . -type d -name "__pycache__" -exec rm -r {} +
make run
```

### Type checking errors (mypy)
```bash
# Run with less strict settings
mypy app --no-strict-optional --ignore-missing-imports
```
