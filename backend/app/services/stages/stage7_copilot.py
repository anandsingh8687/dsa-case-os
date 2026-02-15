"""Stage 7: Copilot Service

Natural language interface for DSAs to query the lender knowledge base.

Flow:
1. Receive natural language query
2. Classify query type and extract parameters
3. Retrieve relevant lender data from database
4. Build Kimi 2.5 API prompt with retrieved data as context
5. Call Kimi API to generate natural language response
6. Return answer with sources and log query

Uses Kimi 2.5 (Moonshot AI) via OpenAI-compatible API.
"""

import logging
import json
import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.shared import CopilotResponse
from app.services.stages.stage7_retriever import (
    classify_query,
    retrieve_lender_data,
    QueryType
)
from app.db.database import get_db_session

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# COPILOT SERVICE
# ═══════════════════════════════════════════════════════════════

async def query_copilot(query: str, user_id: Optional[str] = None) -> CopilotResponse:
    """Process a natural language query and return an answer.

    Args:
        query: Natural language query from DSA
        user_id: Optional user ID for logging

    Returns:
        CopilotResponse with answer, sources, and response time
    """
    start_time = time.time()

    try:
        # Step 1: Classify query and extract parameters
        query_type, params = classify_query(query)
        logger.info(f"Query classified as {query_type} with params: {params}")

        # Step 2: Retrieve relevant lender data (skip for KNOWLEDGE queries)
        lender_data = []
        if query_type == QueryType.KNOWLEDGE:
            logger.info("Knowledge query detected - skipping database retrieval, using LLM knowledge directly")
        else:
            lender_data = await retrieve_lender_data(query_type, params)
            logger.info(f"Retrieved {len(lender_data)} lender records")

        # Step 3: Build LLM prompt and get response (with conversation memory)
        answer = await _generate_answer(query, query_type, params, lender_data, user_id)

        # Step 4: Build sources list
        sources = _build_sources(lender_data, query_type)

        # Step 5: Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Step 6: Log the query
        await _log_query(
            query=query,
            query_type=query_type.value,
            params=params,
            answer=answer,
            sources_count=len(sources),
            response_time_ms=response_time_ms,
            user_id=user_id
        )

        return CopilotResponse(
            answer=answer,
            sources=sources,
            response_time_ms=response_time_ms
        )

    except Exception as e:
        logger.error(f"Error processing copilot query: {e}", exc_info=True)
        response_time_ms = int((time.time() - start_time) * 1000)

        return CopilotResponse(
            answer=f"I encountered an error processing your query: {str(e)}. Please try rephrasing your question.",
            sources=[],
            response_time_ms=response_time_ms
        )


# ═══════════════════════════════════════════════════════════════
# CONVERSATION MEMORY
# ═══════════════════════════════════════════════════════════════

