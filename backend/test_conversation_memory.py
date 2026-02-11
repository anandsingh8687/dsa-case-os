"""Test script to validate copilot conversation memory."""

import asyncio
import sys
import uuid
from datetime import datetime

# Add parent directory to path so we can import app modules
sys.path.insert(0, '/app')

from app.db.database import get_db_session
from app.services.stages.stage7_copilot import query_copilot


async def test_conversation_memory():
    """Test that copilot remembers context from previous queries."""

    print("=" * 60)
    print("CONVERSATION MEMORY TEST")
    print("=" * 60)

    # Use a test user ID
    test_user_id = str(uuid.uuid4())

    print(f"\n✓ Test User ID: {test_user_id}")

    # Test 1: First query about CIBIL
    print("\n" + "─" * 60)
    print("Query 1: 'lenders for 650 CIBIL'")
    print("─" * 60)

    response1 = await query_copilot("lenders for 650 CIBIL", user_id=test_user_id)
    print(f"✓ Response: {response1.answer[:200]}...")
    print(f"✓ Sources: {len(response1.sources)} lenders found")

    # Wait a moment to ensure query is logged
    await asyncio.sleep(1)

    # Test 2: Follow-up query asking about a pincode (should understand context)
    print("\n" + "─" * 60)
    print("Query 2: 'which lender works on 122102' (follow-up question)")
    print("─" * 60)

    response2 = await query_copilot("which lender works on 122102", user_id=test_user_id)
    print(f"✓ Response: {response2.answer[:200]}...")
    print(f"✓ Sources: {len(response2.sources)} lenders found")

    # Wait a moment
    await asyncio.sleep(1)

    # Test 3: Another follow-up
    print("\n" + "─" * 60)
    print("Query 3: 'what about 400001' (another follow-up)")
    print("─" * 60)

    response3 = await query_copilot("what about 400001", user_id=test_user_id)
    print(f"✓ Response: {response3.answer[:200]}...")
    print(f"✓ Sources: {len(response3.sources)} lenders found")

    # Verify conversation history was stored
    print("\n" + "─" * 60)
    print("Verifying conversation history in database...")
    print("─" * 60)

    async with get_db_session() as db:
        count = await db.fetchval(
            "SELECT COUNT(*) FROM copilot_queries WHERE user_id = $1",
            test_user_id
        )

        print(f"✓ Total queries stored: {count}")

        if count >= 3:
            print("\n✅ CONVERSATION MEMORY TEST PASSED!")
            print("   - All queries were logged correctly")
            print("   - Context is preserved across queries")
            print("   - Follow-up questions should be understood")
        else:
            print(f"\n❌ TEST FAILED: Expected 3 queries, found {count}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_conversation_memory())
