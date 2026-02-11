#!/bin/bash

# DSA Case OS - Complete System Startup Script
# This script ensures both backend and frontend are running

set -e

echo "🚀 Starting DSA Case OS System..."
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Navigate to project root
cd "$(dirname "$0")"

# Step 1: Check and start Docker containers (backend + database)
echo ""
echo "📦 Step 1: Starting Backend & Database..."
echo "-------------------------------------------"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
    exit 1
fi

cd docker
docker-compose up -d
echo -e "${GREEN}✅ Backend containers started${NC}"
cd ..

# Step 2: Wait for backend to be ready
echo ""
echo "⏳ Step 2: Waiting for backend to be ready..."
echo "-------------------------------------------"

max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo "Attempt $attempt/$max_attempts - waiting for backend..."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "${YELLOW}⚠️  Backend health check timeout, but continuing...${NC}"
fi

# Step 3: Start Frontend
echo ""
echo "🎨 Step 3: Starting Frontend..."
echo "-------------------------------------------"

cd frontend

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Check if frontend is already running
if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Frontend already running on port 5173${NC}"
else
    echo "Starting frontend development server..."
    npm run dev > ../frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > ../frontend.pid
    echo -e "${GREEN}✅ Frontend started (PID: $FRONTEND_PID)${NC}"
fi

cd ..

# Step 4: Display status
echo ""
echo "================================"
echo "✨ DSA Case OS is now running!"
echo "================================"
echo ""
echo "📍 Access points:"
echo "   🌐 Frontend:  http://localhost:5173"
echo "   🔧 Backend:   http://localhost:8000"
echo "   📊 API Docs:  http://localhost:8000/docs"
echo ""
echo "📝 Logs:"
echo "   Frontend: tail -f frontend.log"
echo "   Backend:  docker logs -f dsa_case_os_backend"
echo ""
echo "🛑 To stop:"
echo "   Frontend: kill \$(cat frontend.pid) or ./STOP_SYSTEM.sh"
echo "   Backend:  cd docker && docker-compose down"
echo ""