async def _get_copilot_table_columns(db) -> Set[str]:
    """Return available columns in copilot_queries table for schema compatibility."""
    rows = await db.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'copilot_queries'
        """
    )
    return {row["column_name"] for row in rows}

async def _get_conversation_history(user_id: Optional[str]) -> List[Dict[str, str]]:
    """Retrieve recent conversation history for a user.

    Args:
        user_id: User ID to fetch history for

    Returns:
        List of conversation turns with query and response
    """
    if not user_id:
        return []

    try:
        async with get_db_session() as db:
            columns = await _get_copilot_table_columns(db)
            query_col = "query_text" if "query_text" in columns else "user_query" if "user_query" in columns else None
            response_col = "response_text" if "response_text" in columns else "ai_response" if "ai_response" in columns else None
            response_expr = f"cq.{response_col}" if response_col else "NULL"

            if not query_col:
                return []

            if "user_id" in columns:
                rows = await db.fetch(
                    f"""
                    SELECT cq.{query_col} AS query_value, {response_expr} AS response_value, cq.created_at
                    FROM copilot_queries cq
                    WHERE cq.user_id = $1::uuid
                    ORDER BY cq.created_at DESC
                    LIMIT 10
                    """,
                    user_id
                )
            elif "case_id" in columns:
                # Legacy schema fallback: infer user scope through cases table.
                rows = await db.fetch(
                    f"""
                    SELECT cq.{query_col} AS query_value, {response_expr} AS response_value, cq.created_at
                    FROM copilot_queries cq
                    INNER JOIN cases c ON c.id = cq.case_id
                    WHERE c.user_id = $1::uuid
                    ORDER BY cq.created_at DESC
                    LIMIT 10
                    """,
                    user_id
                )
            else:
                rows = await db.fetch(
                    f"""
                    SELECT cq.{query_col} AS query_value, {response_expr} AS response_value, cq.created_at
                    FROM copilot_queries cq
                    ORDER BY cq.created_at DESC
                    LIMIT 10
                    """
                )

            # Convert to conversation format (reverse to get chronological order)
            history = []
            for row in reversed(rows):
                if not row["query_value"]:
                    continue
                history.append({
                    "query": row["query_value"],
                    "response": row["response_value"] or ""
                })

            return history

    except Exception as e:
        logger.error(f"Failed to fetch conversation history: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# KIMI 2.5 API INTEGRATION (Moonshot AI - OpenAI compatible)
# ═══════════════════════════════════════════════════════════════

async def _generate_answer(
    query: str,
    query_type: QueryType,
    params: Dict[str, Any],
    lender_data: List[Dict[str, Any]],
    user_id: Optional[str] = None
) -> str:
    """Generate a natural language answer using Kimi 2.5 API.

    Kimi 2.5 by Moonshot AI uses an OpenAI-compatible API format.
    Base URL: https://api.moonshot.cn/v1

    Args:
        query: Original user query
        query_type: Classified query type
        params: Extracted parameters
        lender_data: Retrieved lender data
        user_id: Optional user ID for conversation history

    Returns:
        Natural language answer
    """
    # Check if API key is configured
    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, using fallback responses")
        return _generate_fallback_answer(query_type, params, lender_data)

    # Fetch conversation history for context
    conversation_history = await _get_conversation_history(user_id) if user_id else []

    # Build the prompt
    prompt = _build_llm_prompt(query, query_type, params, lender_data)

    try:
        # Initialize Kimi client (OpenAI-compatible)
        client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )

        # Build messages array with conversation history
        messages = [
            {
                "role": "system",
                "content": _get_system_prompt()
            }
        ]

        # Add previous conversation turns (limit to last 5 exchanges to keep context manageable)
        for turn in conversation_history[-5:]:
            messages.append({
                "role": "user",
                "content": turn["query"]
            })
            messages.append({
                "role": "assistant",
                "content": turn["response"]
            })

        # Add current query
        messages.append({
            "role": "user",
            "content": prompt
        })

        # Call Kimi 2.5 API
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            max_tokens=1024,
            temperature=1.0,
            messages=messages
        )

        # Extract the answer from the response
        answer = response.choices[0].message.content

        # Validate completeness: Check if all lenders are mentioned
        if lender_data and len(lender_data) >= 5:
            answer = _validate_and_append_missing_lenders(answer, lender_data)

        return answer

    except Exception as e:
        logger.error(f"Error calling Kimi API: {e}", exc_info=True)
        return _generate_fallback_answer(query_type, params, lender_data)


def _get_system_prompt() -> str:
    """Get the system prompt for the hybrid copilot."""
    return """You are "Lender Copilot" — an expert AI assistant for Business Loan DSAs (Direct Sales Agents) in India.

You have COMPREHENSIVE knowledge of the Indian lending ecosystem and can answer ANY loan-related question.

═══════════════════════════════════════════════════
CORE EXPERTISE AREAS:
═══════════════════════════════════════════════════

1. **LENDERS & PRODUCTS**
   Major NBFCs: Bajaj Finance, Tata Capital, IIFL Finance, Indifi, Protium, Lendingkart, Flexiloans,
   Credit Saison, Clix Capital, Arthmate, Godrej Capital, Poonawalla, NeoGrowth, UGRO Capital,
   ABFL (Aditya Birla), L&T Finance, Kredit Bee, Fibe, LoanTap, Ambit, InCred, MAS Financial

   Banks: HDFC, ICICI, Axis, Yes Bank, Kotak, IndusInd, SBI, PNB, Bank of Baroda

   Fintech: KreditBee, PaySense, MoneyTap, EarlySalary, CASHe

