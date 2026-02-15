"""Lender Knowledge Base Service

Provides CRUD operations and queries for the lender knowledge base:
- List lenders with product counts
- Get lender details and products
- Find lenders by pincode
- Get all products for eligibility scoring
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.db.database import get_db_session
from app.schemas.shared import LenderProductRule

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# LENDER QUERIES
# ═══════════════════════════════════════════════════════════════

async def list_lenders(
    active_only: bool = True,
    include_stats: bool = True
) -> List[Dict[str, Any]]:
    """List all lenders with optional product counts and pincode coverage.

    Args:
        active_only: If True, only return active lenders
        include_stats: If True, include product count and pincode count

    Returns:
        List of lender dictionaries with:
        - id, lender_name, lender_code, is_active
        - product_count (if include_stats)
        - pincode_count (if include_stats)
    """
    async with get_db_session() as db:
        if include_stats:
            query = """
                SELECT
                    l.id,
                    l.lender_name,
                    l.lender_code,
                    l.is_active,
                    l.created_at,
                    COUNT(DISTINCT lp.id) as product_count,
                    COUNT(DISTINCT lpc.pincode) as pincode_count
                FROM lenders l
                LEFT JOIN lender_products lp ON l.id = lp.lender_id
                LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
            """

            if active_only:
                query += " WHERE l.is_active = TRUE"

            query += """
                GROUP BY l.id, l.lender_name, l.lender_code, l.is_active, l.created_at
                ORDER BY l.lender_name
            """
        else:
            query = """
                SELECT id, lender_name, lender_code, is_active, created_at
                FROM lenders
            """

            if active_only:
                query += " WHERE is_active = TRUE"

            query += " ORDER BY lender_name"

        rows = await db.fetch(query)

        return [dict(row) for row in rows]


async def get_lender(lender_id: UUID) -> Optional[Dict[str, Any]]:
    """Get a single lender by ID with full details.

    Returns:
        Lender dict with product_count and pincode_count, or None if not found
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT
                l.id,
                l.lender_name,
                l.lender_code,
                l.is_active,
                l.created_at,
                l.updated_at,
                COUNT(DISTINCT lp.id) as product_count,
                COUNT(DISTINCT lpc.pincode) as pincode_count
            FROM lenders l
            LEFT JOIN lender_products lp ON l.id = lp.lender_id
            LEFT JOIN lender_pincodes lpc ON l.id = lpc.lender_id
            WHERE l.id = $1
            GROUP BY l.id, l.lender_name, l.lender_code, l.is_active, l.created_at, l.updated_at
            """,
            lender_id
        )

        return dict(row) if row else None


async def get_lender_by_name(lender_name: str) -> Optional[Dict[str, Any]]:
    """Get a lender by name (case-insensitive).

    Returns:
        Lender dict or None if not found
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT id, lender_name, lender_code, is_active, created_at, updated_at
            FROM lenders
            WHERE LOWER(lender_name) = LOWER($1)
            """,
            lender_name
        )

        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════
# PRODUCT QUERIES
# ═══════════════════════════════════════════════════════════════

async def get_lender_products(
    lender_id: UUID,
    active_only: bool = True
) -> List[LenderProductRule]:
    """Get all products for a lender.

    Args:
        lender_id: The lender UUID
        active_only: If True, only return active products

    Returns:
        List of LenderProductRule objects
    """
    async with get_db_session() as db:
        # Get lender name first
        lender_row = await db.fetchrow(
            "SELECT lender_name FROM lenders WHERE id = $1",
            lender_id
        )

        if not lender_row:
            return []

        lender_name = lender_row['lender_name']

        # Get products
        query = """
            SELECT
                lp.*,
                COUNT(DISTINCT lpc.pincode) as serviceable_pincodes_count
            FROM lender_products lp
            LEFT JOIN lender_pincodes lpc ON lp.lender_id = lpc.lender_id
            WHERE lp.lender_id = $1
        """

        if active_only:
            query += " AND lp.is_active = TRUE"

        query += """
            GROUP BY lp.id
            ORDER BY lp.product_name
        """

        rows = await db.fetch(query, lender_id)

        products = []
        for row in rows:
            product_dict = dict(row)
            product_dict['lender_name'] = lender_name

            # Convert to LenderProductRule
            product = _row_to_lender_product_rule(product_dict)
            products.append(product)

        return products


async def get_product_by_id(product_id: UUID) -> Optional[LenderProductRule]:
    """Get a single product by ID.

    Returns:
        LenderProductRule or None if not found
    """
    async with get_db_session() as db:
        row = await db.fetchrow(
            """
            SELECT
                lp.*,
                l.lender_name,
                COUNT(DISTINCT lpc.pincode) as serviceable_pincodes_count
            FROM lender_products lp
            INNER JOIN lenders l ON lp.lender_id = l.id
            LEFT JOIN lender_pincodes lpc ON lp.lender_id = lpc.lender_id
            WHERE lp.id = $1
            GROUP BY lp.id, l.lender_name
            """,
            product_id
        )

        if not row:
            return None

        return _row_to_lender_product_rule(dict(row))


async def get_all_products_for_scoring(
    program_type: Optional[str] = None,
    active_only: bool = True
) -> List[LenderProductRule]:
    """Get all active lender products for eligibility scoring.

    This is used by the Stage 4 eligibility engine to evaluate a borrower
    against all available products.

    Args:
        program_type: Filter by program type (banking, income, hybrid)
        active_only: If True, only return active products with available policies

    Returns:
        List of LenderProductRule objects
    """
    async with get_db_session() as db:
        query = """
            SELECT
                lp.*,
                l.lender_name,
                COUNT(DISTINCT lpc.pincode) as serviceable_pincodes_count
            FROM lender_products lp
            INNER JOIN lenders l ON lp.lender_id = l.id
            LEFT JOIN lender_pincodes lpc ON lp.lender_id = lpc.lender_id
            WHERE 1=1
        """

        params = []
        param_count = 1

        if active_only:
            query += " AND lp.is_active = TRUE AND lp.policy_available = TRUE AND l.is_active = TRUE"

        if program_type:
            query += f" AND lp.program_type = ${param_count}"
            params.append(program_type)
            param_count += 1

        query += """
            GROUP BY lp.id, l.lender_name
            ORDER BY l.lender_name, lp.product_name
        """

        rows = await db.fetch(query, *params)

        products = []
        for row in rows:
            product = _row_to_lender_product_rule(dict(row))
            products.append(product)

        logger.info(
            f"Retrieved {len(products)} products for scoring "
            f"(program_type={program_type}, active_only={active_only})"
        )

        return products


# ═══════════════════════════════════════════════════════════════
# PINCODE QUERIES
# ═══════════════════════════════════════════════════════════════

async def find_lenders_by_pincode(
    pincode: str,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """Find all lenders that service a specific pincode.

    Args:
        pincode: The 6-digit pincode
        active_only: If True, only return active lenders

    Returns:
        List of dicts with: lender_id, lender_name, product_count
    """
    async with get_db_session() as db:
        query = """
            SELECT DISTINCT
                l.id as lender_id,
                l.lender_name,
                l.lender_code,
                COUNT(DISTINCT lp.id) as product_count,
                COALESCE(ARRAY_REMOVE(ARRAY_AGG(DISTINCT lp.product_name), NULL), ARRAY[]::text[]) as product_types,
                MIN(lp.min_cibil_score) as min_cibil,
                MAX(lp.max_ticket_size) as max_ticket_size
            FROM lenders l
            INNER JOIN lender_pincodes lpc ON l.id = lpc.lender_id
            LEFT JOIN lender_products lp ON l.id = lp.lender_id AND lp.is_active = TRUE
            WHERE lpc.pincode = $1
        """

        if active_only:
            query += " AND l.is_active = TRUE"

        query += """
            GROUP BY l.id, l.lender_name, l.lender_code
            ORDER BY l.lender_name
        """

        rows = await db.fetch(query, pincode)

        return [dict(row) for row in rows]


async def check_pincode_coverage(pincode: str) -> Dict[str, Any]:
    """Check if a pincode is serviced by any lenders.

    Returns:
        Dict with: serviced (bool), lender_count (int), lender_names (list)
    """
    lenders = await find_lenders_by_pincode(pincode, active_only=True)

    return {
        "pincode": pincode,
        "serviced": len(lenders) > 0,
        "lender_count": len(lenders),
        "lender_names": [l['lender_name'] for l in lenders]
    }


# ═══════════════════════════════════════════════════════════════
# STATISTICS
# ═══════════════════════════════════════════════════════════════

async def get_knowledge_base_stats() -> Dict[str, Any]:
    """Get overall statistics about the knowledge base.

    Returns:
        Dict with counts of lenders, products, pincodes, etc.
    """
    async with get_db_session() as db:
        # Count lenders
        lender_stats = dict(await db.fetchrow(
            "SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_active = TRUE) as active FROM lenders"
        ))

        # Count products
        product_stats = dict(await db.fetchrow(
            """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = TRUE) as active,
                COUNT(*) FILTER (WHERE policy_available = FALSE) as no_policy
            FROM lender_products
            """
        ))

        # Count unique pincodes
        pincode_stats = dict(await db.fetchrow(
            "SELECT COUNT(DISTINCT pincode) as unique_pincodes FROM lender_pincodes"
        ))

        # Program type breakdown
        rows = await db.fetch(
            """
            SELECT program_type, COUNT(*) as count
            FROM lender_products
            WHERE is_active = TRUE AND policy_available = TRUE
            GROUP BY program_type
            """
        )
        program_breakdown = {row['program_type']: row['count'] for row in rows}

        return {
            "lenders": {
                "total": lender_stats['total'],
                "active": lender_stats['active']
            },
            "products": {
                "total": product_stats['total'],
                "active": product_stats['active'],
                "no_policy": product_stats['no_policy']
            },
            "pincodes": {
                "unique_covered": pincode_stats['unique_pincodes']
            },
            "program_types": program_breakdown
        }


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _row_to_lender_product_rule(row: Dict[str, Any]) -> LenderProductRule:
    """Convert a database row to a LenderProductRule schema object."""

    # Handle JSONB fields
    eligible_entity_types = row.get('eligible_entity_types', [])
    if isinstance(eligible_entity_types, str):
        import json
        try:
            eligible_entity_types = json.loads(eligible_entity_types)
        except:
            eligible_entity_types = []

    excluded_industries = row.get('excluded_industries', [])
    if isinstance(excluded_industries, str):
        import json
        try:
            excluded_industries = json.loads(excluded_industries)
        except:
            excluded_industries = []

    required_documents = row.get('required_documents', [])
    if isinstance(required_documents, str):
        import json
        try:
            required_documents = json.loads(required_documents)
        except:
            required_documents = []

    return LenderProductRule(
        lender_name=row['lender_name'],
        product_name=row.get('product_name', ''),
        program_type=row.get('program_type'),
        min_vintage_years=row.get('min_vintage_years'),
        min_cibil_score=row.get('min_cibil_score'),
        min_turnover_annual=row.get('min_turnover_annual'),
        max_ticket_size=row.get('max_ticket_size'),
        min_abb=row.get('min_abb'),
        abb_to_emi_ratio=row.get('abb_to_emi_ratio'),
        eligible_entity_types=eligible_entity_types or [],
        age_min=row.get('age_min'),
        age_max=row.get('age_max'),
        no_30plus_dpd_months=row.get('no_30plus_dpd_months'),
        no_60plus_dpd_months=row.get('no_60plus_dpd_months'),
        no_90plus_dpd_months=row.get('no_90plus_dpd_months'),
        max_enquiries_rule=row.get('max_enquiries_rule'),
        max_overdue_amount=row.get('max_overdue_amount'),
        emi_bounce_rule=row.get('emi_bounce_rule'),
        bureau_check_detail=row.get('bureau_check_detail'),
        banking_months_required=row.get('banking_months_required'),
        bank_source_type=row.get('bank_source_type'),
        gst_required=row.get('gst_required', False),
        ownership_proof_required=row.get('ownership_proof_required', False),
        kyc_documents=row.get('kyc_documents'),
        tenor_min_months=row.get('tenor_min_months'),
        tenor_max_months=row.get('tenor_max_months'),
        tele_pd_required=row.get('tele_pd_required', False),
        video_kyc_required=row.get('video_kyc_required', False),
        fi_required=row.get('fi_required', False),
        policy_available=row.get('policy_available', True),
        serviceable_pincodes_count=row.get('serviceable_pincodes_count', 0),
        max_foir=row.get('max_foir'),
        excluded_industries=excluded_industries or [],
        min_ticket_size=row.get('min_ticket_size'),
        required_documents=required_documents or []
    )
