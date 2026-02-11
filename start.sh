#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# DSA Case OS — One-Click Startup Script
# ═══════════════════════════════════════════════════════════════

set -e

echo "🚀 Starting DSA Case OS..."
echo ""

# Navigate to project root
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please open Docker Desktop first."
    exit 1
fi

echo "✅ Docker is running"

# Create .env file for docker-compose if not exists
if [ ! -f docker/.env ]; then
    cat > docker/.env << 'ENV'
DB_USER=postgres
DB_PASSWORD=postgres
DB_NAME=dsa_case_os
SECRET_KEY=dsa-case-os-secret-key-2025
LLM_API_KEY=sk-jOZ0CdgAROEkv0b5J1hd60mDQTTi44h00XHTsyJsPBEbVlU8
LLM_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=kimi-latest
ENV
    echo "✅ Created docker/.env"
fi

# Create data directory for lender CSVs
mkdir -p backend/data

# Stop any existing containers
echo ""
echo "📦 Building and starting containers..."
cd docker
docker compose down 2>/dev/null || true
docker compose up -d --build

# Wait for PostgreSQL to be ready
echo ""
echo "⏳ Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec dsa_case_os_db pg_isready -U postgres > /dev/null 2>&1; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    sleep 2
    echo "   Waiting... ($i)"
done

# Initialize database schema
echo ""
echo "🗄️  Initializing database schema..."
docker exec -i dsa_case_os_db psql -U postgres -d dsa_case_os < ../backend/app/db/schema.sql 2>/dev/null || echo "   (Tables may already exist — that's OK)"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ DSA Case OS is RUNNING!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  🌐 API Docs (Swagger):  http://localhost:8000/docs"
echo "  🔧 Backend API:         http://localhost:8000/api/v1"
echo "  💻 Frontend:            http://localhost:3000"
echo "  🏥 Health Check:        http://localhost:8000/health"
echo ""
echo "  📋 Quick Test Flow:"
echo "     1. Open http://localhost:8000/docs"
echo "     2. POST /api/v1/auth/register → create user"
echo "     3. POST /api/v1/auth/login → get token"
echo "     4. Click 'Authorize' → paste token"
echo "     5. Start creating cases!"
echo ""
echo "  📊 To load lender data:"
echo "     Copy your CSVs to backend/data/ then run:"
echo "     docker exec -it dsa_case_os_backend python scripts/ingest_lender_data.py"
echo ""
echo "  🛑 To stop: cd docker && docker compose down"
echo "═══════════════════════════════════════════════════════════"
