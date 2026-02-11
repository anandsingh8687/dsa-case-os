#!/bin/bash

# DSA Case OS - System Status Check

echo "🔍 DSA Case OS - System Status"
echo "================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check Docker
echo "1️⃣  Docker Status:"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}   ✅ Docker installed${NC}"

    # Check containers
    if docker ps --format "{{.Names}}" | grep -q "dsa_case_os"; then
        echo -e "${GREEN}   ✅ Backend containers running:${NC}"
        docker ps --filter "name=dsa_case_os" --format "      - {{.Names}} ({{.Status}})"
    else
        echo -e "${RED}   ❌ Backend containers not running${NC}"
        echo -e "${YELLOW}      Run: cd docker && docker-compose up -d${NC}"
    fi
else
    echo -e "${RED}   ❌ Docker not installed${NC}"
fi

echo ""

# Check Backend
echo "2️⃣  Backend Status (http://localhost:8000):"
if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ Backend is responding${NC}"
    HEALTH=$(curl -s http://localhost:8000/api/v1/health)
    echo "      Response: $HEALTH"
else
    echo -e "${RED}   ❌ Backend not responding${NC}"
    echo -e "${YELLOW}      1. Check if containers are running: docker ps${NC}"
    echo -e "${YELLOW}      2. Check logs: docker logs dsa_case_os_backend${NC}"
    echo -e "${YELLOW}      3. Restart: cd docker && docker-compose restart${NC}"
fi

echo ""

# Check Frontend
echo "3️⃣  Frontend Status (http://localhost:5173):"
if lsof -ti:5173 > /dev/null 2>&1; then
    PID=$(lsof -ti:5173)
    echo -e "${GREEN}   ✅ Frontend running (PID: $PID)${NC}"

    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo -e "${GREEN}   ✅ Frontend is responding${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Port 5173 occupied but not responding${NC}"
    fi
else
    echo -e "${RED}   ❌ Frontend not running${NC}"
    echo -e "${YELLOW}      Run: cd frontend && npm run dev${NC}"
fi

echo ""

# Check Database
echo "4️⃣  Database Status:"
if docker ps --format "{{.Names}}" | grep -q "dsa_case_os_db"; then
    echo -e "${GREEN}   ✅ Database container running${NC}"

    # Try to connect
    if docker exec dsa_case_os_db pg_isready -U postgres > /dev/null 2>&1; then
        echo -e "${GREEN}   ✅ Database accepting connections${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Database container running but not ready${NC}"
    fi
else
    echo -e "${RED}   ❌ Database container not running${NC}"
fi

echo ""

# Summary
echo "================================"
echo "📊 Quick Actions:"
echo "================================"
echo ""
echo "Start everything:    ./START_SYSTEM.sh"
echo "Stop everything:     ./STOP_SYSTEM.sh"
echo "View backend logs:   docker logs -f dsa_case_os_backend"
echo "View frontend logs:  tail -f frontend.log"
echo ""
