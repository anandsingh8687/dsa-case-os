#!/bin/bash

# DSA Case OS - Login Issue Fix Script
# This script will help diagnose and fix the login → dashboard issue

set -e

echo "🔧 DSA Case OS - Login Issue Fix"
echo "================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$(dirname "$0")"

echo -e "${BLUE}This script will:${NC}"
echo "  1. Check backend status"
echo "  2. Check frontend status"
echo "  3. Verify configurations"
echo "  4. Provide specific fix instructions"
echo ""
read -p "Press Enter to continue..."
echo ""

# Step 1: Check Backend
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Checking Backend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if docker ps --filter "name=dsa_case_os_backend" --format "{{.Names}}" | grep -q "dsa_case_os_backend"; then
    echo -e "${GREEN}✅ Backend container is running${NC}"

    if curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend API is responding${NC}"
        BACKEND_OK=true
    else
        echo -e "${RED}❌ Backend container running but API not responding${NC}"
        echo -e "${YELLOW}📝 Action: Check backend logs:${NC}"
        echo "   docker logs dsa_case_os_backend"
        BACKEND_OK=false
    fi
else
    echo -e "${RED}❌ Backend container not running${NC}"
    echo -e "${YELLOW}📝 Action: Start backend:${NC}"
    echo "   cd docker && docker-compose up -d"
    BACKEND_OK=false
fi

echo ""

# Step 2: Check Frontend
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Checking Frontend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend is running on port 5173${NC}"

    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Frontend is responding${NC}"
        FRONTEND_OK=true
    else
        echo -e "${YELLOW}⚠️  Port occupied but not responding properly${NC}"
        FRONTEND_OK=false
    fi
else
    echo -e "${RED}❌ Frontend not running${NC}"
    echo -e "${YELLOW}📝 Action: Start frontend:${NC}"
    echo "   cd frontend && npm run dev"
    FRONTEND_OK=false
fi

echo ""

# Step 3: Diagnosis
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Diagnosis & Fix"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$BACKEND_OK" = true ] && [ "$FRONTEND_OK" = true ]; then
    echo -e "${GREEN}✅ Both backend and frontend are running!${NC}"
    echo ""
    echo -e "${BLUE}🎯 To fix the login → dashboard issue:${NC}"
    echo ""
    echo "1️⃣  Clear browser cache and localStorage:"
    echo "   • Open http://localhost:5173"
    echo "   • Press F12 (DevTools)"
    echo "   • Go to Application tab"
    echo "   • Click 'Clear site data' button"
    echo "   • Refresh the page (Cmd+Shift+R or Ctrl+Shift+R)"
    echo ""
    echo "2️⃣  Test the login flow:"
    echo "   • Visit: http://localhost:5173/"
    echo "   • Click 'Sign In'"
    echo "   • Enter credentials"
    echo "   • Should redirect to dashboard"
    echo ""
    echo "3️⃣  If still not working, check browser console:"
    echo "   • Press F12 → Console tab"
    echo "   • Look for red errors"
    echo "   • Share the error message for further help"
    echo ""

    echo -e "${BLUE}🔍 Quick Test Command:${NC}"
    echo "Test login API directly:"
    echo -e "${YELLOW}curl -X POST http://localhost:8000/api/v1/auth/login \\"
    echo "  -H 'Content-Type: application/json' \\"
    echo "  -d '{\"email\":\"your@email.com\",\"password\":\"yourpassword\"}'${NC}"
    echo ""

else
    echo -e "${RED}⚠️  System is not fully running${NC}"
    echo ""

    if [ "$BACKEND_OK" != true ]; then
        echo -e "${YELLOW}❌ Backend issue detected${NC}"
        echo "   Fix: cd docker && docker-compose up -d"
        echo "   Logs: docker logs -f dsa_case_os_backend"
        echo ""
    fi

    if [ "$FRONTEND_OK" != true ]; then
        echo -e "${YELLOW}❌ Frontend issue detected${NC}"
        echo "   Fix: cd frontend && npm run dev"
        echo "   Logs: tail -f frontend.log"
        echo ""
    fi

    echo "After fixing, run this script again to verify."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✨ Use these helper scripts:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ./START_SYSTEM.sh    - Start everything"
echo "  ./CHECK_STATUS.sh    - Check system status"
echo "  ./STOP_SYSTEM.sh     - Stop everything"
echo "  Read QUICK_START.md  - Full documentation"
echo ""
