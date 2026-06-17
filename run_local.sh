#!/bin/bash
#
# run_local.sh — Run the SAP AI Platform backend WITHOUT Docker.
#
# Uses native Homebrew PostgreSQL 15 (+ pgvector) and Redis instead of the
# docker-compose stack, then launches FastAPI (uvicorn) and, optionally, the
# Celery worker + beat. Everything here is plain Python/CLI — no containers.
#
# Usage:
#   ./run_local.sh            # infra + migrations + API (uvicorn) only
#   ./run_local.sh --workers  # also start Celery worker + beat in the background
#   ./run_local.sh --no-deps  # skip pip install (faster restarts)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

# ── Native service config (NOT the docker port remaps) ──────────────────────
# We use postgresql@17 because Homebrew's pgvector bottle only builds for
# @17/@18 (there is NO pgvector for @15). This machine already runs another
# Postgres on 5432, so the native @17 instance is put on 5434. Redis uses the
# Homebrew default 6379.
PG_FORMULA="postgresql@17"
PG_BIN="/opt/homebrew/opt/${PG_FORMULA}/bin"
PG_PORT=5434
PG_DB="${POSTGRES_DB:-sap_ai_platform}"
PG_USER="${POSTGRES_USER:-platform_user}"
PG_PASSWORD="${POSTGRES_PASSWORD:-mypassword123}"
REDIS_PORT=6379

START_WORKERS=false
INSTALL_DEPS=true
for arg in "$@"; do
  case "$arg" in
    --workers)  START_WORKERS=true ;;
    --no-deps)  INSTALL_DEPS=false ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

echo "🚀 Starting SAP AI Platform backend (native, no Docker)..."

# ── 1. PostgreSQL (native) ──────────────────────────────────────────────────
echo "🐘 Ensuring PostgreSQL ($PG_FORMULA) is installed and running..."
brew list "$PG_FORMULA" >/dev/null 2>&1 || brew install "$PG_FORMULA"
export PATH="$PG_BIN:$PATH"

# Pin this instance to $PG_PORT (5432 is taken by another local Postgres).
PG_CONF="/opt/homebrew/var/${PG_FORMULA}/postgresql.conf"
if [ -f "$PG_CONF" ] && ! grep -qE "^port = ${PG_PORT}\b" "$PG_CONF"; then
  echo "🔧 Setting $PG_FORMULA port to $PG_PORT..."
  /usr/bin/sed -i '' -E "s/^#?port = [0-9]+.*/port = ${PG_PORT}/" "$PG_CONF"
fi
brew services restart "$PG_FORMULA" >/dev/null

# pgvector ships as a separate formula; the app needs CREATE EXTENSION vector.
# On macOS the lib is vector.dylib. If it's absent for this formula, (re)install
# pgvector so Homebrew links the lib into $PG_FORMULA's package lib dir.
if ! ls "$(pg_config --pkglibdir)"/vector.* >/dev/null 2>&1; then
  echo "🧩 Installing pgvector for $PG_FORMULA..."
  brew list pgvector >/dev/null 2>&1 && brew reinstall pgvector || brew install pgvector
fi

# Wait for PG to accept connections.
echo "⏳ Waiting for PostgreSQL on port $PG_PORT..."
until pg_isready -h localhost -p "$PG_PORT" >/dev/null 2>&1; do sleep 1; done

# ── 2. Bootstrap role / database / extensions (idempotent) ──────────────────
# Connect as the current macOS superuser (Homebrew default) to provision.
echo "🔧 Provisioning role '$PG_USER' and database '$PG_DB'..."
psql -h localhost -p "$PG_PORT" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$PG_USER') THEN
    -- SUPERUSER mirrors the docker setup (platform_user owns that instance)
    -- and lets Alembic migrations run CREATE EXTENSION vector.
    CREATE ROLE $PG_USER LOGIN PASSWORD '$PG_PASSWORD' CREATEDB SUPERUSER;
  END IF;
END
\$\$;
SQL
psql -h localhost -p "$PG_PORT" -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname = '$PG_DB'" | grep -q 1 || \
  createdb -h localhost -p "$PG_PORT" -O "$PG_USER" "$PG_DB"

# Extensions (mirrors infra/postgres/init.sql).
psql -h localhost -p "$PG_PORT" -d "$PG_DB" -v ON_ERROR_STOP=1 <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
SQL

# ── 3. Redis (native) ───────────────────────────────────────────────────────
echo "🧰 Ensuring Redis is installed and running..."
brew list redis >/dev/null 2>&1 || brew install redis
brew services start redis >/dev/null
echo "⏳ Waiting for Redis on port $REDIS_PORT..."
until redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; do sleep 1; done

# ── 4. Connection overrides for native ports ────────────────────────────────
# .env points DATABASE_URL at 5433 (the docker mapping); native @17 is on 5434.
export POSTGRES_HOST=localhost
export POSTGRES_PORT="$PG_PORT"
export DATABASE_URL="postgresql+asyncpg://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${PG_DB}"
export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
export CELERY_BROKER_URL="redis://localhost:${REDIS_PORT}/0"
export CELERY_RESULT_BACKEND="redis://localhost:${REDIS_PORT}/0"

# ── 5. Python env + dependencies ────────────────────────────────────────────
echo "🐍 Activating virtual environment..."

if [ ! -d ".venv" ]; then
  echo "📦 Creating Python 3.13 virtual environment..."
  /opt/homebrew/bin/python3.13 -m venv .venv
fi

source .venv/bin/activate

echo "🔍 Verifying Python version..."
PYTHON_VERSION=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")

if [ "$PYTHON_VERSION" != "3.13" ]; then
  echo "❌ Python 3.13 required. Found Python $PYTHON_VERSION"
  echo "Delete .venv and recreate:"
  echo "rm -rf .venv"
  echo "/opt/homebrew/bin/python3.13 -m venv .venv"
  exit 1
fi

echo "✅ Using Python $(python --version)"

cd backend

if [ "$INSTALL_DEPS" = true ]; then
  echo "⬆️ Upgrading pip tooling..."
  pip install --upgrade pip setuptools wheel

  echo "🔧 Ensuring pyodbc is Python 3.13 compatible..."

  if grep -q "pyodbc==5.1.0" requirements.txt; then
      sed -i '' 's/pyodbc==5.1.0/pyodbc==5.2.0/g' requirements.txt
  fi

  echo "📥 Installing backend dependencies..."
  pip install -r requirements.txt
fi

# ── 6. Database migrations ──────────────────────────────────────────────────
echo "📜 Running Alembic migrations..."
alembic upgrade head

# ── 7. Celery worker + beat (optional, background) ──────────────────────────
PIDS=()
cleanup() { echo; echo "🛑 Shutting down background processes..."; for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [ "$START_WORKERS" = true ]; then
  echo "👷 Starting Celery worker (queues: default,discovery)..."
  celery -A app.worker.celery_app worker --loglevel=info -Q default,discovery &
  PIDS+=($!)
  echo "⏰ Starting Celery beat..."
  celery -A app.worker.celery_app beat --loglevel=info --scheduler redbeat.RedBeatScheduler &
  PIDS+=($!)
fi

# ── 8. FastAPI (foreground) ─────────────────────────────────────────────────
echo "✨ Starting FastAPI on http://localhost:8000 ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
