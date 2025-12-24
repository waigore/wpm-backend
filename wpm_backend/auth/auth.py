"""User authentication logic and login endpoint handler."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from wpm_backend.config import Settings

logger = logging.getLogger(__name__)


def authenticate_user(username: str, password: str, settings: Settings) -> bool:
    """
    Validate provided credentials against settings.

    Args:
        username: Username to validate
        password: Password to validate
        settings: Application settings containing credentials

    Returns:
        True if credentials match, False otherwise
    """
    logger.info(f"Authentication attempt for user: {username}")
    is_valid = username == settings.username and password == settings.password
    if is_valid:
        logger.info(f"Authentication successful for user: {username}")
    else:
        logger.info(f"Authentication failed for user: {username}")
    return is_valid


def create_access_token(
    data: dict, settings: Settings, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a JWT access token.

    Args:
        data: Dictionary containing token payload data (should include 'sub' for username)
        settings: Application settings containing secret key and algorithm
        expires_delta: Optional timedelta for token expiry. If None, uses default from settings.

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    username = data.get("sub", "unknown")
    logger.info(f"Access token created for user: {username}, expires at: {expire}")
    return encoded_jwt


def verify_token(token: str, settings: Settings) -> Optional[str]:
    """
    Verify JWT token signature and expiry, extract username from token payload.

    Args:
        token: JWT token string to verify
        settings: Application settings containing secret key and algorithm

    Returns:
        Username if token is valid, None if token is invalid or expired
    """
    try:
        logger.info("Token verification attempt")
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            logger.info("Token verification failed: missing 'sub' claim")
            return None
        logger.info(f"Token verification successful for user: {username}")
        return username
    except JWTError as e:
        logger.debug(f"Token verification failed: {e}")
        return None