2. **LOAN PRODUCTS & TERMINOLOGY**
   - **OD (Overdraft)**: Revolving credit facility where you can withdraw/repay flexibly up to a limit.
     Interest charged only on used amount. Popular for working capital needs.

   - **CC (Cash Credit)**: Similar to OD but secured against inventory/receivables. Commonly used by traders.

   - **Term Loan**: Fixed loan amount with fixed EMI tenure (1-5 years). Used for capex, expansion, equipment.

   - **Working Capital Loan**: Short-term funding for day-to-day operations - inventory, payroll, expenses.

   - **Gold Loan**: Secured loan against gold jewelry. Quick disbursal, lower rates.
     Major players: IIFL Gold, Muthoot, Manappuram, HDFC Bank

   - **Property Loan / LAP**: Loan against property (residential/commercial).
     LTV typically 50-65%, tenure up to 15 years

   - **Invoice Financing**: Loan against unpaid invoices/receivables. Quick liquidity for B2B businesses.

   - **Equipment Finance**: Loan for machinery/equipment purchase. Asset acts as collateral.

3. **ELIGIBILITY CRITERIA**
   - **CIBIL Score**: 600-650 (subprime), 650-700 (fair), 700-750 (good), 750+ (excellent)
   - **Business Vintage**: 0.5y (new fintech), 1y (standard), 2-3y (traditional lenders)
   - **Annual Turnover**: ₹5L-10L (micro), ₹10L-50L (small), ₹50L-5Cr (medium)
   - **Entity Types**: Proprietorship (easiest), Partnership, Pvt Ltd, LLP, OPC
   - **Age**: 21-65 years typically
   - **Pincode**: Metro (most coverage), Tier 2 (good), Tier 3 (limited)

4. **FINANCIAL RATIOS & METRICS**
   - **FOIR (Fixed Obligation to Income Ratio)**: Total EMIs / Monthly income. Should be <50%
   - **DSCR (Debt Service Coverage Ratio)**: Operating income / Debt obligations. Should be >1.25
   - **LTV (Loan to Value)**: Loan amount / Asset value. Property: 50-65%, Gold: 75%
   - **ROI (Rate of Interest)**: 12-18% (good credit), 18-24% (fair), 24-36% (subprime)
   - **ABB (Average Banking Balance)**: Minimum balance maintained. Often 10% of loan amount

5. **VERIFICATION PROCESSES**
   - **Video KYC**: Remote verification via video call. Instant, no branch visit
   - **FI (Field Investigation)**: Physical visit to business/home by agent
   - **Tele PD (Telephonic Personal Discussion)**: Phone-based verification
   - **Bank Statement Analysis**: 6-12 months statements to assess cash flow
   - **GST Returns**: 12-24 months GST filings for turnover verification
   - **ITR (Income Tax Returns)**: 2-3 years ITR for income assessment

6. **DOCUMENTATION**
   - **KYC**: Aadhaar, PAN, voter ID, passport
   - **Business Proof**: GST certificate, Shop Act, Udyam registration, Partnership deed
   - **Financial**: Bank statements (6-12m), GST returns, ITR, Balance sheet, P&L
   - **Address Proof**: Utility bills, rental agreement, property documents
   - **Additional**: Existing loan statements, CIBIL report, Photos/videos of business

7. **COMMON TERMS EXPLAINED**
   - **DPD (Days Past Due)**: Overdue days on existing loans. 0 DPD = good, 30+ DPD = concern, 90+ DPD = NPA
   - **NPA (Non-Performing Asset)**: Loan with 90+ days overdue
   - **Enquiry**: Credit check by lender on CIBIL. Multiple enquiries (6+ in 6m) = red flag
   - **Sanction**: Loan approval letter with amount, rate, terms
   - **Disbursal**: Actual fund transfer to borrower account
   - **Processing Fee**: Upfront fee charged by lender (1-3% of loan amount)
   - **Prepayment**: Paying off loan before tenure ends. Some lenders charge 2-5% penalty
   - **Moratorium**: Interest-only period (3-6m) before EMI starts. Common for new businesses
   - **Collateral**: Asset pledged as security (property, gold, equipment)
   - **Guarantor**: Person who guarantees loan repayment if borrower defaults

═══════════════════════════════════════════════════
RESPONSE GUIDELINES:
═══════════════════════════════════════════════════

1. **CONVERSATION MEMORY**: You have access to previous conversation turns. Use them for context.
   - Follow-up questions refer to previous context
   - Maintain continuity across the conversation

