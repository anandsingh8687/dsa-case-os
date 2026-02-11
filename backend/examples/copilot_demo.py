"""
DSA Copilot Demo Script

Demonstrates the copilot's query classification and response generation.
This script works WITHOUT requiring database or Claude API connection.

Run: python examples/copilot_demo.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock the database imports to avoid dependency errors
import unittest.mock as mock
sys.modules['app.db.database'] = mock.MagicMock()

from app.services.stages.stage7_retriever import classify_query, QueryType


def print_header(text):
    """Print a formatted header."""
    print("\n" + "═" * 70)
    print(f"  {text}")
    print("═" * 70)


def print_query_result(query, query_type, params):
    """Print query classification result."""
    print(f"\n📝 Query: \"{query}\"")
    print(f"🎯 Type: {query_type.value.upper()}")
    if params:
        print(f"📊 Extracted Params:")
        for key, value in params.items():
            print(f"   - {key}: {value}")


def demo_query_classification():
    """Demonstrate query classification capabilities."""
    print_header("DSA Copilot - Query Classification Demo")

    test_queries = [
        # CIBIL queries
        ("Which lenders accept CIBIL score of 650?", "Tests CIBIL score detection"),
        ("lenders for 700 cibil", "Tests informal CIBIL query"),
        ("score below 680", "Tests operator detection (below)"),

        # Pincode queries
        ("who serves pincode 400001?", "Tests pincode detection"),
        ("lenders for Mumbai 110001", "Tests pincode in context"),

        # Lender-specific queries
        ("What's the policy for Bajaj Finance?", "Tests lender name detection"),
        ("Tell me about Tata Capital", "Tests informal lender query"),

        # Comparison queries
        ("Compare Bajaj Finance and IIFL", "Tests comparison detection"),
        ("Bajaj vs Tata Capital", "Tests vs comparison"),

        # Vintage queries
        ("lenders accepting 1.5 year vintage", "Tests vintage with decimals"),
        ("2 years business experience", "Tests alternative vintage phrasing"),

        # Turnover queries
        ("50 lakh annual turnover", "Tests turnover in lakhs"),
        ("2 crore revenue requirement", "Tests turnover in crores"),

        # Entity type queries
        ("proprietorship friendly lenders", "Tests entity type detection"),
        ("private limited company loans", "Tests full entity name"),

        # Requirement queries
        ("lenders with no video KYC", "Tests negative requirement"),
        ("without physical verification", "Tests alternative requirement phrasing"),
        ("lenders requiring video KYC", "Tests positive requirement"),

        # Ticket size queries
        ("max ticket 50 lakh", "Tests ticket size detection"),
        ("loan amount 25 lakh", "Tests alternative ticket phrasing"),

        # General queries
        ("Tell me about business loans", "Tests general query"),
    ]

    print("\n🔍 Testing Query Classification Engine\n")

    for i, (query, description) in enumerate(test_queries, 1):
        query_type, params = classify_query(query)
        print(f"\n[Test {i}/{len(test_queries)}] {description}")
        print_query_result(query, query_type, params)

    print("\n\n✅ Query classification demo completed!")
    print(f"   Tested {len(test_queries)} different query patterns")
    print(f"   Covered all {len(QueryType)} query types")


def demo_sql_query_mapping():
    """Show how queries map to SQL."""
    print_header("SQL Query Mapping Examples")

    examples = [
        {
            "query": "lenders for 650 CIBIL",
            "sql": """
SELECT l.lender_name, lp.product_name, lp.min_cibil_score
FROM lender_products lp
INNER JOIN lenders l ON lp.lender_id = l.id
WHERE lp.min_cibil_score <= 650
ORDER BY lp.min_cibil_score ASC
            """,
            "explanation": "Finds all lenders with minimum CIBIL requirement at or below 650"
        },
        {
            "query": "who serves pincode 400001",
            "sql": """
SELECT DISTINCT l.lender_name, lp.product_name
FROM lender_pincodes lpc
INNER JOIN lenders l ON lpc.lender_id = l.id
INNER JOIN lender_products lp ON l.id = lp.lender_id
WHERE lpc.pincode = '400001'
            """,
            "explanation": "Finds lenders that have this pincode in their serviceability list"
        },
        {
            "query": "compare Bajaj and IIFL",
            "sql": """
SELECT l.lender_name, lp.product_name, lp.min_cibil_score,
       lp.min_vintage_years, lp.max_ticket_size
FROM lender_products lp
INNER JOIN lenders l ON lp.lender_id = l.id
WHERE LOWER(l.lender_name) LIKE '%bajaj%'
   OR LOWER(l.lender_name) LIKE '%iifl%'
            """,
            "explanation": "Fetches all products from both lenders for side-by-side comparison"
        },
    ]

    for example in examples:
        print(f"\n📝 Query: \"{example['query']}\"")
        print(f"💡 {example['explanation']}")
        print(f"\n💻 Generated SQL:")
        print(example['sql'].strip())
        print("-" * 70)


def demo_response_examples():
    """Show example responses for different query types."""
    print_header("Expected Response Examples")

    responses = [
        {
            "query": "lenders for 650 CIBIL",
            "answer": """
