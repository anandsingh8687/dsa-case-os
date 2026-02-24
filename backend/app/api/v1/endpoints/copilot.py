from fastapi import APIRouter, HTTPException, Depends
from app.schemas.shared import CopilotQuery, CopilotResponse
from app.services.stages.stage7_copilot import query_copilot as process_copilot_query
from app.models.user import User
from app.core.deps import get_current_user_optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/query", response_model=CopilotResponse)
async def query_copilot(
    query_data: CopilotQuery,
    current_user: User = Depends(get_current_user_optional)
):
    """Query the DSA Copilot for lender information.

    The copilot accepts natural language queries about lenders and their policies.

    **Example queries:**
    - "Which lenders accept CIBIL score below 650?"
    - "Who serves pincode 400001?"
    - "Compare Bajaj Finance and Tata Capital"
    - "What's the policy for proprietorship loans at IIFL?"
    - "Lenders with no video KYC requirement"
    - "Maximum ticket size 50 lakh"

    **Returns:**
    - Natural language answer
    - Sources with lender details
    - Response time in milliseconds
    """
    try:
        # Extract user ID if authenticated
        user_id = str(current_user.id) if current_user else None

        # Process the query
        response = await process_copilot_query(
            query=query_data.query,
            user_id=user_id,
            organization_id=str(current_user.organization_id) if current_user and current_user.organization_id else None,
            ui_history=[item.model_dump() for item in query_data.history] if query_data.history else None
        )

        return response

    except Exception as e:
        logger.error(f"Error in copilot endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process query: {str(e)}"
        )
