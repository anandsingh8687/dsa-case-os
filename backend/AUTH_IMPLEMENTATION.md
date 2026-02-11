# JWT Authentication Implementation Guide

## Overview

This document explains the JWT-based authentication system implemented for the DSA Case OS platform.

## Architecture

The authentication system consists of the following components:

### 1. **Security Module** (`app/core/security.py`)
Handles password hashing and JWT token management:
- `hash_password(plain)` - Hash passwords using bcrypt
- `verify_password(plain, hashed)` - Verify password against hash
- `create_access_token(user_id, email)` - Generate JWT access tokens
- `decode_token(token)` - Decode and validate JWT tokens

### 2. **User Model** (`app/models/user.py`)
SQLAlchemy model for the users table with fields:
- `id` - UUID primary key
- `email` - Unique email address
- `hashed_password` - Bcrypt hashed password
- `full_name` - User's full name
- `role` - User role (default: "dsa")
- `is_active` - Account status
- Other fields: phone, organization, timestamps

### 3. **Auth Dependency** (`app/core/deps.py`)
FastAPI dependency for protecting routes:
- `get_current_user` - Extracts JWT from Authorization header, validates it, and returns the authenticated user
- Can be used as: `current_user: Annotated[User, Depends(get_current_user)]`

### 4. **Auth Endpoints** (`app/api/v1/endpoints/auth.py`)
Three main endpoints:
- `POST /auth/register` - Register new users
- `POST /auth/login` - Login and get access token
- `GET /auth/me` - Get current user info (requires auth)

## Usage Examples

### Registering a New User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!",
    "full_name": "John Doe",
    "phone": "1234567890",
    "organization": "ABC Corp"
  }'
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "dsa",
  "is_active": true,
  "created_at": "2024-02-10T10:00:00Z"
}
```

### Logging In

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Accessing Protected Routes

```bash
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "dsa",
  "is_active": true,
  "created_at": "2024-02-10T10:00:00Z"
}
```

## Protecting Your Routes

To protect any route with authentication, add the `get_current_user` dependency:

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/protected-resource")
async def get_protected_resource(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """This route requires authentication."""
    return {
        "message": f"Hello {current_user.full_name}!",
        "user_id": current_user.id
    }
```

Or use the type alias:

```python
from app.core.deps import CurrentUser

@router.get("/protected-resource")
async def get_protected_resource(current_user: CurrentUser):
    """This route requires authentication."""
    return {"user_id": current_user.id}
```

## Configuration

Authentication settings are configured in `app/core/config.py`:

```python
# Auth
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
JWT_ALGORITHM: str = "HS256"
```

**⚠️ IMPORTANT**: Always set a strong `SECRET_KEY` in production via environment variable!

## Token Structure

JWT tokens contain the following payload:
```json
{
  "sub": "user-uuid",           # Subject (user ID)
  "email": "user@example.com",  # User email
  "exp": 1234567890,            # Expiration timestamp
  "iat": 1234567890             # Issued at timestamp
}
```

## Security Features

1. **Password Security**
   - Passwords are hashed using bcrypt with automatic salt
   - Plain text passwords are never stored

2. **Token Security**
   - Tokens are signed with HS256 algorithm
   - Tokens expire after 24 hours (configurable)
   - Tokens include issued-at timestamp

3. **User Validation**
   - Email uniqueness is enforced
   - Inactive users cannot login or access protected routes
   - Invalid/expired tokens return 401 Unauthorized

4. **Error Handling**
   - 400 Bad Request: Email already registered
   - 401 Unauthorized: Invalid credentials or token
   - 403 Forbidden: Inactive user account

## Testing

Run the comprehensive test suite:

```bash
cd backend
pytest tests/test_auth.py -v
```

Tests cover:
- Password hashing and verification
- JWT token creation and validation
- User registration (including duplicate email handling)
- User login (correct/incorrect credentials, inactive users)
- Protected route access (valid/invalid/expired tokens)
- Complete authentication flow (register → login → access)

## Database Setup

The users table is defined in `backend/app/db/schema.sql`:

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(15),
    full_name       VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(512) NOT NULL,
    role            VARCHAR(20) DEFAULT 'dsa',
    organization    VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

## Next Steps

To integrate authentication with your existing endpoints:

1. Import the dependency:
   ```python
   from app.core.deps import CurrentUser
   ```

2. Add it to your route:
   ```python
   @router.get("/cases")
   async def list_cases(current_user: CurrentUser):
       # current_user is automatically injected
       # Access user info: current_user.id, current_user.email, etc.
   ```

3. Filter queries by user:
   ```python
   cases = await db.execute(
       select(Case).where(Case.user_id == current_user.id)
   )
   ```

## Dependencies

Required packages (already in requirements.txt):
- `python-jose[cryptography]` - JWT token handling
- `passlib[bcrypt]` - Password hashing

## Security Best Practices

1. **Always use HTTPS in production** - Tokens should never be transmitted over HTTP
2. **Rotate SECRET_KEY regularly** in production
3. **Set appropriate token expiration** based on your security requirements
4. **Implement token refresh** for long-lived sessions (future enhancement)
5. **Add rate limiting** to login endpoints to prevent brute force attacks
6. **Log authentication events** for security auditing
7. **Implement password strength requirements** in production

## Troubleshooting

### "Could not validate credentials" error
- Check that the Authorization header is properly formatted: `Bearer <token>`
- Verify the token hasn't expired
- Ensure the SECRET_KEY matches between token creation and validation

### "Email already registered" error
- The email address is already in use
- Use a different email or implement password reset functionality

### "User account is inactive" error
- The user's `is_active` field is set to `false`
- Reactivate the user in the database or contact an administrator
