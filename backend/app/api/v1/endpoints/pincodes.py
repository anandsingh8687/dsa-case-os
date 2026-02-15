"""Public pincode tools endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.services import lender_service

router = APIRouter(prefix="/pincodes", tags=["pincodes"])


@router.get("/{pincode}/lenders")
async def get_lenders_for_pincode(
    pincode: str,
    active_only: bool = Query(True, description="Only return active lenders"),
):
    """Get lenders serviceable in a pincode for the standalone checker page."""
    if not pincode or len(pincode) != 6 or not pincode.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid pincode. Must be a 6-digit number.",
        )

    lenders = await lender_service.find_lenders_by_pincode(
        pincode=pincode,
        active_only=active_only,
    )

    return {
        "pincode": pincode,
        "lender_count": len(lenders),
        "lenders": lenders,
    }
