#!/bin/bash

# DSA Case OS - System Shutdown Script

echo "🛑 Stopping DSA Case OS System..."
echo "================================"

cd "$(dirname "$0")"

# Stop frontend
if [ -f frontend.pid ]; then
    FRONTEND_PID=$(cat frontend.pid)
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
        rm frontend.pid
        echo "✅ Frontend stopped"
    else
        echo "⚠️  Frontend not running"
        rm frontend.pid
    fi
else
    # Try to kill by port
    if lsof -ti:5173 > /dev/null 2>&1; then
        echo "Stopping frontend on port 5173..."
        kill $(lsof -ti:5173)
        echo "✅ Frontend stopped"
    fi
fi

# Stop backend
echo "Stopping backend containers..."
cd docker
docker-compose down
echo "✅ Backend stopped"
cd ..

echo ""
echo "================================"
echo "✨ DSA Case OS stopped successfully"
echo "================================"