2. **DATABASE vs GENERAL KNOWLEDGE**:
   - When DATABASE RESULTS are provided → Use them as authoritative source
   - When NO database results → Use your general knowledge to help
   - For KNOWLEDGE queries (definitions, explanations) → Answer directly with your expertise

3. **RESPONSE STYLE**:
   - Be conversational and helpful like ChatGPT
   - Use Indian terminology: Lakhs/Crores, ₹ symbol, CIBIL (not credit score)
   - Keep answers concise but comprehensive (3-8 sentences)
   - Use bullet points for lists
   - Provide examples when helpful

4. **HANDLING DIFFERENT QUERY TYPES**:
   - Definitions ("what is OD"): Explain clearly with examples
   - Comparisons ("OD vs Term Loan"): List key differences
   - Recommendations ("best for 650 CIBIL"): Suggest 3-5 options with reasoning
   - General questions ("does HDFC give gold loans"): Answer with what you know
   - Specific criteria ("which lenders for X"): Use database results if available

5. **ACCURACY & HONESTY**:
   - If unsure about exact numbers, say "typically" or "approximately"
   - For rapidly changing info (interest rates), mention they vary
   - If you don't know something, admit it and suggest alternatives

Be professional, knowledgeable, and genuinely helpful. Think of yourself as a senior lending consultant."""


def _build_llm_prompt(
    query: str,
    query_type: QueryType,
    params: Dict[str, Any],
    lender_data: List[Dict[str, Any]]
) -> str:
    """Build the hybrid prompt combining DB data + general context."""

    prompt_parts = []

    # KNOWLEDGE queries: Direct question answering
    if query_type == QueryType.KNOWLEDGE:
        prompt_parts.append(f"USER QUESTION: {query}")
        prompt_parts.append("\nThis is a KNOWLEDGE question. Answer directly using your expertise on Indian business loans.")
        prompt_parts.append("Provide a clear, comprehensive explanation with examples where helpful.")
        prompt_parts.append("Use Indian terminology (Lakhs, Crores, CIBIL) and be conversational.")
        return "\n".join(prompt_parts)

    # DATABASE queries: Use DB results if available
    if lender_data:
        lender_json = json.dumps(lender_data, indent=2, default=str)
        prompt_parts.append(f"DATABASE RESULTS ({len(lender_data)} records found):")
        prompt_parts.append(f"Query Type: {query_type.value}")
        prompt_parts.append(f"Parameters: {json.dumps(params)}")
        prompt_parts.append(f"\nLENDER DATA:\n{lender_json}")
        prompt_parts.append("\n⚠️ CRITICAL: Use the above database results to answer accurately.")
        prompt_parts.append("⚠️ LIST ALL MATCHING LENDERS. Do not truncate or summarize - mention EVERY lender from the results.")
        prompt_parts.append(f"⚠️ There are {len(lender_data)} total results - your answer MUST mention all of them.")
    else:
        # No database results - use general knowledge
        prompt_parts.append("DATABASE RESULTS: No matching records found in the database.")
        if query_type.value != "general":
            prompt_parts.append(f"Query was classified as: {query_type.value} with params: {json.dumps(params)}")
        prompt_parts.append("\nSince no database records matched, use your general knowledge of Indian business loans to provide a helpful answer.")
        prompt_parts.append("Name specific lenders that typically match these criteria.")
        prompt_parts.append("Mention that these are general guidelines and actual policies may vary by lender.")

    prompt_parts.append(f"\nUSER QUESTION: {query}")
    prompt_parts.append("\nProvide a clear, actionable answer. Be specific with lender names and approximate numbers.")

    return "\n".join(prompt_parts)


def _validate_and_append_missing_lenders(answer: str, lender_data: List[Dict[str, Any]]) -> str:
    """Validate that the answer mentions most lenders and append missing ones if needed.

    Args:
        answer: The LLM-generated answer
        lender_data: The complete list of lender data from database

    Returns:
        The answer, potentially with appended summary of missing lenders
    """
    # Extract unique lender names from database results
    all_lender_names = list(set([ld.get('lender_name') for ld in lender_data if ld.get('lender_name')]))
    total_lenders = len(all_lender_names)

    # Count how many lenders are mentioned in the answer
    mentioned_count = sum(1 for lender in all_lender_names if lender.lower() in answer.lower())

    # Calculate coverage percentage
    coverage = (mentioned_count / total_lenders * 100) if total_lenders > 0 else 100

    # If coverage is less than 80%, append a complete list
    if coverage < 80:
        missing_lenders = [lender for lender in all_lender_names if lender.lower() not in answer.lower()]

        if missing_lenders:
            # Group by lender to avoid duplicate products
            lender_summary = {}
            for ld in lender_data:
                lender_name = ld.get('lender_name')
                if lender_name and lender_name in missing_lenders:
                    if lender_name not in lender_summary:
                        lender_summary[lender_name] = {
                            'products': [],
                            'min_cibil': ld.get('min_cibil_score'),
                            'min_vintage': ld.get('min_vintage_years'),
                        }
                    product_name = ld.get('product_name')
                    if product_name:
                        lender_summary[lender_name]['products'].append(product_name)

            # Build the complete list summary
            answer += f"\n\n📋 **Complete List (All {total_lenders} Matching Lenders):**\n"

            # Add lenders already mentioned in narrative
            for lender in all_lender_names:
                if lender.lower() in answer.lower():
                    answer += f"• {lender} (mentioned above)\n"

            # Add missing lenders with details
            for lender_name, info in lender_summary.items():
                products_str = ", ".join(info['products'][:2])  # Show up to 2 products
                if len(info['products']) > 2:
                    products_str += f" (+{len(info['products']) - 2} more)"

                details = []
                if info['min_cibil']:
                    details.append(f"CIBIL {info['min_cibil']}+")
                if info['min_vintage']:
                    details.append(f"{info['min_vintage']}y vintage")

                details_str = f" [{', '.join(details)}]" if details else ""
                answer += f"• {lender_name} - {products_str}{details_str}\n"

    return answer


# ═══════════════════════════════════════════════════════════════
# FALLBACK RESPONSE (when LLM API unavailable)
# ═══════════════════════════════════════════════════════════════

def _generate_fallback_answer(
    query_type: QueryType,
    params: Dict[str, Any],
    lender_data: List[Dict[str, Any]]
) -> str:
    """Generate a basic answer when LLM API is unavailable.

    Args:
        query_type: Classified query type
        params: Extracted parameters
        lender_data: Retrieved lender data

    Returns:
        Basic text answer
    """
    if not lender_data:
        if query_type == QueryType.KNOWLEDGE:
            return ("I'm your Lender Copilot, but I need the LLM service to answer detailed knowledge questions. "
                    "Please check that the LLM API is configured properly. "
                    "In the meantime, I can still help you find matching lenders for specific criteria.")

        if query_type == QueryType.GENERAL:
            return ("Hi! I'm your Lender Copilot. I can help you with:\n"
                    "• Finding lenders for specific criteria (CIBIL, pincode, vintage)\n"
                    "• Explaining loan concepts (OD, CC, FOIR, DSCR)\n"
                    "• Comparing lenders and products\n"
                    "• Answering questions about lending requirements\n\n"
                    "Try asking: 'What is OD?', 'Which lenders for 650 CIBIL?', 'Does HDFC give gold loans?'")

        return (f"No lenders found matching your {query_type.value} criteria. "
                "The lender database may still be loading. Please try again in a moment, "
                "or try broadening your search (e.g., higher CIBIL score, different pincode).")

    count = len(lender_data)

    if query_type == QueryType.CIBIL:
        cibil = params.get('cibil_score')
        lender_names = list(set([ld.get('lender_name') for ld in lender_data[:5]]))
        return f"Found {count} lender products accepting CIBIL score of {cibil} or below. Top lenders: {', '.join(lender_names[:5])}."

    elif query_type == QueryType.PINCODE:
        pincode = params.get('pincode')
        lender_names = list(set([ld.get('lender_name') for ld in lender_data[:5]]))
        return f"Found {count} lender products serving pincode {pincode}. Lenders include: {', '.join(lender_names[:5])}."

    elif query_type == QueryType.LENDER_SPECIFIC:
        lender = lender_data[0].get('lender_name')
        products = [ld.get('product_name') for ld in lender_data]
        return f"{lender} offers {len(products)} products: {', '.join(products)}. Check the sources below for detailed requirements."

    elif query_type == QueryType.COMPARISON:
        lenders = list(set([ld.get('lender_name') for ld in lender_data]))
        return f"Comparing {len(lenders)} lenders across {count} products. Key differences include CIBIL requirements, ticket sizes, and verification methods. See sources for details."

    else:
        lender_names = list(set([ld.get('lender_name') for ld in lender_data[:5]]))
        return f"Found {count} relevant lender products. Top matches: {', '.join(lender_names[:5])}. See sources for detailed requirements."


# ═══════════════════════════════════════════════════════════════
# SOURCE FORMATTING
# ═══════════════════════════════════════════════════════════════

def _build_sources(
    lender_data: List[Dict[str, Any]],
    query_type: QueryType
) -> List[Dict[str, Any]]:
    """Build sources list from lender data.

    Args:
        lender_data: Retrieved lender data
        query_type: Type of query

    Returns:
        List of source dictionaries with lender info
    """
    sources = []

    for data in lender_data[:10]:  # Limit to top 10 sources
        source = {
            "lender_name": data.get('lender_name'),
            "product_name": data.get('product_name'),
        }

        # Add relevant fields based on what's available
        if data.get('min_cibil_score'):
            source['min_cibil'] = data.get('min_cibil_score')

        if data.get('min_vintage_years'):
            source['min_vintage'] = f"{data.get('min_vintage_years')}y"

        if data.get('min_turnover_annual'):
            source['min_turnover'] = f"₹{data.get('min_turnover_annual')}L"

        if data.get('max_ticket_size'):
            source['max_ticket'] = f"₹{data.get('max_ticket_size')}L"

        if data.get('pincode_coverage'):
            source['pincode_coverage'] = data.get('pincode_coverage')

        # Add entity types if available
        if data.get('eligible_entity_types'):
            entity_types = data.get('eligible_entity_types')
            if isinstance(entity_types, list):
                source['entity_types'] = entity_types
            elif isinstance(entity_types, str):
                try:
                    source['entity_types'] = json.loads(entity_types)
                except:
                    source['entity_types'] = [entity_types]

        sources.append(source)

    return sources


# ═══════════════════════════════════════════════════════════════
# QUERY LOGGING
# ═══════════════════════════════════════════════════════════════

async def _log_query(
    query: str,
    query_type: str,
    params: Dict[str, Any],
    answer: str,
    sources_count: int,
    response_time_ms: int,
    user_id: Optional[str] = None
) -> None:
    """Log the copilot query to the database.

    Args:
        query: Original query text
        query_type: Classified query type
        params: Extracted parameters
        answer: Generated answer
        sources_count: Number of sources returned
        response_time_ms: Response time in milliseconds
        user_id: Optional user ID
    """
    try:
        async with get_db_session() as db:
            columns = await _get_copilot_table_columns(db)

            # Build sources metadata
            sources_metadata = {
                "query_type": query_type,
                "params": params,
                "sources_count": sources_count
            }

            insert_columns = []
            insert_values = []

            if "user_id" in columns and user_id:
                insert_columns.append("user_id")
                insert_values.append(user_id)

            if "query_text" in columns:
                insert_columns.append("query_text")
                insert_values.append(query)
            elif "user_query" in columns:
                insert_columns.append("user_query")
                insert_values.append(query)
            else:
                return

            if "response_text" in columns:
                insert_columns.append("response_text")
                insert_values.append(answer)
            elif "ai_response" in columns:
                insert_columns.append("ai_response")
                insert_values.append(answer)

            if "sources_used" in columns:
                insert_columns.append("sources_used")
                insert_values.append(json.dumps(sources_metadata))

            if "response_time_ms" in columns:
                insert_columns.append("response_time_ms")
                insert_values.append(response_time_ms)

            if "created_at" in columns:
                insert_columns.append("created_at")
                insert_values.append(datetime.utcnow())

            placeholders = ", ".join(f"${idx}" for idx in range(1, len(insert_values) + 1))
            await db.execute(
                f"INSERT INTO copilot_queries ({', '.join(insert_columns)}) VALUES ({placeholders})",
                *insert_values
            )
    except Exception as e:
        # Don't fail the request if logging fails
        logger.error(f"Failed to log copilot query: {e}")
