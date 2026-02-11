#!/bin/bash

echo "🔄 Restarting backend with WhatsApp summary changes..."
cd docker
docker-compose restart backend

echo ""
echo "⏳ Waiting 15 seconds for backend to fully restart..."
sleep 15

echo ""
echo "✅ Backend restarted!"
echo ""
echo "📝 NOW DO THIS:"
echo ""
echo "1. Refresh your browser: Cmd+Shift+R"
echo "2. Go to the case (VANASHREE ASSOCIATES)"
echo "3. Click 'Generate Report' button"
echo "4. Wait for report generation to complete"
echo "5. Scroll down - you should see 'WhatsApp Share' section"
echo "   with comprehensive message including:"
echo "   • Strengths"
echo "   • Risk Flags"
echo "   • Submission Strategy"
echo "   • Top 5 Lender Matches"
echo "   • Missing Documents"
echo ""
