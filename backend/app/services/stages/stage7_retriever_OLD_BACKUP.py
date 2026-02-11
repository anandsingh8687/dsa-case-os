"""Stage 7: Knowledge Retriever for Copilot

Classifies natural language queries and retrieves relevant lender data from the knowledge base.

Query Types Supported:
- CIBIL-based: "lenders for 650 CIBIL"
- Pincode-based: "who serves pincode 400001"
- Lender-specific: "Bajaj Finance policy"
- Comparison: "compare Bajaj and IIFL"
- Vintage-based: "1 year vintage accepted"
- Turnover-based: "50 lakh turnover"
- Entity-based: "proprietorship friendly lenders"
- Requirement-based: "no video KYC", "accept 60+ DPD"
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

from app.db.database import get_db_session
from app.schemas.shared import LenderProductRule

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Types of copilot queries."""
    CIBIL = "cibil"
    PINCODE = "pincode"
    LENDER_SPECIFIC = "lender_specific"
    COMPARISON = "comparison"
    VINTAGE = "vintage"
    TURNOVER = "turnover"
    ENTITY_TYPE = "entity_type"
    TICKET_SIZE = "ticket_size"
    REQUIREMENT = "requirement"
    GENERAL = "general"


# ═══════════════════════════════════════════════════════════════
# QUERY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════

def classify_query(query: str) -> Tuple[QueryType, Dict[str, Any]]:
    """Classify the query and extract relevant parameters.

    Args:
        query: Natural language query from DSA

    Returns:
        (query_type, params) where params contains extracted values
    """
    query_lower = query.lower()
    params = {}

    # Check for pincode pattern (6 digits)
    pincode_match = re.search(r'\b\d{6}\b', query)
    if pincode_match or 'pincode' in query_lower:
        params['pincode'] = pincode_match.group() if pincode_match else None
        return QueryType.PINCODE, params

    # Check for CIBIL score
    cibil_patterns = [
        r'(\d{3})\s*(?:cibil|score|credit score)',
        r'cibil\s*(?:of|score)?\s*(\d{3})',
        r'score\s*(?:of|below|above|under|over)?\s*(\d{3})',
    ]
    for pattern in cibil_patterns:
        match = re.search(pattern, query_lower)
        if match:
            params['cibil_score'] = int(match.group(1))
            # Determine if it's "above" or "below"
            if 'above' in query_lower or 'over' in query_lower or 'more than' in query_lower:
                params['operator'] = '>='
            elif 'below' in query_lower or 'under' in query_lower or 'less than' in query_lower:
                params['operator'] = '<='
            else:
                params['operator'] = '<='  # Default: show lenders that accept this score
            return QueryType.CIBIL, params

    # Check for comparison (mentions multiple lenders)
    lender_keywords = [
        'bajaj', 'tata capital', 'iifl', 'indifi', 'protium',
        'lendingkart', 'flexiloans', 'abfl', 'clix', 'neogrowth',
        'ugro', 'godrej', 'icici', 'hdfc', 'axis', 'yes bank'
    ]
    mentioned_lenders = [lender for lender in lender_keywords if lender in query_lower]

    if 'compar' in query_lower and len(mentioned_lenders) >= 2:
        params['lenders'] = mentioned_lenders
        return QueryType.COMPARISON, params

    # Check for lender-specific query
    if len(mentioned_lenders) == 1:
        params['lender_name'] = mentioned_lenders[0]
        return QueryType.LENDER_SPECIFIC, params

    # Check for vintage
    vintage_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:year|yr)s?\s*(?:vintage|old|business|experience)',
        r'vintage\s*(?:of)?\s*(\d+(?:\.\d+)?)',
    ]
    for pattern in vintage_patterns:
        match = re.search(pattern, query_lower)
        if match:
            params['vintage_years'] = float(match.group(1))
            return QueryType.VINTAGE, params

    # Check for turnover
    turnover_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\s*(?:turnover|revenue|sales)',
        r'turnover\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)?',
        r'(\d+)\s*cr(?:ore)?\s*(?:turnover|revenue)',
    ]
    for pattern in turnover_patterns:
        match = re.search(pattern, query_lower)
        if match:
            amount = float(match.group(1))
            # Convert crores to lakhs if needed
            if 'cr' in pattern:
                amount *= 100
            params['turnover'] = amount
            return QueryType.TURNOVER, params

    # Check for ticket size
    ticket_patterns = [
        r'(?:ticket|loan|amount)\s*(?:of|size)?\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)',
        r'(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\s*(?:loan|ticket|amount)',
    ]
    for pattern in ticket_patterns:
        match = re.search(pattern, query_lower)
        if match:
            params['ticket_size'] = float(match.group(1))
            return QueryType.TICKET_SIZE, params

    # Check for entity type
    entity_keywords = {
        'proprietor': 'proprietorship',
        'partnership': 'partnership',
        'pvt ltd': 'private limited',
        'private limited': 'private limited',
        'llp': 'llp',
        'one person company': 'opc',
        'opc': 'opc',
    }
    for keyword, entity_type in entity_keywords.items():
        if keyword in query_lower:
            params['entity_type'] = entity_type
            return QueryType.ENTITY_TYPE, params

    # Check for specific requirements
    requirement_keywords = {
        'video kyc': 'video_kyc_required',
        'video verification': 'video_kyc_required',
        'physical verification': 'fi_required',
        'field investigation': 'fi_required',
        'fi required': 'fi_required',
        'tele pd': 'tele_pd_required',
        'telephonic pd': 'tele_pd_required',
        'gst required': 'gst_required',
    }
    for keyword, requirement in requirement_keywords.items():
        if keyword in query_lower:
            params['requirement'] = requirement
            # Check if they want "no" or "without"
            params['value'] = not ('no ' in query_lower or 'without' in query_lower or "don't" in query_lower)
            return QueryType.REQUIREMENT, params

    # Default: general query
    return QueryType.GENERAL, params


