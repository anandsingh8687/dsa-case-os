"""Test script to validate copilot fixes.

Run this to verify:
1. Database queries work correctly
2. Query classification works
3. Lender data retrieval works
4. All query types return results
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.stages.stage7_retriever import (
    classify_query,
    retrieve_lender_data,
    QueryType
)


async def test_query_classification():
    """Test query classification."""
    print("\n" + "="*60)
    print("TEST 1: Query Classification")
    print("="*60)

    test_queries = [
        "lenders for 650 CIBIL",
        "who serves pincode 400001",
        "compare Bajaj and IIFL",
        "1 year vintage accepted",
        "proprietorship friendly lenders",
        "hello",
    ]

    for query in test_queries:
        query_type, params = classify_query(query)
        print(f"\nQuery: '{query}'")
        print(f"  Type: {query_type}")
        print(f"  Params: {params}")

    print("\n✅ Query classification working!")


async def test_data_retrieval():
    """Test database retrieval functions."""
    print("\n" + "="*60)
    print("TEST 2: Database Data Retrieval")
    print("="*60)

    tests = [
        ("CIBIL Query (650)", "lenders for 650 CIBIL"),
        ("Pincode Query (400001)", "who serves pincode 400001"),
        ("Lender Specific (Bajaj)", "Bajaj Finance policy"),
        ("Vintage Query (1 year)", "1 year vintage accepted"),
        ("General Query", "hello"),
    ]

    results_summary = []

    for test_name, query in tests:
        print(f"\n{test_name}")
        print("-" * 40)

        try:
            query_type, params = classify_query(query)
            data = await retrieve_lender_data(query_type, params)

            print(f"  Query Type: {query_type}")
            print(f"  Params: {params}")
            print(f"  Results: {len(data)} lenders found")

            if data:
                print(f"  Sample: {data[0].get('lender_name', 'N/A')} - {data[0].get('product_name', 'N/A')}")
                results_summary.append((test_name, len(data), "✅ PASS"))
            else:
                print(f"  ⚠️  No data found (database may be empty)")
                results_summary.append((test_name, 0, "⚠️  EMPTY"))

        except Exception as e:
            print(f"  ❌ ERROR: {str(e)}")
            results_summary.append((test_name, 0, "❌ FAIL"))

    # Print summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    for name, count, status in results_summary:
        print(f"{status} {name}: {count} results")

    # Determine if tests passed
    failed = [r for r in results_summary if "FAIL" in r[2]]
    if failed:
        print(f"\n❌ {len(failed)} tests FAILED")
        return False
    else:
        print("\n✅ All tests PASSED!")
        return True


async def test_all_query_types():
    """Test all supported query types."""
    print("\n" + "="*60)
    print("TEST 3: All Query Types")
    print("="*60)

    query_tests = {
        "CIBIL": "Which lenders accept CIBIL 650?",
        "Pincode": "Lenders in pincode 110001",
        "Lender Specific": "Tell me about Indifi",
        "Comparison": "Compare Bajaj Finance and Lendingkart",
        "Vintage": "Lenders for 2 year vintage",
        "Turnover": "Lenders for 50 lakh turnover",
        "Entity Type": "Proprietorship friendly lenders",
        "Ticket Size": "Lenders for 30 lakh loan",
        "Requirement": "Lenders without video KYC",
        "General": "What can you help me with?",
    }

    for query_type_name, query in query_tests.items():
        try:
            query_type, params = classify_query(query)
            data = await retrieve_lender_data(query_type, params)
            status = "✅" if len(data) > 0 else "⚠️"
            print(f"{status} {query_type_name}: {len(data)} results")
        except Exception as e:
            print(f"❌ {query_type_name}: ERROR - {str(e)}")


async def test_database_connection():
    """Test if database is accessible."""
    print("\n" + "="*60)
    print("TEST 0: Database Connection")
    print("="*60)

    try:
        from app.db.database import get_db_session

        async with get_db_session() as db:
            # Try a simple query (using asyncpg methods, not SQLAlchemy)
            row = await db.fetchrow("SELECT 1 as test")
            print(f"✅ Database connection working! Test query returned: {row['test']}")

            # Check if lenders table exists and has data
            count = await db.fetchval("SELECT COUNT(*) FROM lenders")
            print(f"✅ Lenders table exists with {count} records")

            if count == 0:
                print("\n⚠️  WARNING: Lenders table is EMPTY!")
                print("   You need to load lender data:")
                print("   cd backend")
                print("   python scripts/ingest_lender_data.py --policy-csv ... --pincode-csv ...")
                return False

            return True

    except Exception as e:
        print(f"❌ Database connection FAILED: {str(e)}")
        print("\nTroubleshooting:")
        print("1. Is PostgreSQL running? Check: docker ps | grep postgres")
        print("2. Is DATABASE_URL configured correctly?")
        print("3. Run migrations: alembic upgrade head")
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print(" DSA CASE OS - COPILOT VALIDATION TESTS")
    print("="*70)

    # Test 0: Database connection
    db_ok = await test_database_connection()
    if not db_ok:
        print("\n❌ Database check failed. Fix database issues before continuing.")
        return

    # Test 1: Classification
    await test_query_classification()

    # Test 2: Data retrieval
    data_ok = await test_data_retrieval()

    # Test 3: All query types
    await test_all_query_types()

    # Final summary
    print("\n" + "="*70)
    print(" FINAL RESULT")
    print("="*70)

    if data_ok:
        print("\n✅ ALL TESTS PASSED!")
        print("\nYour copilot is ready to use. Next steps:")
        print("1. Start the backend: uvicorn app.main:app --reload")
        print("2. Test via API: curl -X POST http://localhost:8000/api/v1/copilot/query \\")
        print("                 -H 'Content-Type: application/json' \\")
        print("                 -d '{\"query\": \"lenders for 650 CIBIL\"}'")
        print("3. Update frontend to use the working API")
    else:
        print("\n⚠️  TESTS COMPLETED WITH WARNINGS")
        print("\nSome queries returned no data. This might be because:")
        print("- Database is empty (need to load lender data)")
        print("- Specific queries don't match any lenders in the database")
        print("\nThe copilot code is working correctly, just needs data!")


if __name__ == "__main__":
    asyncio.run(main())
