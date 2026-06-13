#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting SAP AI Platform Backend..."

# Navigate to the project root directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "$SCRIPT_DIR"

echo "📦 Starting infrastructure (PostgreSQL & Redis) via Docker..."
docker compose up -d postgres redis

echo "🐍 Activating virtual environment..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ Error: .venv folder not found in the project root!"
    echo "Please create it using 'python3 -m venv .venv' first."
    exit 1
fi

echo "📥 Checking backend dependencies..."
cd backend
pip install -r requirements.txt > /dev/null

# Docker maps Redis to port 6380 locally, so we override the .env variables temporarily for the local run
export REDIS_URL="redis://localhost:6380/0"
export CELERY_BROKER_URL="redis://localhost:6380/0"
export CELERY_RESULT_BACKEND="redis://localhost:6380/0"

echo "✨ Starting FastAPI server locally on port 8000..."
uvicorn app.main:app --reload
