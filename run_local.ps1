<#
  run_local.ps1 — Run the SAP AI Platform backend on WINDOWS without Docker.

  Windows-native equivalent of run_local.sh. Runs PostgreSQL + Redis + FastAPI
  (+ optional Celery worker/beat) using plain Python/CLI — no containers.

  PREREQUISITES (install once; Docker is NOT required):
    - PostgreSQL 17 with pgvector. Easiest: install via the EDB installer or
      `choco install postgresql17`, then add the pgvector extension. pgvector
      has no one-click Windows package — get a prebuilt DLL matching your PG
      version or build it (see https://github.com/pgvector/pgvector#windows),
      and drop vector.dll into <PG>\lib and the vector* files into <PG>\share\extension.
    - A Redis server. Native Windows Redis is unofficial — use Memurai
      (https://www.memurai.com) or `choco install memurai-developer`. Both speak
      the Redis protocol on port 6379.
    - Python 3.12 and a .venv at the project root (py -3.12 -m venv .venv).

  USAGE (from a PowerShell prompt in the project root):
    .\run_local.ps1                # infra checks + migrations + API (uvicorn)
    .\run_local.ps1 -Workers       # also start Celery worker + beat
    .\run_local.ps1 -NoDeps        # skip pip install (faster restarts)
    .\run_local.ps1 -PgPort 5434   # use a non-default Postgres port

  If you hit an execution-policy error, run once:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>

[CmdletBinding()]
param(
  [switch]$Workers,
  [switch]$NoDeps,
  [int]$PgPort = 5432,
  [int]$RedisPort = 6379,
  [string]$PgDb       = $(if ($env:POSTGRES_DB)       { $env:POSTGRES_DB }       else { "sap_ai_platform" }),
  [string]$PgUser     = $(if ($env:POSTGRES_USER)     { $env:POSTGRES_USER }     else { "platform_user" }),
  [string]$PgPassword = $(if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "mypassword123" })
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Starting SAP AI Platform backend on Windows (native, no Docker)..." -ForegroundColor Cyan

# ── 1. PostgreSQL must be reachable ─────────────────────────────────────────
# We don't manage the Windows service here (installs vary); we require psql on
# PATH and verify the server answers. Start the "postgresql-x64-17" service via
# services.msc or:  Start-Service postgresql-x64-17
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
  throw "psql not found on PATH. Install PostgreSQL 17 and add its bin\ to PATH."
}

Write-Host "Waiting for PostgreSQL on port $PgPort..."
$pgReady = $false
foreach ($i in 1..30) {
  & pg_isready -h localhost -p $PgPort *> $null
  if ($LASTEXITCODE -eq 0) { $pgReady = $true; break }
  Start-Sleep -Seconds 1
}
if (-not $pgReady) {
  throw "PostgreSQL is not accepting connections on port $PgPort. Is the postgresql service running?"
}

# ── 2. Bootstrap role / database / extensions (idempotent) ──────────────────
# Connect as the 'postgres' superuser to provision. You'll be prompted for the
# postgres password unless PGPASSWORD is set or a pgpass entry exists.
Write-Host "Provisioning role '$PgUser' and database '$PgDb'..."

$createRole = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$PgUser') THEN
    CREATE ROLE $PgUser LOGIN PASSWORD '$PgPassword' CREATEDB SUPERUSER;
  END IF;
END
`$`$;
"@
$createRole | & psql -h localhost -p $PgPort -U postgres -d postgres -v ON_ERROR_STOP=1

$dbExists = (& psql -h localhost -p $PgPort -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$PgDb'")
if ($dbExists -notmatch "1") {
  & createdb -h localhost -p $PgPort -U postgres -O $PgUser $PgDb
}

# Extensions (mirrors infra/postgres/init.sql). Requires pgvector installed.
$ext = @"
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
"@
$ext | & psql -h localhost -p $PgPort -U postgres -d $PgDb -v ON_ERROR_STOP=1

# ── 3. Redis must be reachable ──────────────────────────────────────────────
Write-Host "Waiting for Redis on port $RedisPort..."
$redisReady = $false
foreach ($i in 1..30) {
  if (Test-NetConnection -ComputerName localhost -Port $RedisPort -InformationLevel Quiet) {
    $redisReady = $true; break
  }
  Start-Sleep -Seconds 1
}
if (-not $redisReady) {
  throw "Redis (or Memurai) is not listening on port $RedisPort. Start it and retry."
}

# ── 4. Connection overrides for native ports ────────────────────────────────
$env:POSTGRES_HOST          = "localhost"
$env:POSTGRES_PORT          = "$PgPort"
$env:DATABASE_URL           = "postgresql+asyncpg://${PgUser}:${PgPassword}@localhost:${PgPort}/${PgDb}"
$env:REDIS_URL              = "redis://localhost:${RedisPort}/0"
$env:CELERY_BROKER_URL      = "redis://localhost:${RedisPort}/0"
$env:CELERY_RESULT_BACKEND  = "redis://localhost:${RedisPort}/0"

# ── 5. Python env + dependencies ────────────────────────────────────────────
Write-Host "Activating virtual environment..."
$activate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activate)) {
  throw ".venv not found. Create it with: py -3.12 -m venv .venv"
}
. $activate

Set-Location -Path (Join-Path $PSScriptRoot "backend")
if (-not $NoDeps) {
  Write-Host "Installing backend dependencies..."
  pip install -r requirements.txt | Out-Null
}

# ── 6. Database migrations ──────────────────────────────────────────────────
Write-Host "Running Alembic migrations..."
alembic upgrade head

# ── 7. Celery worker + beat (optional, separate windows) ────────────────────
if ($Workers) {
  Write-Host "Starting Celery worker + beat in new windows..."
  Start-Process powershell -ArgumentList "-NoExit","-Command",
    "Set-Location '$PWD'; . '$activate'; celery -A app.worker.celery_app worker --loglevel=info -Q default,discovery"
  Start-Process powershell -ArgumentList "-NoExit","-Command",
    "Set-Location '$PWD'; . '$activate'; celery -A app.worker.celery_app beat --loglevel=info --scheduler redbeat.RedBeatScheduler"
}

# ── 8. FastAPI (foreground) ─────────────────────────────────────────────────
Write-Host "Starting FastAPI on http://localhost:8000 ..." -ForegroundColor Green
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
