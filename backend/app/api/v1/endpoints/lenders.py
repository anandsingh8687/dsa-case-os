"""Lender Knowledge Base API Endpoints

Provides endpoints for:
- Listing lenders and products
- Querying lenders by pincode
- Ingesting CSV data (policy and pincodes)
- Knowledge base statistics
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.services import lender_service
from app.services.stages.stage3_ingestion import (
    ingest_lender_policy_csv,
    ingest_pincode_csv,
    ingest_all_lender_data
)
from app.schemas.shared import LenderProductRule


router = APIRouter(prefix="/lenders", tags=["lenders"])


# ═══════════════════════════════════════════════════════════════
# REQUEST/RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════

class LenderListItem(BaseModel):
    id: UUID
    lender_name: str
    lender_code: Optional[str]
    is_active: bool
    product_count: int = 0
    pincode_count: int = 0


class LenderDetail(BaseModel):
    id: UUID
    lender_name: str
    lender_code: Optional[str]
    is_active: bool
    product_count: int
    pincode_count: int


class PincodeCoverageResponse(BaseModel):
    pincode: str
    serviced: bool
    lender_count: int
    lender_names: List[str]


class IngestionStatsResponse(BaseModel):
    success: bool
    policy: dict
    pincodes: dict
    message: str


class KnowledgeBaseStats(BaseModel):
    lenders: dict
    products: dict
    pincodes: dict
    program_types: dict


# ═══════════════════════════════════════════════════════════════
# LENDER ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.get("/", response_model=List[LenderListItem])
async def list_lenders(
    active_only: bool = Query(True, description="Only return active lenders")
):
    """List all lenders with product and pincode counts.

    Returns a list of lenders with:
    - Basic lender information
    - Number of products available
    - Number of pincodes serviced
    """
    lenders = await lender_service.list_lenders(
        active_only=active_only,
        include_stats=True
    )

    return lenders


@router.get("/stats", response_model=KnowledgeBaseStats)
async def get_knowledge_base_stats():
    """Get overall statistics about the lender knowledge base.

    Returns:
    - Total lenders and active count
    - Total products and policy availability
    - Unique pincodes covered
    - Breakdown by program type (banking, income, hybrid)
    """
    stats = await lender_service.get_knowledge_base_stats()
    return stats


@router.get("/{lender_id}", response_model=LenderDetail)
async def get_lender_detail(lender_id: UUID):
    """Get detailed information about a specific lender.

    Returns:
    - Lender basic info
    - Product count
    - Pincode coverage count
    """
    lender = await lender_service.get_lender(lender_id)

    if not lender:
        raise HTTPException(status_code=404, detail="Lender not found")

    return lender


@router.get("/{lender_id}/products", response_model=List[LenderProductRule])
async def get_lender_products(
    lender_id: UUID,
    active_only: bool = Query(True, description="Only return active products")
):
    """Get all products for a specific lender with full rule details.

    Returns:
    - Product name and program type
    - All hard filter criteria (vintage, CIBIL, turnover, etc.)
    - Document and verification requirements
    - Tenure range
    - Pincode coverage count
    """
    products = await lender_service.get_lender_products(
        lender_id=lender_id,
        active_only=active_only
    )

    return products


# ═══════════════════════════════════════════════════════════════
# PINCODE QUERY ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.get("/by-pincode/{pincode}")
async def get_lenders_by_pincode(
    pincode: str,
    active_only: bool = Query(True, description="Only return active lenders")
):
    """Find all lenders that service a specific pincode.

    Args:
        pincode: 6-digit pincode
        active_only: Filter to active lenders only

    Returns:
        List of lenders with product counts that service this pincode
    """
    if not pincode or len(pincode) != 6 or not pincode.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid pincode. Must be a 6-digit number."
        )

    lenders = await lender_service.find_lenders_by_pincode(
        pincode=pincode,
        active_only=active_only
    )

    return {
        "pincode": pincode,
        "lender_count": len(lenders),
        "lenders": lenders
    }


@router.get("/pincode-coverage/{pincode}", response_model=PincodeCoverageResponse)
async def check_pincode_coverage(pincode: str):
    """Check if a pincode is serviced by any lenders.

    Returns:
    - Whether the pincode is serviced
    - Number of lenders servicing it
    - List of lender names
    """
    if not pincode or len(pincode) != 6 or not pincode.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid pincode. Must be a 6-digit number."
        )

    coverage = await lender_service.check_pincode_coverage(pincode)
    return coverage


@router.get("/pincodes/{pincode}/details")
async def get_pincode_lender_details(
    pincode: str,
    include_market_summary: bool = Query(False, description="Generate AI market summary")
):
    """Get detailed lender information for a pincode (Fix 5: Pincode Checker).

    This is a user-friendly endpoint for the standalone pincode checker page.
    Returns lenders with their product offerings and key eligibility parameters.

    Args:
        pincode: 6-digit pincode
        include_market_summary: If True, generates an LLM-powered market intelligence summary

    Returns:
        - Pincode location info
        - List of lenders with products, CIBIL cutoffs, and max tickets
        - Optional: AI-generated market summary for DSAs
    """
    if not pincode or len(pincode) != 6 or not pincode.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid pincode. Must be a 6-digit number."
        )

    # Get detailed lender data
    lender_details = await lender_service.get_pincode_lender_details(pincode)

    response = {
        "pincode": pincode,
        "lender_count": len(lender_details),
        "lenders": lender_details
    }

    # Generate market summary with LLM if requested
    if include_market_summary and lender_details:
        from app.services.llm_service import generate_pincode_market_summary
        summary = await generate_pincode_market_summary(pincode, lender_details)
        response["market_summary"] = summary

    return response


# ═══════════════════════════════════════════════════════════════
# PRODUCT QUERY ENDPOINTS (for Eligibility Engine)
# ═══════════════════════════════════════════════════════════════

@router.get("/products/all", response_model=List[LenderProductRule])
async def get_all_products(
    program_type: Optional[str] = Query(
        None,
        description="Filter by program type: banking, income, or hybrid"
    ),
    active_only: bool = Query(
        True,
        description="Only return active products with available policies"
    )
):
    """Get all lender products for eligibility scoring.

    This endpoint is used by the Stage 4 eligibility engine to evaluate
    a borrower against all available products.

    Args:
        program_type: Optional filter (banking, income, hybrid)
        active_only: If True, only active products with available policies

    Returns:
        List of all product rules with full criteria
    """
    products = await lender_service.get_all_products_for_scoring(
        program_type=program_type,
        active_only=active_only
    )

    return products


# ═══════════════════════════════════════════════════════════════
# CSV INGESTION ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/ingest/policy")
async def ingest_policy_csv(
    file: UploadFile = File(..., description="Lender Policy CSV file")
):
    """Upload and ingest lender policy CSV.

    Expected format: BL Lender Policy.csv with columns:
    - Lender, Product Program, Min. Vintage, Min. Score, Min. Turnover,
    - Max Ticket size, ABB, Entity, Age, Banking Statement, etc.

    Returns:
        Statistics about the ingestion (lenders created, products created, errors)
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV"
        )

    # Save uploaded file temporarily
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name

    try:
        # Ingest the CSV
        stats = await ingest_lender_policy_csv(tmp_path)

        return {
            "success": True,
            "message": f"Ingested {stats['products_created']} products from {stats['lenders_created']} lenders",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    finally:
        # Clean up temp file
        os.unlink(tmp_path)


@router.post("/ingest/pincodes")
async def ingest_pincodes_csv(
    file: UploadFile = File(..., description="Pincode serviceability CSV file")
):
    """Upload and ingest pincode serviceability CSV.

    Expected format: Each column = a lender name, cells = pincodes they service.

    Returns:
        Statistics about the ingestion (lenders mapped, pincodes created)
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV"
        )

    # Save uploaded file temporarily
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name

    try:
        # Ingest the CSV
        stats = await ingest_pincode_csv(tmp_path)

        return {
            "success": True,
            "message": f"Ingested {stats['pincodes_created']} pincodes for {stats['lenders_mapped']} lenders",
            "stats": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    finally:
        # Clean up temp file
        os.unlink(tmp_path)


@router.post("/ingest/all", response_model=IngestionStatsResponse)
async def ingest_all_data(
    policy_file: UploadFile = File(..., description="Lender Policy CSV"),
    pincode_file: UploadFile = File(..., description="Pincode serviceability CSV")
):
    """Upload and ingest both policy and pincode CSV files at once.

    This is a convenience endpoint that ingests both files in the correct order:
    1. Policy CSV (creates lenders and products)
    2. Pincode CSV (links pincodes to lenders)

    Returns:
        Combined statistics from both ingestions
    """
    # Validate file types
    if not policy_file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Policy file must be a CSV")
    if not pincode_file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Pincode file must be a CSV")

    import tempfile
    import os

    # Save both files temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='_policy.csv') as tmp1:
        content1 = await policy_file.read()
        tmp1.write(content1)
        policy_path = tmp1.name

    with tempfile.NamedTemporaryFile(delete=False, suffix='_pincodes.csv') as tmp2:
        content2 = await pincode_file.read()
        tmp2.write(content2)
        pincode_path = tmp2.name

    try:
        # Ingest both
        combined_stats = await ingest_all_lender_data(policy_path, pincode_path)

        message = (
            f"Successfully ingested: "
            f"{combined_stats['policy']['lenders_created']} lenders, "
            f"{combined_stats['policy']['products_created']} products, "
            f"{combined_stats['pincodes']['pincodes_created']} pincodes"
        )

        combined_stats['message'] = message
        return combined_stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    finally:
        # Clean up temp files
        os.unlink(policy_path)
        os.unlink(pincode_path)
