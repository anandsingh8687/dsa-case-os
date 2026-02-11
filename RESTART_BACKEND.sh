#!/bin/bash

# Restart backend container to load WhatsApp polling fix
# No rebuild needed - volume is mounted

cd "$(dirname "$0")/docker"

echo "🔄 Restarting backend container..."
docker-compose restart backend

echo ""
echo "✅ Backend restarted!"
echo ""
echo "🧪 Now test the WhatsApp flow:"
echo "   1. Refresh your browser (Cmd+Shift+R)"
echo "   2. Go to any case → Report tab"
echo "   3. Click '📱 Send to Customer'"
echo "   4. Scan QR code"
echo "   5. Should see: 'WhatsApp linked successfully!' toast"
echo "   6. Should auto-open: 'Send WhatsApp Message' modal"
echo ""
