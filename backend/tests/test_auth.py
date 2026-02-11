"""Tests for authentication endpoints and JWT functionality."""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.shared import UserCreate


# ═══════════════════════════════════════════════════════════════
# SECURITY UTILITIES TESTS
# ═══════════════════════════════════════════════════════════════


class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password(self):
        """Test that password hashing works."""
        password = "MySecurePassword123!"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix
        assert len(hashed) > 50

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "MySecurePassword123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "MySecurePassword123!"
        wrong_password = "WrongPassword456!"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_different_hashes_for_same_password(self):
        """Test that hashing the same password twice produces different hashes (salt)."""
        password = "MySecurePassword123!"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token(self):
        """Test JWT token creation."""
        user_id = str(uuid4())
        email = "test@example.com"

        token = create_access_token(user_id, email)

        assert isinstance(token, str)
        assert len(token) > 50

    def test_decode_valid_token(self):
        """Test decoding a valid JWT token."""
        user_id = str(uuid4())
        email = "test@example.com"

        token = create_access_token(user_id, email)
        payload = decode_token(token)

        assert payload["sub"] == user_id
        assert payload["email"] == email
        assert "exp" in payload
        assert "iat" in payload

    def test_decode_expired_token(self):
        """Test that expired tokens raise an error."""
        user_id = str(uuid4())
        email = "test@example.com"

        # Create an expired token (expired 1 hour ago)
        expire = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "iat": datetime.now(timezone.utc),
        }
        expired_token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )

        with pytest.raises(Exception):  # JWTError or its subclass
            decode_token(expired_token)

    def test_decode_invalid_token(self):
        """Test that invalid tokens raise an error."""
        invalid_token = "invalid.token.here"

        with pytest.raises(Exception):  # JWTError
            decode_token(invalid_token)

    def test_decode_token_wrong_secret(self):
        """Test that tokens signed with wrong secret fail."""
        user_id = str(uuid4())
        email = "test@example.com"

        # Create token with wrong secret
        payload = {
            "sub": user_id,
            "email": email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        wrong_token = jwt.encode(payload, "wrong-secret", algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(Exception):  # JWTError
            decode_token(wrong_token)


# ═══════════════════════════════════════════════════════════════
# ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestUserRegistration:
    """Test user registration endpoint."""

    async def test_register_new_user(self, db_session):
        """Test successful user registration."""
        # Import here to avoid circular imports
        from app.api.v1.endpoints.auth import register

        user_data = UserCreate(
            email="newuser@example.com",
            password="SecurePassword123!",
            full_name="New User",
            phone="1234567890",
            organization="Test Org",
        )

        response = await register(user_data, db_session)

        assert response.email == user_data.email
        assert response.full_name == user_data.full_name
        assert response.role == "dsa"
        assert response.is_active is True
        assert response.id is not None

        # Verify user was actually created in database
        result = await db_session.execute(
            select(User).where(User.email == user_data.email)
        )
        created_user = result.scalar_one_or_none()
        assert created_user is not None
        assert created_user.email == user_data.email

    async def test_register_duplicate_email(self, db_session):
        """Test that registering with duplicate email fails."""
        from app.api.v1.endpoints.auth import register

        user_data = UserCreate(
            email="duplicate@example.com",
            password="SecurePassword123!",
            full_name="First User",
        )

        # Register first user
        await register(user_data, db_session)

        # Try to register second user with same email
        duplicate_data = UserCreate(
            email="duplicate@example.com",
            password="DifferentPassword456!",
            full_name="Second User",
        )

        with pytest.raises(HTTPException) as exc_info:
            await register(duplicate_data, db_session)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered" in exc_info.value.detail.lower()

    async def test_register_password_is_hashed(self, db_session):
        """Test that password is properly hashed in database."""
        from app.api.v1.endpoints.auth import register

        password = "MyPlainTextPassword123!"
        user_data = UserCreate(
            email="hashtest@example.com",
            password=password,
            full_name="Hash Test User",
        )

        await register(user_data, db_session)

        # Retrieve user from database
        result = await db_session.execute(
            select(User).where(User.email == user_data.email)
        )
        created_user = result.scalar_one()

        # Verify password is hashed, not plain text
        assert created_user.hashed_password != password
        assert created_user.hashed_password.startswith("$2b$")

        # Verify hashed password can be verified
        assert verify_password(password, created_user.hashed_password) is True


@pytest.mark.asyncio
class TestUserLogin:
    """Test user login endpoint."""

    async def test_login_success(self, db_session):
        """Test successful user login."""
        from app.api.v1.endpoints.auth import register, login, LoginRequest

        # Create a user first
        password = "SecurePassword123!"
        user_data = UserCreate(
            email="logintest@example.com",
            password=password,
            full_name="Login Test User",
        )
        await register(user_data, db_session)

        # Try to login
        credentials = LoginRequest(
            email="logintest@example.com",
            password=password,
        )

        response = await login(credentials, db_session)

        assert response.access_token is not None
        assert isinstance(response.access_token, str)
        assert response.token_type == "bearer"

        # Verify token is valid
        payload = decode_token(response.access_token)
        assert payload["email"] == user_data.email

    async def test_login_wrong_password(self, db_session):
        """Test login with incorrect password."""
        from app.api.v1.endpoints.auth import register, login, LoginRequest

        # Create a user
        user_data = UserCreate(
            email="wrongpass@example.com",
            password="CorrectPassword123!",
            full_name="Wrong Pass User",
        )
        await register(user_data, db_session)

        # Try to login with wrong password
        credentials = LoginRequest(
            email="wrongpass@example.com",
            password="WrongPassword456!",
        )

        with pytest.raises(HTTPException) as exc_info:
            await login(credentials, db_session)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "incorrect" in exc_info.value.detail.lower()

    async def test_login_nonexistent_user(self, db_session):
        """Test login with non-existent email."""
        from app.api.v1.endpoints.auth import login, LoginRequest

        credentials = LoginRequest(
            email="nonexistent@example.com",
            password="SomePassword123!",
        )

        with pytest.raises(HTTPException) as exc_info:
            await login(credentials, db_session)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_login_inactive_user(self, db_session):
        """Test that inactive users cannot login."""
        from app.api.v1.endpoints.auth import register, login, LoginRequest

        # Create a user
        password = "SecurePassword123!"
        user_data = UserCreate(
            email="inactive@example.com",
            password=password,
            full_name="Inactive User",
        )
        await register(user_data, db_session)

        # Deactivate the user
        result = await db_session.execute(
            select(User).where(User.email == "inactive@example.com")
        )
        user = result.scalar_one()
        user.is_active = False
        await db_session.commit()

        # Try to login
        credentials = LoginRequest(
            email="inactive@example.com",
            password=password,
        )

        with pytest.raises(HTTPException) as exc_info:
            await login(credentials, db_session)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "inactive" in exc_info.value.detail.lower()


@pytest.mark.asyncio
class TestGetCurrentUser:
    """Test the /me endpoint and get_current_user dependency."""

    async def test_get_me_success(self, db_session):
        """Test getting current user info with valid token."""
        from app.api.v1.endpoints.auth import register, login, get_me, LoginRequest

        # Create and login a user
        password = "SecurePassword123!"
        user_data = UserCreate(
            email="metest@example.com",
            password=password,
            full_name="Me Test User",
        )
        registered_user = await register(user_data, db_session)

        credentials = LoginRequest(email=user_data.email, password=password)
        login_response = await login(credentials, db_session)

        # Decode token to get user
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        # Simulate bearer token credentials
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=login_response.access_token
        )

        # Get current user
        current_user = await get_current_user(creds, db_session)

        assert current_user.id == registered_user.id
        assert current_user.email == user_data.email
        assert current_user.full_name == user_data.full_name

    async def test_get_current_user_invalid_token(self, db_session):
        """Test get_current_user with invalid token."""
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, db_session)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_current_user_expired_token(self, db_session):
        """Test get_current_user with expired token."""
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        # Create an expired token
        user_id = str(uuid4())
        expire = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": user_id,
            "email": "expired@example.com",
            "exp": expire,
        }
        expired_token = jwt.encode(
            payload,
            settings.SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )

        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=expired_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, db_session)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_current_user_nonexistent_user(self, db_session):
        """Test get_current_user when user doesn't exist in database."""
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        # Create a valid token for a non-existent user
        fake_user_id = str(uuid4())
        token = create_access_token(fake_user_id, "fake@example.com")

        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, db_session)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_current_user_inactive_user(self, db_session):
        """Test that inactive users fail authentication."""
        from app.api.v1.endpoints.auth import register, login, LoginRequest
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        # Create a user
        password = "SecurePassword123!"
        user_data = UserCreate(
            email="inactiveauth@example.com",
            password=password,
            full_name="Inactive Auth User",
        )
        await register(user_data, db_session)

        # Login to get token
        credentials = LoginRequest(email=user_data.email, password=password)
        login_response = await login(credentials, db_session)

        # Deactivate the user
        result = await db_session.execute(
            select(User).where(User.email == user_data.email)
        )
        user = result.scalar_one()
        user.is_active = False
        await db_session.commit()

        # Try to use the token
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=login_response.access_token
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(creds, db_session)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "inactive" in exc_info.value.detail.lower()


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestAuthenticationFlow:
    """Test the complete authentication flow end-to-end."""

    async def test_full_auth_flow(self, db_session):
        """Test complete flow: register -> login -> access protected resource."""
        from app.api.v1.endpoints.auth import register, login, get_me, LoginRequest
        from fastapi.security import HTTPAuthorizationCredentials
        from app.core.deps import get_current_user

        # Step 1: Register a new user
        password = "MySecurePassword123!"
        user_data = UserCreate(
            email="fullflow@example.com",
            password=password,
            full_name="Full Flow User",
            phone="9876543210",
            organization="Flow Test Org",
        )

        registered_user = await register(user_data, db_session)
        assert registered_user.email == user_data.email

        # Step 2: Login with credentials
        credentials = LoginRequest(
            email=user_data.email,
            password=password,
        )

        login_response = await login(credentials, db_session)
        assert login_response.access_token is not None

        # Step 3: Use token to access protected resource
        creds = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=login_response.access_token
        )

        current_user = await get_current_user(creds, db_session)
        assert current_user.id == registered_user.id
        assert current_user.email == user_data.email
        assert current_user.full_name == user_data.full_name
        assert current_user.organization == user_data.organization

        # Step 4: Call /me endpoint
        me_response = await get_me(current_user)
        assert me_response.id == registered_user.id
        assert me_response.email == user_data.email
