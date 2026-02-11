# JWT Authentication - Quick Start Guide

## ✅ What's Been Implemented

A complete JWT-based authentication system with:
- User registration with email/password
- Login with JWT token generation
- Protected routes using JWT validation
- Password hashing with bcrypt
- Comprehensive test suite

## 🚀 Quick Start

### 1. Install Dependencies

The required packages are already in `requirements.txt`:
- `python-jose[cryptography]` - JWT handling
- `passlib[bcrypt]` - Password hashing

If needed, install them:
```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

### 2. Set Environment Variables

Create a `.env` file in the backend directory:
```bash
SECRET_KEY=your-super-secret-key-change-this-in-production
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/dsa_case_os
```

⚠️ **IMPORTANT**: Use a strong, random SECRET_KEY in production!

### 3. Database Setup

The users table should already exist from the schema file. If not, apply the migration:
```bash
psql -U postgres -d dsa_case_os -f app/db/schema.sql
```

### 4. Test the Implementation

Run the manual test script:
```bash
cd backend
python test_auth_manual.py
```

Expected output:
```
✅ PASS: Password Hashing
✅ PASS: JWT Tokens
✅ PASS: Authentication Flow
🎉 ALL TESTS PASSED!
```

### 5. Start the Server

```bash
cd backend
uvicorn app.main:app --reload
```

### 6. Try the API

#### Register a new user:
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePassword123!",
    "full_name": "Test User"
  }'
```

#### Login:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "SecurePassword123!"
  }'
```

You'll get a response like:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### Access protected endpoint:
```bash
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 📖 Documentation

- **Full Implementation Guide**: `AUTH_IMPLEMENTATION.md`
- **Usage Examples**: `example_protected_route.py`
- **Implementation Summary**: `../IMPLEMENTATION_SUMMARY.md`

## 🔐 Protect Your Routes

Add authentication to any route:

```python
from app.core.deps import CurrentUser

@router.get("/my-cases")
async def list_my_cases(current_user: CurrentUser):
    # current_user is automatically injected
    # Access: current_user.id, current_user.email, current_user.role
    return {"user_id": str(current_user.id)}
```

## 🧪 Run Tests

```bash
cd backend
pytest tests/test_auth.py -v
```

## 📁 Files Created

| File | Purpose |
|------|---------|
| `app/core/security.py` | Password hashing & JWT functions |
| `app/core/deps.py` | Auth dependency for routes |
| `app/models/user.py` | User SQLAlchemy model |
| `app/api/v1/endpoints/auth.py` | Register, login, /me endpoints |
| `tests/test_auth.py` | Comprehensive test suite |
| `AUTH_IMPLEMENTATION.md` | Complete documentation |
| `example_protected_route.py` | Usage examples |

## ❓ Troubleshooting

### "Could not validate credentials"
- Check that the token is valid and not expired
- Ensure the Authorization header format: `Bearer <token>`
- Verify SECRET_KEY is the same for token creation and validation

### "Email already registered"
- Use a different email
- Or delete the existing user from the database

### Import errors
- Make sure all dependencies are installed
- Check that you're in the backend directory

## 🎯 Next Steps

1. Protect your existing endpoints by adding `current_user: CurrentUser`
2. Filter database queries by `current_user.id`
3. Add role-based access control for admin features
4. Set up HTTPS in production
5. Implement rate limiting on auth endpoints

---

**Status**: ✅ Ready to use!
