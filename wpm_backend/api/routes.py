"""API route definitions (login, portfolio endpoints)."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from starlette.requests import Request

from wpm.portfolio import CompositePortfolio
from wpm.pricing import PriceService

from wpm_backend.auth.auth import authenticate_user, create_access_token, verify_token
from wpm_backend.config import Settings, get_settings
from wpm_backend.models.auth import LoginRequest, LoginResponse
from wpm_backend.models.portfolio import PortfolioResponse
from wpm_backend.services.portfolio_service import get_all_positions

logger = logging.getLogger(__name__)

# OAuth2 scheme for JWT token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Create router
router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest, settings: Settings = Depends(get_settings)
) -> LoginResponse:
    """
    POST endpoint for user authentication.

    Validates credentials and returns JWT access token.

    Args:
        request: LoginRequest containing username and password
        settings: Application settings

    Returns:
        LoginResponse containing access_token and token_type

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    logger.info(f"Login request received for user: {request.username}")

    # Authenticate user
    if not authenticate_user(request.username, request.password, settings):
        logger.info(f"Login failed for user: {request.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": request.username}, settings=settings
    )

    logger.info(f"Login successful for user: {request.username}")
    return LoginResponse(access_token=access_token, token_type="bearer")


def get_current_user(
    token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)
) -> str:
    """
    Dependency function to extract and verify JWT token.

    Args:
        token: JWT token extracted from Authorization header
        settings: Application settings

    Returns:
        Username from token payload

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    username = verify_token(token, settings)
    if username is None:
        logger.info("Token verification failed in get_current_user")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


def get_composite_portfolio(request: Request) -> CompositePortfolio:
    """
    Dependency function to get composite portfolio from app state.

    Args:
        request: FastAPI Request object to access app.state

    Returns:
        CompositePortfolio instance from app state

    Raises:
        HTTPException: 500 if portfolio data is not available
    """
    portfolio = getattr(request.app.state, "composite_portfolio", None)
    if portfolio is None:
        logger.error("Composite portfolio not available in application state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Portfolio data not available",
        )
    return portfolio


def get_price_service(request: Request) -> PriceService:
    """
    Dependency function to get price service from app state.

    Args:
        request: FastAPI Request object to access app.state

    Returns:
        PriceService instance from app state

    Raises:
        HTTPException: 500 if price service is not available
    """
    price_service = getattr(request.app.state, "price_service", None)
    if price_service is None:
        logger.error("PriceService not available in application state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Price service not available",
        )
    return price_service


@router.get("/portfolio/all", response_model=PortfolioResponse)
def get_all_positions_endpoint(
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    price_service: PriceService = Depends(get_price_service),
) -> PortfolioResponse:
    """
    GET endpoint to retrieve all portfolio positions.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        price_service: Price service instance (injected via dependency)

    Returns:
        PortfolioResponse containing list of positions

    Raises:
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(f"Portfolio request received from user: {username}")

    # Get all positions
    positions = get_all_positions(composite_portfolio, price_service)

    logger.info(f"Portfolio response sent to user: {username}, positions: {len(positions)}")
    return PortfolioResponse(positions=positions)

