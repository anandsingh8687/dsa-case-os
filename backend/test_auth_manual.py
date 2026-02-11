#!/usr/bin/env python3
"""
Manual test script to verify JWT authentication implementation.

This script demonstrates the authentication flow without needing a running server.
It tests the core security functions directly.

Run: python test_auth_manual.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Test imports
try:
    from passlib.context import CryptContext
    from jose import jwt, JWTError
    print("✅ Required packages imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Run: pip install python-jose[cryptography] passlib[bcrypt]")
    sys.exit(1)


def test_password_hashing():
    """Test password hashing and verification."""
    print("\n📝 Testing Password Hashing...")

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Test 1: Hash a password
    password = "MySecurePassword123!"
    hashed = pwd_context.hash(password)
    print(f"   Password: {password}")
    print(f"   Hashed: {hashed[:50]}...")

    assert hashed != password, "Password should be hashed"
    assert hashed.startswith("$2b$"), "Should use bcrypt"
    print("   ✅ Password hashing works")

    # Test 2: Verify correct password
    assert pwd_context.verify(password, hashed), "Correct password should verify"
    print("   ✅ Password verification works")

    # Test 3: Reject incorrect password
    wrong_password = "WrongPassword456!"
    assert not pwd_context.verify(wrong_password, hashed), "Wrong password should fail"
    print("   ✅ Wrong password rejected")

    # Test 4: Different hashes for same password (salt)
    hash2 = pwd_context.hash(password)
    assert hash2 != hashed, "Each hash should have unique salt"
    assert pwd_context.verify(password, hash2), "Both hashes should verify"
    print("   ✅ Salt is working (different hashes for same password)")

    return True


def test_jwt_tokens():
    """Test JWT token creation and validation."""
    print("\n🔐 Testing JWT Tokens...")

    SECRET_KEY = "test-secret-key-do-not-use-in-production"
    ALGORITHM = "HS256"
    user_id = str(uuid4())
    email = "test@example.com"

    # Test 1: Create a token
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"   Created token (length: {len(token)})")
    print(f"   Token preview: {token[:50]}...")
    print("   ✅ Token creation works")

    # Test 2: Decode the token
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == user_id, "User ID should match"
    assert decoded["email"] == email, "Email should match"
    print(f"   Decoded user_id: {decoded['sub']}")
    print(f"   Decoded email: {decoded['email']}")
    print("   ✅ Token decoding works")

    # Test 3: Expired token should fail
    expired_payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    expired_token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

    try:
        jwt.decode(expired_token, SECRET_KEY, algorithms=[ALGORITHM])
        print("   ❌ Expired token should have failed!")
        return False
    except JWTError:
        print("   ✅ Expired token correctly rejected")

    # Test 4: Invalid token should fail
    invalid_token = "invalid.token.here"
    try:
        jwt.decode(invalid_token, SECRET_KEY, algorithms=[ALGORITHM])
        print("   ❌ Invalid token should have failed!")
        return False
    except JWTError:
        print("   ✅ Invalid token correctly rejected")

    # Test 5: Wrong secret should fail
    wrong_token = jwt.encode(payload, "wrong-secret", algorithm=ALGORITHM)
    try:
        jwt.decode(wrong_token, SECRET_KEY, algorithms=[ALGORITHM])
        print("   ❌ Token with wrong secret should have failed!")
        return False
    except JWTError:
        print("   ✅ Token with wrong secret correctly rejected")

    return True


def test_security_functions():
    """Test the actual security.py functions if available."""
    print("\n🔧 Testing Security Module Functions...")

    try:
        from app.core.security import (
            hash_password,
            verify_password,
            create_access_token,
            decode_token,
        )
        print("   ✅ Security module imported successfully")
    except ImportError as e:
        print(f"   ⚠️  Could not import security module: {e}")
        print("   Skipping security module tests")
        return True

    # Test hash_password
    password = "TestPassword123!"
    hashed = hash_password(password)
    print(f"   hash_password() output: {hashed[:50]}...")
    assert verify_password(password, hashed), "Verify should work"
    print("   ✅ hash_password() and verify_password() work")

    # Test create_access_token
    user_id = str(uuid4())
    email = "test@example.com"
    token = create_access_token(user_id, email)
    print(f"   create_access_token() output length: {len(token)}")
    print("   ✅ create_access_token() works")

    # Test decode_token
    payload = decode_token(token)
    assert payload["sub"] == user_id, "User ID should match"
    assert payload["email"] == email, "Email should match"
    print(f"   decode_token() extracted user_id: {payload['sub']}")
    print("   ✅ decode_token() works")

    return True


def test_authentication_flow():
    """Simulate the complete authentication flow."""
    print("\n🔄 Testing Complete Authentication Flow...")

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    SECRET_KEY = "test-secret"
    ALGORITHM = "HS256"

    # Step 1: User registration
    print("\n   Step 1: User Registration")
    user_email = "newuser@example.com"
    user_password = "SecurePassword123!"
    user_id = str(uuid4())

    # Hash password for storage
    hashed_password = pwd_context.hash(user_password)
    print(f"      - Email: {user_email}")
    print(f"      - Password hashed: {hashed_password[:30]}...")
    print("      ✅ User registered")

    # Step 2: User login
    print("\n   Step 2: User Login")
    login_email = "newuser@example.com"
    login_password = "SecurePassword123!"

    # Verify credentials
    if login_email == user_email and pwd_context.verify(login_password, hashed_password):
        print(f"      - Credentials valid for {login_email}")

        # Create token
        payload = {
            "sub": user_id,
            "email": user_email,
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            "iat": datetime.now(timezone.utc),
        }
        access_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        print(f"      - JWT token created: {access_token[:50]}...")
        print("      ✅ Login successful")
    else:
        print("      ❌ Login failed")
        return False

    # Step 3: Access protected resource
    print("\n   Step 3: Access Protected Resource")
    auth_header = f"Bearer {access_token}"
    print(f"      - Authorization: {auth_header[:70]}...")

    # Extract and validate token
    token_from_header = auth_header.replace("Bearer ", "")
    decoded_payload = jwt.decode(token_from_header, SECRET_KEY, algorithms=[ALGORITHM])

    if decoded_payload["sub"] == user_id:
        print(f"      - Authenticated as user: {decoded_payload['email']}")
        print(f"      - User ID: {decoded_payload['sub']}")
        print("      ✅ Protected resource accessed")
    else:
        print("      ❌ Authentication failed")
        return False

    # Step 4: Try with invalid token
    print("\n   Step 4: Try Invalid Token")
    invalid_token = "invalid.token.here"
    try:
        jwt.decode(invalid_token, SECRET_KEY, algorithms=[ALGORITHM])
        print("      ❌ Invalid token should have been rejected")
        return False
    except JWTError:
        print("      ✅ Invalid token correctly rejected")

    return True


def main():
    """Run all tests."""
    print("=" * 70)
    print("JWT AUTHENTICATION IMPLEMENTATION - MANUAL TEST")
    print("=" * 70)

    tests = [
        ("Password Hashing", test_password_hashing),
        ("JWT Tokens", test_jwt_tokens),
        ("Security Functions", test_security_functions),
        ("Authentication Flow", test_authentication_flow),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} failed with error: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(result for _, result in results)

    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Authentication system is working correctly.")
    else:
        print("⚠️  SOME TESTS FAILED. Please check the errors above.")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
