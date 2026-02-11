"""
Example: How to protect routes with JWT authentication

This file demonstrates how to use the authentication system
in your FastAPI routes.
"""

from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser  # Use the type alias for convenience
from app.db.database import get_db
from app.models.case import Case
from app.schemas.shared import CaseResponse


router = APIRouter(prefix="/api/v1", tags=["examples"])


# ═══════════════════════════════════════════════════════════════
# METHOD 1: Using CurrentUser type alias (RECOMMENDED)
# ═══════════════════════════════════════════════════════════════

@router.get("/my-cases")
async def list_my_cases(
    current_user: CurrentUser,  # Authentication required
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[CaseResponse]:
    """
    Get all cases belonging to the current user.

    This route is protected - only authenticated users can access it.
    The current_user is automatically injected from the JWT token.
    """
    # Query only cases belonging to this user
    result = await db.execute(
        select(Case)
        .where(Case.user_id == current_user.id)
        .order_by(Case.created_at.desc())
    )
    cases = result.scalars().all()

    # Return cases as response models
    return [
        CaseResponse(
            id=case.id,
            case_id=case.case_id,
            status=case.status,
            program_type=case.program_type,
            borrower_name=case.borrower_name,
            entity_type=case.entity_type,
            completeness_score=case.completeness_score,
            created_at=case.created_at,
            updated_at=case.updated_at,
        )
        for case in cases
    ]


# ═══════════════════════════════════════════════════════════════
# METHOD 2: Explicit dependency (alternative approach)
# ═══════════════════════════════════════════════════════════════

from app.core.deps import get_current_user
from app.models.user import User


@router.get("/profile")
async def get_my_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Get the current user's profile.

    Alternative method using explicit dependency import.
    Both methods work identically.
    """
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "organization": current_user.organization,
        "is_active": current_user.is_active,
    }


# ═══════════════════════════════════════════════════════════════
# EXAMPLE 3: Creating resources owned by current user
# ═══════════════════════════════════════════════════════════════

from app.schemas.shared import CaseCreate


@router.post("/cases", status_code=201)
async def create_case(
    case_data: CaseCreate,
    current_user: CurrentUser,  # Auth required
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CaseResponse:
    """
    Create a new case for the current user.

    The case is automatically associated with the authenticated user.
    """
    # Generate case ID (simplified - you'd use your actual ID generator)
    from datetime import datetime
    case_id = f"CASE-{datetime.now().strftime('%Y%m%d')}-0001"

    # Create case owned by current user
    new_case = Case(
        case_id=case_id,
        user_id=current_user.id,  # Associate with current user
        borrower_name=case_data.borrower_name,
        entity_type=case_data.entity_type,
        program_type=case_data.program_type,
        industry_type=case_data.industry_type,
        pincode=case_data.pincode,
        loan_amount_requested=case_data.loan_amount_requested,
        status="created",
    )

    db.add(new_case)
    await db.commit()
    await db.refresh(new_case)

    return CaseResponse(
        id=new_case.id,
        case_id=new_case.case_id,
        status=new_case.status,
        program_type=new_case.program_type,
        borrower_name=new_case.borrower_name,
        entity_type=new_case.entity_type,
        completeness_score=new_case.completeness_score,
        created_at=new_case.created_at,
        updated_at=new_case.updated_at,
    )


# ═══════════════════════════════════════════════════════════════
# EXAMPLE 4: Role-based access control
# ═══════════════════════════════════════════════════════════════

from fastapi import HTTPException, status


@router.get("/admin/users")
async def list_all_users(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Admin-only endpoint to list all users.

    Demonstrates role-based access control.
    """
    # Check if user has admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    # Admin can see all users
    result = await db.execute(select(User))
    users = result.scalars().all()

    return [
        {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        }
        for user in users
    ]


# ═══════════════════════════════════════════════════════════════
# EXAMPLE 5: Optional authentication
# ═══════════════════════════════════════════════════════════════

from typing import Optional


async def get_current_user_optional(
    credentials: Optional[str] = None
) -> Optional[User]:
    """
    Optional authentication dependency.

    Returns user if authenticated, None otherwise.
    Use this for routes that have different behavior for authenticated users
    but don't require authentication.
    """
    if not credentials:
        return None
    try:
        from app.core.deps import get_current_user
        # Implementation would need to be adapted for optional auth
        return None  # Simplified for example
    except:
        return None


@router.get("/public-cases")
async def list_public_cases(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Public endpoint that behaves differently for authenticated users.

    - Authenticated users see their own cases
    - Unauthenticated users see sample/public cases
    """
    if current_user:
        # Show user's cases if authenticated
        result = await db.execute(
            select(Case).where(Case.user_id == current_user.id)
        )
    else:
        # Show public cases if not authenticated
        result = await db.execute(
            select(Case).where(Case.status == "public").limit(10)
        )

    cases = result.scalars().all()
    return {"cases": [case.case_id for case in cases]}


# ═══════════════════════════════════════════════════════════════
# KEY POINTS
# ═══════════════════════════════════════════════════════════════

"""
1. Import CurrentUser from app.core.deps for the simplest approach
2. The authenticated user is automatically available in your route
3. Always filter queries by current_user.id for user-owned resources
4. Implement role checks for admin/privileged operations
5. Return 403 Forbidden for authorization failures (not 401)
6. The dependency automatically:
   - Extracts the JWT token from Authorization header
   - Validates the token
   - Fetches the user from database
   - Raises 401 if token is invalid/expired
   - Raises 403 if user is inactive
"""