Found 5 lender products accepting CIBIL 650 or below:

1. Bajaj Finance BL - Min CIBIL: 650, Max Ticket: ₹75L, Vintage: 2y
2. Lendingkart BL - Min CIBIL: 650, Max Ticket: ₹30L, Vintage: 1y
3. Flexiloans STBL - Min CIBIL: 650, Max Ticket: ₹25L, Vintage: 1y
4. Indifi BL - Min CIBIL: 640, Max Ticket: ₹40L, Vintage: 1y
5. IIFL BL - Min CIBIL: 675, Max Ticket: ₹50L, Vintage: 2y

All accept proprietorship and partnership. Bajaj and IIFL require
video KYC. Lendingkart and Flexiloans have faster processing.
            """,
        },
        {
            "query": "compare Bajaj Finance and IIFL",
            "answer": """
Comparison: Bajaj Finance vs IIFL

| Criteria | Bajaj Finance BL | IIFL BL |
|----------|------------------|---------|
| Min CIBIL | 650 | 675 |
| Min Vintage | 2 years | 2 years |
| Max Ticket | ₹75 Lakh | ₹50 Lakh |
| Entity Types | Prop, Partner, Pvt Ltd | All types |
| Video KYC | Required | Required |
| FI | Required | Not required |
| Pincode Coverage | 1,500+ | 1,200+ |

Key Differences:
- Bajaj accepts lower CIBIL (650 vs 675)
- Bajaj offers higher ticket size (₹75L vs ₹50L)
- IIFL doesn't require FI, faster processing
- Both need 2+ years vintage
            """,
        },
        {
            "query": "proprietorship with 1 year vintage",
            "answer": """
Found 12 lenders accepting proprietorship with 1 year vintage:

Top 5:
- Lendingkart: 1y vintage, CIBIL 650+, up to ₹30L
- Flexiloans: 1y vintage, CIBIL 650+, up to ₹25L
- NeoGrowth: 1y vintage, CIBIL 600+, up to ₹20L
- Indifi: 1y vintage, CIBIL 640+, up to ₹40L
- Capital Float: 1y vintage, CIBIL 650+, up to ₹15L

Most require:
- 12+ months bank statement
- GST registration
- Basic KYC (PAN, Aadhaar)
- Tele-PD (no field investigation for most)
            """,
        },
    ]

    for example in responses:
        print(f"\n📝 Query: \"{example['query']}\"")
        print(f"\n💬 Expected Answer:")
        print(example['answer'].strip())
        print("\n" + "-" * 70)


def demo_use_cases():
    """Show real-world use cases."""
    print_header("Real-World Use Cases for DSAs")

    use_cases = [
        {
            "scenario": "Quick Client Eligibility Check",
            "conversation": [
                ("DSA", "Client has 680 CIBIL, proprietorship, 1.5 years, Mumbai"),
                ("Copilot", "Found 6 lenders in Mumbai accepting these criteria..."),
                ("DSA", "Which ones don't require video KYC?"),
                ("Copilot", "3 lenders: Lendingkart, Capital Float, NeoGrowth"),
            ],
        },
        {
            "scenario": "Policy Verification Before Submission",
            "conversation": [
                ("DSA", "Does Bajaj Finance accept partnership firms?"),
                ("Copilot", "Yes, Bajaj Finance BL accepts partnership firms"),
                ("DSA", "What's the minimum vintage?"),
                ("Copilot", "Bajaj Finance requires 2 years minimum vintage"),
            ],
        },
        {
            "scenario": "Finding Alternative Lenders",
            "conversation": [
                ("DSA", "Client rejected by IIFL due to CIBIL 650"),
                ("Copilot", "Try these lenders accepting CIBIL 650: Bajaj, Lendingkart, Flexiloans..."),
                ("DSA", "Which one has fastest TAT?"),
                ("Copilot", "Lendingkart typically has 3-5 day TAT for CIBIL 650+"),
            ],
        },
    ]

    for i, use_case in enumerate(use_cases, 1):
        print(f"\n[Use Case {i}] {use_case['scenario']}")
        print("-" * 70)
        for speaker, message in use_case['conversation']:
            if speaker == "DSA":
                print(f"\n👤 {speaker}: {message}")
            else:
                print(f"🤖 {speaker}: {message}")
        print()


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║              DSA COPILOT DEMONSTRATION                       ║
    ║              Natural Language Lender Queries                 ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    # Run all demos
    demo_query_classification()
    demo_sql_query_mapping()
    demo_response_examples()
    demo_use_cases()

    print_header("Demo Complete!")
    print("""
    🎉 The DSA Copilot is ready to use!

    Next Steps:
    1. Ensure PostgreSQL database is running
    2. Load lender knowledge base (already done)
    3. Set ANTHROPIC_API_KEY in .env
    4. Start the FastAPI server: uvicorn app.main:app --reload
    5. Query via API: POST /api/v1/copilot/query

    For more info, see: backend/app/services/stages/COPILOT_README.md
    """)