# ═══════════════════════════════════════════════════════════════
# DATA RETRIEVAL
# ═══════════════════════════════════════════════════════════════

async def retrieve_lender_data(
    query_type: QueryType,
    params: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Retrieve relevant lender data based on query type and parameters.

    Args:
        query_type: Type of query
        params: Extracted parameters from the query

    Returns:
        List of lender product records as dicts
    """
    async with get_db_session() as db:
        if query_type == QueryType.CIBIL:
            return await _retrieve_by_cibil(db, params)

        elif query_type == QueryType.PINCODE:
            return await _retrieve_by_pincode(db, params)

        elif query_type == QueryType.LENDER_SPECIFIC:
            return await _retrieve_lender_details(db, params)

        elif query_type == QueryType.COMPARISON:
            return await _retrieve_for_comparison(db, params)

        elif query_type == QueryType.VINTAGE:
            return await _retrieve_by_vintage(db, params)

        elif query_type == QueryType.TURNOVER:
            return await _retrieve_by_turnover(db, params)

        elif query_type == QueryType.ENTITY_TYPE:
            return await _retrieve_by_entity_type(db, params)

        elif query_type == QueryType.TICKET_SIZE:
            return await _retrieve_by_ticket_size(db, params)

        elif query_type == QueryType.REQUIREMENT:
            return await _retrieve_by_requirement(db, params)

        else:  # GENERAL
            return await _retrieve_general(db)


async def _retrieve_by_cibil(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by CIBIL score requirement."""
    cibil_score = params.get('cibil_score')
    operator = params.get('operator', '<=')

    # Build query based on operator
    if operator == '<=':
        # Find lenders that accept this CIBIL or lower
        condition = "lp.min_cibil_score <= $1"
        order = "lp.min_cibil_score ASC"
    else:
        # Find lenders requiring higher CIBIL
        condition = "lp.min_cibil_score > $1"
        order = "lp.min_cibil_score ASC"

    query = f"""
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.eligible_entity_types,
            lp.video_kyc_required,
            lp.fi_required,
            lp.gst_required,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND {condition}
        GROUP BY l.lender_name, lp.id, lp.product_name, lp.min_cibil_score,
                 lp.min_vintage_years, lp.min_turnover_annual, lp.max_ticket_size,
                 lp.eligible_entity_types, lp.video_kyc_required, lp.fi_required, lp.gst_required
        ORDER BY {order}
        LIMIT 20
    """

    rows = await db.fetch(query, cibil_score)
    return [dict(row) for row in rows]


async def _retrieve_by_pincode(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders serving a specific pincode."""
    pincode = params.get('pincode')

    if not pincode:
        return []

    query = """
        SELECT DISTINCT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.eligible_entity_types
        FROM lender_pincodes lpc
        INNER JOIN lenders l ON lpc.lender_id = l.id
        INNER JOIN lender_products lp ON l.id = lp.lender_id
        WHERE lpc.pincode = $1
          AND lp.is_active = TRUE
          AND l.is_active = TRUE
        ORDER BY l.lender_name, lp.product_name
    """

    rows = await db.fetch(query, pincode)
    return [dict(row) for row in rows]


async def _retrieve_lender_details(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve all products for a specific lender."""
    lender_name = params.get('lender_name', '')

    query = """
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.min_abb,
            lp.eligible_entity_types,
            lp.no_30plus_dpd_months,
            lp.no_60plus_dpd_months,
            lp.no_90plus_dpd_months,
            lp.banking_months_required,
            lp.gst_required,
            lp.video_kyc_required,
            lp.fi_required,
            lp.tele_pd_required,
            lp.tenor_min_months,
            lp.tenor_max_months,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE LOWER(l.lender_name) LIKE LOWER($1)
          AND lp.is_active = TRUE
          AND l.is_active = TRUE
        GROUP BY l.lender_name, lp.id, lp.product_name, lp.min_cibil_score,
                 lp.min_vintage_years, lp.min_turnover_annual, lp.max_ticket_size,
                 lp.min_abb, lp.eligible_entity_types, lp.no_30plus_dpd_months,
                 lp.no_60plus_dpd_months, lp.no_90plus_dpd_months,
                 lp.banking_months_required, lp.gst_required, lp.video_kyc_required,
                 lp.fi_required, lp.tele_pd_required, lp.tenor_min_months, lp.tenor_max_months
        ORDER BY lp.product_name
    """

    rows = await db.fetch(query, f'%{lender_name}%')
    return [dict(row) for row in rows]


async def _retrieve_for_comparison(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve products from multiple lenders for comparison."""
    lenders = params.get('lenders', [])

    if not lenders:
        return []

    # Build IN clause for lender names
    placeholders = ', '.join([f'${i+1}' for i in range(len(lenders))])

    query = f"""
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.min_abb,
            lp.eligible_entity_types,
            lp.video_kyc_required,
            lp.fi_required,
            lp.tele_pd_required,
            lp.tenor_min_months,
            lp.tenor_max_months,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND (
            {' OR '.join([f"LOWER(l.lender_name) LIKE LOWER('%' || ${i+1} || '%')" for i in range(len(lenders))])}
          )
        GROUP BY l.lender_name, lp.id, lp.product_name, lp.min_cibil_score,
                 lp.min_vintage_years, lp.min_turnover_annual, lp.max_ticket_size,
                 lp.min_abb, lp.eligible_entity_types, lp.video_kyc_required,
                 lp.fi_required, lp.tele_pd_required, lp.tenor_min_months, lp.tenor_max_months
        ORDER BY l.lender_name, lp.product_name
    """

    rows = await db.fetch(query, *lenders)
    return [dict(row) for row in rows]


async def _retrieve_by_vintage(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by business vintage requirement."""
    vintage_years = params.get('vintage_years')

    query = """
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_vintage_years,
            lp.min_cibil_score,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.eligible_entity_types
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND lp.min_vintage_years <= $1
        ORDER BY lp.min_vintage_years ASC, l.lender_name
        LIMIT 20
    """

    rows = await db.fetch(query, vintage_years)
    return [dict(row) for row in rows]


async def _retrieve_by_turnover(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by turnover requirement."""
    turnover = params.get('turnover')

    query = """
        SELECT
            l.lender_name,
            lp.product_name,
            lp.min_turnover_annual,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.max_ticket_size,
            lp.eligible_entity_types
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND lp.min_turnover_annual <= $1
        ORDER BY lp.min_turnover_annual DESC, l.lender_name
        LIMIT 20
    """

    rows = await db.fetch(query, turnover)
    return [dict(row) for row in rows]


async def _retrieve_by_entity_type(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders supporting a specific entity type."""
    entity_type = params.get('entity_type')

    query = """
        SELECT
            l.lender_name,
            lp.product_name,
            lp.eligible_entity_types,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND lp.eligible_entity_types @> $1::jsonb
        ORDER BY l.lender_name, lp.product_name
        LIMIT 20
    """

    import json
    rows = await db.fetch(query, json.dumps([entity_type]))
    return [dict(row) for row in rows]


async def _retrieve_by_ticket_size(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by ticket size."""
    ticket_size = params.get('ticket_size')

    query = """
        SELECT
            l.lender_name,
            lp.product_name,
            lp.max_ticket_size,
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.eligible_entity_types
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND lp.max_ticket_size >= $1
        ORDER BY lp.max_ticket_size ASC, l.lender_name
        LIMIT 20
    """

    rows = await db.fetch(query, ticket_size)
    return [dict(row) for row in rows]


async def _retrieve_by_requirement(db, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Retrieve lenders by specific requirement (e.g., video KYC)."""
    requirement = params.get('requirement')
    value = params.get('value', False)

    query = f"""
        SELECT
            l.lender_name,
            lp.product_name,
            lp.{requirement},
            lp.min_cibil_score,
            lp.min_vintage_years,
            lp.min_turnover_annual,
            lp.max_ticket_size,
            lp.eligible_entity_types
        FROM lender_products lp
        INNER JOIN lenders l ON lp.lender_id = l.id
        WHERE lp.is_active = TRUE
          AND l.is_active = TRUE
          AND lp.{requirement} = $1
        ORDER BY l.lender_name, lp.product_name
        LIMIT 20
    """

    rows = await db.fetch(query, value)
    return [dict(row) for row in rows]


async def _retrieve_general(db) -> List[Dict[str, Any]]:
    """Retrieve general lender overview."""
    query = """
        SELECT
            l.lender_name,
            COUNT(DISTINCT lp.id) as product_count,
            MIN(lp.min_cibil_score) as lowest_cibil,
            MIN(lp.min_vintage_years) as lowest_vintage,
            MAX(lp.max_ticket_size) as max_ticket,
            COUNT(DISTINCT lpc.pincode) as pincode_coverage
        FROM lenders l
        LEFT JOIN lender_products lp ON l.id = lp.lender_id AND lp.is_active = TRUE
        LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
        WHERE l.is_active = TRUE
        GROUP BY l.lender_name
        HAVING COUNT(DISTINCT lp.id) > 0
        ORDER BY l.lender_name
        LIMIT 25
    """

    rows = await db.fetch(query)
    return [dict(row) for row in rows]
