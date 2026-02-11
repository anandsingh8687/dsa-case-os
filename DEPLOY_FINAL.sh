#!/bin/bash

echo "═══════════════════════════════════════════════════"
echo "🔧 FINAL DEPLOYMENT - Copilot + WhatsApp Fixes"
echo "═══════════════════════════════════════════════════"
echo ""

cd /Users/aparajitasharma/Downloads/dsa-case-os

echo "📦 Step 1: Rebuilding Backend (for Copilot fix)..."
echo "   - Loading .env file properly"
echo "   - Using correct Kimi model: moonshot-v1-32k"
docker compose -f docker/docker-compose.yml build backend

echo ""
echo "📦 Step 2: Rebuilding WhatsApp (for session management)..."
echo "   - Installing Chromium browser"
echo "   - Fixing session conflicts"
docker compose -f docker/docker-compose.yml build whatsapp

echo ""
echo "🛑 Step 3: Stopping all services..."
docker compose -f docker/docker-compose.yml down

echo ""
echo "🚀 Step 4: Starting services with new builds..."
docker compose -f docker/docker-compose.yml up -d

echo ""
echo "⏳ Waiting 20 seconds for services to fully start..."
sleep 20

echo ""
echo "✅ Step 5: Verifying services..."
docker compose -f docker/docker-compose.yml ps

echo ""
echo "📋 Step 6: Checking Backend logs..."
docker compose -f docker/docker-compose.yml logs backend --tail 15

echo ""
echo "📋 Step 7: Checking WhatsApp logs..."
docker compose -f docker/docker-compose.yml logs whatsapp --tail 15

echo ""
echo "🧪 Step 8: Testing service connectivity..."
echo "--- Backend can reach WhatsApp? ---"
docker compose -f docker/docker-compose.yml exec -T backend curl -s http://whatsapp:3001/health || echo "❌ Failed"

echo ""
echo "🔍 Step 9: Checking environment variables..."
echo "--- Backend LLM configuration ---"
docker compose -f docker/docker-compose.yml exec -T backend env | grep "LLM_" || echo "❌ LLM vars not set"

echo ""
echo "═══════════════════════════════════════════════════"
echo "✅ DEPLOYMENT COMPLETE!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "🎯 NEXT STEPS:"
echo ""
echo "1. Open browser: http://localhost:8000"
echo "2. Hard refresh (Cmd+Shift+R) to clear cache"
echo ""
echo "📝 TEST COPILOT:"
echo "   → Go to 'Lender Copilot' page"
echo "   → Ask: 'what is OD'"
echo "   → Expected: Full explanation (NOT error message)"
echo ""
echo "📝 TEST WHATSAPP:"
echo "   → Go to any case → Report tab"
echo "   → Click '📱 Send to Customer'"
echo "   → Expected: QR code appears in 5-10 seconds"
echo "   → Scan with WhatsApp mobile app"
echo "   → Expected: 'WhatsApp Linked Successfully!'"
echo ""
echo "═══════════════════════════════════════════════════"
echo ""
