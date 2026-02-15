"""FastAPI dependencies for authentication and database access."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.database import get_db
from app.models.user import User


# Security scheme for Bearer token
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Dependency to get the current authenticated user.

    This function:
    1. Extracts the JWT token from the Authorization header
    2. Decodes and validates the token
    3. Fetches the user from the database
    4. Returns the user object

    Args:
        credentials: HTTP Authorization credentials (Bearer token)
        db: Database session

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException 401: If token is invalid, expired, or user not found
    """
    # Extract token from credentials
    token = credentials.credentials

    # Define the exception for invalid credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the JWT token
        payload = decode_token(token)

        # Extract user_id from the token payload
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception

        # Convert string to UUID
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


# Type alias for easier use in route handlers
CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> User:
    """
    Dependency that allows only admin users.

    Raises:
        HTTPException 403: If current user is not an admin.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


CurrentAdmin = Annotated[User, Depends(require_admin)]


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> User | None:
    """
    Optional dependency to get the current authenticated user.

    Similar to get_current_user but returns None instead of raising exceptions
    when authentication fails or no credentials are provided.

    Args:
        credentials: HTTP Authorization credentials (Bearer token), optional
        db: Database session

    Returns:
        User | None: The authenticated user object, or None if not authenticated
    """
    if credentials is None:
        return None

    try:
        # Extract token from credentials
        token = credentials.credentials

        # Decode the JWT token
        payload = decode_token(token)

        # Extract user_id from the token payload
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            return None

        # Convert string to UUID
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            return None

    except JWTError:
        return None

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        return None

    return user
