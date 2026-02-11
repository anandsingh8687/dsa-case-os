#!/bin/bash

echo "🔧 Deploying WhatsApp + Copilot Fixes..."
echo ""

cd /Users/aparajitasharma/Downloads/dsa-case-os

echo "📦 Step 1: Rebuilding WhatsApp service (with Chromium)..."
docker compose -f docker/docker-compose.yml build whatsapp

echo ""
echo "🔄 Step 2: Restarting all services..."
docker compose -f docker/docker-compose.yml down backend whatsapp
docker compose -f docker/docker-compose.yml up -d backend whatsapp

echo ""
echo "⏳ Waiting 15 seconds for services to start..."
sleep 15

echo ""
echo "✅ Step 3: Checking service status..."
docker compose -f docker/docker-compose.yml ps

echo ""
echo "📋 Step 4: Checking logs..."
echo "--- Backend logs (last 15 lines) ---"
docker compose -f docker/docker-compose.yml logs backend --tail 15

echo ""
echo "--- WhatsApp logs (last 15 lines) ---"
docker compose -f docker/docker-compose.yml logs whatsapp --tail 15

echo ""
echo "🧪 Step 5: Testing WhatsApp service health..."
docker compose -f docker/docker-compose.yml exec -T backend curl -s http://whatsapp:3001/health || echo "❌ WhatsApp service not reachable"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Hard refresh browser (Cmd+Shift+R)"
echo "2. Test Copilot: Ask 'what is OD'"
echo "3. Test WhatsApp: Generate QR code in Report tab"
echo ""
