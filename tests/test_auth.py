"""Unit and integration tests for authentication module."""

import time
from datetime import timedelta

import pytest
from jose import jwt

from wpm_backend.auth.auth import authenticate_user, create_access_token, verify_token
from wpm_backend.config import Settings


def test_authenticate_user_valid_credentials(test_settings):
    """Test authenticate_user() with valid credentials."""
    result = authenticate_user("testuser", "testpass", test_settings)
    assert result is True


def test_authenticate_user_invalid_username(test_settings):
    """Test authenticate_user() with invalid username."""
    result = authenticate_user("wronguser", "testpass", test_settings)
    assert result is False


def test_authenticate_user_invalid_password(test_settings):
    """Test authenticate_user() with invalid password."""
    result = authenticate_user("testuser", "wrongpass", test_settings)
    assert result is False


def test_create_access_token(test_settings):
    """Test JWT token generation with correct payload structure."""
    data = {"sub": "testuser"}
    token = create_access_token(data, test_settings)

    # Decode token to verify structure
    payload = jwt.decode(
        token, test_settings.secret_key, algorithms=[test_settings.algorithm]
    )

    assert payload["sub"] == "testuser"
    assert "exp" in payload
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]


def test_create_access_token_with_custom_expiry(test_settings):
    """Test JWT token generation with custom expiry."""
    data = {"sub": "testuser"}
    expires_delta = timedelta(minutes=30)
    token = create_access_token(data, test_settings, expires_delta=expires_delta)

    payload = jwt.decode(
        token, test_settings.secret_key, algorithms=[test_settings.algorithm]
    )

    # Check that expiry is approximately 30 minutes from now
    expected_exp = int(time.time()) + 30 * 60
    actual_exp = payload["exp"]
    # Allow 5 second tolerance
    assert abs(actual_exp - expected_exp) < 5


def test_verify_token_valid(test_settings):
    """Test token verification with valid token."""
    data = {"sub": "testuser"}
    token = create_access_token(data, test_settings)

    username = verify_token(token, test_settings)
    assert username == "testuser"


def test_verify_token_invalid_signature(test_settings):
    """Test token verification with invalid signature."""
    # Create token with different secret key
    wrong_settings = Settings(
        username="testuser",
        password="testpass",
        secret_key="wrong-secret-key-for-testing-purposes-only-minimum-32",
        algorithm="HS256",
        access_token_expire_minutes=60,
        import_dir="import",
        log_level="INFO",
        log_dir="logs",
    )

    data = {"sub": "testuser"}
    token = create_access_token(data, wrong_settings)

    # Try to verify with correct secret key
    username = verify_token(token, test_settings)
    assert username is None


def test_verify_token_expired(test_settings):
    """Test token verification with expired token."""
    # Create token with very short expiry
    data = {"sub": "testuser"}
    expires_delta = timedelta(seconds=-1)  # Already expired
    token = create_access_token(data, test_settings, expires_delta=expires_delta)

    # Wait a bit to ensure it's expired
    time.sleep(1)

    username = verify_token(token, test_settings)
    assert username is None


def test_verify_token_missing_sub(test_settings):
    """Test token verification with missing 'sub' claim."""
    # Create token without 'sub' claim
    data = {}
    token = create_access_token(data, test_settings)

    username = verify_token(token, test_settings)
    assert username is None


def test_login_endpoint_success(client, test_settings):
    """Test login endpoint with valid credentials."""
    response = client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify token is valid
    token = data["access_token"]
    username = verify_token(token, test_settings)
    assert username == "testuser"


def test_login_endpoint_invalid_credentials(client):
    """Test login endpoint with invalid credentials."""
    response = client.post(
        "/login",
        json={"username": "wronguser", "password": "wrongpass"},
    )

    assert response.status_code == 401
    assert "detail" in response.json()


def test_login_endpoint_missing_fields(client):
    """Test login endpoint with missing fields."""
    response = client.post(
        "/login",
        json={"username": "testuser"},
    )

    assert response.status_code == 422  # Validation error


def test_protected_endpoint_with_valid_token(client_with_portfolio, test_settings):
    """Test protected endpoint access with valid token."""
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Access protected endpoint
    response = client_with_portfolio.get(
        "/portfolio/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert "total_count" in data


def test_protected_endpoint_without_token(client_with_portfolio):
    """Test protected endpoint access without token."""
    response = client_with_portfolio.get("/portfolio/all")

    assert response.status_code == 401


def test_protected_endpoint_with_invalid_token(client_with_portfolio):
    """Test protected endpoint access with invalid token."""
    response = client_with_portfolio.get(
        "/portfolio/all",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_protected_endpoint_with_expired_token(client_with_portfolio, test_settings):
    """Test protected endpoint access with expired token."""
    # Create expired token
    data = {"sub": "testuser"}
    expires_delta = timedelta(seconds=-1)
    expired_token = create_access_token(data, test_settings, expires_delta=expires_delta)

    time.sleep(1)

    response = client_with_portfolio.get(
        "/portfolio/all",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401

