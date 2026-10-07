# MeBusKá Backend

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

# Full setup (venv + dependencies + database + docker)
chmod +x setup.sh start.sh
./start.sh

# To reset the database
./start.sh -e clean_database=true
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

# 3. Start the database (in another terminal)
docker compose -f infra/database.yml up -d

# 4. Seed the database
make initdb

# 5. Run the server
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
make run            # Run the server (port 5000)
make initdb         # Create and seed the database
make deletedb       # Wipe the database
make bdcon          # Connect to the database via psql
```

### Docker (Production)

```bash
make docker-build   # Build the image
make docker-up      # Bring up containers (port 5000)
make docker-down    # Stop containers
make docker-logs    # Tail logs
make docker-clean   # Clean up everything (volumes + images)
```

## 📁 Project Structure

```
mebuska-corporate/
├── app/                    # Application code
│   ├── api/
│   │   ├── controllers/    # Endpoint logic
│   │   └── routes/         # Route definitions
│   ├── core/
│   │   ├── auth.py         # JWT authentication
│   │   └── config.py       # Configuration
│   ├── models/             # SQLAlchemy models
│   └── services/           # Business logic services
├── database/               # SQL scripts
│   ├── init.sql            # Schema and extensions
│   └── populate.sql        # Seed data
├── docs/                   # API documentation
│   └── endpoints/          # YAML specs (Swagger)
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
├── start.sh                # Setup + Docker
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
DEBUG=false
JWT_SECRET_KEY=a_long_random_jwt_secret
JWT_EXPIRES_HOURS=2
```

## 📚 Documentation

### API Documentation
Full interactive API documentation is available at:
- **Swagger UI**: http://localhost:5000/docs
- **ReDoc**: http://localhost:5000/redoc

Main endpoints:
- `POST /auth/login` - Authenticate
- `POST /auth/register` - Create an account
- `GET /rotas` - List routes
- `GET /viagens` - List trips
- `GET /me` - Authenticated user's data

## 🔒 Security

The backend implements multiple layers of security:

### Authentication & Authorization
- **JWT** with configurable expiration (default: 2 hours)
- **RBAC** (Role-Based Access Control): ALUNO, MOTORISTA, GESTOR
- **Tenant isolation** per Prefeitura (municipality)

### Protections in Place
- ✅ **Security Headers**: CSP, XSS Protection, HSTS, etc.
- ✅ **Audit Logging**: logs every sensitive operation
- ✅ **Request ID Tracking**

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
./start.sh
```

Containers started:
- `buska_api` - Flask API with Gunicorn (port 5000)
- `buska_db_prod` - PostgreSQL + PostGIS (port 5432)

## 🐛 Troubleshooting

### Error: import errors for new utilities
```bash
# Reinstall dependencies
pip install -e "."
```

### Logs aren't in a readable format
```bash
# Add DEBUG=true to .env
echo "DEBUG=true" >> .env

# Clear cache and restart
find . -type d -name "__pycache__" -exec rm -r {} +
make run
```

### Type checking errors (mypy)
```bash
# Run with less strict settings
mypy app --no-strict-optional --ignore-missing-imports
```
