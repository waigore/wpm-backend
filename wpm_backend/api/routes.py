"""API route definitions (login, portfolio endpoints)."""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi_pagination import Page, Params, paginate
from fastapi.security import OAuth2PasswordBearer

from wpm.portfolio import CompositePortfolio, fetch_price_map
from wpm.pricing import PriceService

from wpm_backend.auth.auth import authenticate_user, create_access_token, verify_token
from wpm_backend.config import Settings, get_settings
from wpm_backend.models.auth import LoginRequest, LoginResponse
from wpm_backend.models.portfolio import PortfolioHistoryPoint, PortfolioPerformanceResponse, Position, PortfolioAllResponse, PortfolioAssetLotsResponse, PortfolioAssetTradesResponse
from wpm_backend.services.portfolio_service import get_all_positions, get_asset_lots, get_asset_trades, get_portfolio_performance, VALID_LOT_SORT_FIELDS, VALID_SORT_FIELDS, VALID_TRADE_SORT_FIELDS

logger = logging.getLogger(__name__)

# OAuth2 scheme for JWT token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def _parse_date_string(date_str: str, param_name: str) -> date:
    """
    Parse a date string from query parameters to a date object.
    
    Args:
        date_str: Date string in ISO format (YYYY-MM-DD)
        param_name: Name of the parameter (for error messages)
        
    Returns:
        date object
        
    Raises:
        HTTPException: 400 if date format is invalid
    """
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        logger.warning(f"Invalid {param_name} format: {date_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {param_name} format: {date_str}. Expected ISO format (YYYY-MM-DD)",
        )

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


@router.get("/portfolio/all", response_model=PortfolioAllResponse)
def get_all_positions_endpoint(
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    price_service: PriceService = Depends(get_price_service),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    sort_by: Optional[str] = Query("ticker", description="Field to sort by"),
    sort_order: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
) -> PortfolioAllResponse:
    """
    GET endpoint to retrieve all portfolio positions with pagination and sorting support.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        price_service: Price service instance (injected via dependency)
        page: Page number (1-indexed, default: 1)
        size: Number of items per page (default: 20, max: 100)
        sort_by: Field to sort by (default: "ticker")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        PortfolioAllResponse containing paginated list of positions and portfolio totals

    Raises:
        HTTPException: 400 if sort_by field is invalid
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Portfolio request received from user: {username}, page={page}, size={size}, "
        f"sort_by={sort_by}, sort_order={sort_order}"
    )

    # Validate sort_by parameter
    if sort_by is not None and sort_by not in VALID_SORT_FIELDS:
        logger.warning(f"Invalid sort_by field requested: {sort_by}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_SORT_FIELDS)}",
        )

    try:
        # Fetch price map for portfolio totals (needed for get_total_market_value and get_total_unrealized_pnl)
        logger.info("Fetching price map for portfolio totals")
        price_map = fetch_price_map(composite_portfolio, price_service)
        
        # Get all positions with sorting applied
        positions = get_all_positions(
            composite_portfolio, price_service, sort_by=sort_by, sort_order=sort_order
        )

        # Apply pagination with explicit page and size
        paginated_result = paginate(positions, params=Params(page=page, size=size))

        # Get portfolio totals from composite portfolio (pass price_map for methods that need it)
        total_cost_basis = composite_portfolio.get_total_cost_basis()
        total_market_value = composite_portfolio.get_total_market_value(price_map)
        total_unrealized_gain_loss = composite_portfolio.get_total_unrealized_pnl(price_map)

        logger.info(
            f"Portfolio response sent to user: {username}, "
            f"total={paginated_result.total}, page={paginated_result.page}, "
            f"size={paginated_result.size}, pages={paginated_result.pages}, "
            f"total_cost_basis={total_cost_basis}, total_market_value={total_market_value}, "
            f"total_unrealized_gain_loss={total_unrealized_gain_loss}"
        )

        return PortfolioAllResponse(
            positions=paginated_result,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_gain_loss=total_unrealized_gain_loss,
        )
    except ValueError as e:
        # Handle invalid sort_by from service layer
        logger.warning(f"Invalid sort parameter: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/portfolio/trades/{ticker}", response_model=PortfolioAssetTradesResponse)
def get_asset_trades_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    start_date: Optional[str] = Query(None, description="Start date for filtering (ISO format YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (ISO format YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("date", description="Field to sort by"),
    sort_order: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
) -> PortfolioAssetTradesResponse:
    """
    GET endpoint to retrieve all trades for a specific asset ticker with pagination, date filtering, and sorting support.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        page: Page number (1-indexed, default: 1)
        size: Number of items per page (default: 20, max: 100)
        start_date: Optional start date for filtering trades (ISO format YYYY-MM-DD, inclusive)
        end_date: Optional end date for filtering trades (ISO format YYYY-MM-DD, inclusive)
        sort_by: Field to sort by (default: "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        PortfolioAssetTradesResponse containing paginated list of trades

    Raises:
        HTTPException: 400 if date format is invalid, start_date > end_date, or sort_by field is invalid
        HTTPException: 404 if ticker is not found
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Asset trades request received from user: {username}, ticker={ticker}, "
        f"page={page}, size={size}, start_date={start_date}, end_date={end_date}, "
        f"sort_by={sort_by}, sort_order={sort_order}"
    )

    # Parse and validate date parameters
    start_date_obj = None
    end_date_obj = None

    if start_date is not None:
        start_date_obj = _parse_date_string(start_date, "start_date")

    if end_date is not None:
        end_date_obj = _parse_date_string(end_date, "end_date")

    # Validate date range
    if start_date_obj is not None and end_date_obj is not None:
        if start_date_obj > end_date_obj:
            logger.warning(f"Invalid date range: start_date={start_date_obj} > end_date={end_date_obj}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"start_date ({start_date_obj}) must be less than or equal to end_date ({end_date_obj})",
            )

    # Validate sort_by parameter
    if sort_by is not None and sort_by not in VALID_TRADE_SORT_FIELDS:
        logger.warning(f"Invalid sort_by field requested: {sort_by}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_TRADE_SORT_FIELDS)}",
        )

    try:
        # Get trades with date filtering and sorting
        trades = get_asset_trades(
            composite_portfolio,
            ticker,
            start_date=start_date_obj,
            end_date=end_date_obj,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Apply pagination
        paginated_result = paginate(trades, params=Params(page=page, size=size))

        logger.info(
            f"Asset trades response sent to user: {username}, ticker={ticker}, "
            f"total={paginated_result.total}, page={paginated_result.page}, "
            f"size={paginated_result.size}, pages={paginated_result.pages}"
        )

        return PortfolioAssetTradesResponse(trades=paginated_result)
    except ValueError as e:
        # Handle ticker not found, invalid sort_by, or other value errors
        logger.warning(f"Error retrieving trades for ticker {ticker}: {e}")
        # Check if it's a sort_by validation error
        if "Invalid sort_by field" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving trades for ticker {ticker}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error while retrieving trades for ticker {ticker}",
        )


@router.get("/portfolio/lots/{ticker}", response_model=PortfolioAssetLotsResponse)
def get_asset_lots_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    price_service: PriceService = Depends(get_price_service),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    start_date: Optional[str] = Query(None, description="Start date for filtering (ISO format YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (ISO format YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("date", description="Field to sort by"),
    sort_order: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
) -> PortfolioAssetLotsResponse:
    """
    GET endpoint to retrieve all lots for a specific asset ticker with pagination, date filtering, and sorting support.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        price_service: Price service instance (injected via dependency)
        page: Page number (1-indexed, default: 1)
        size: Number of items per page (default: 20, max: 100)
        start_date: Optional start date for filtering lots (ISO format YYYY-MM-DD, inclusive)
        end_date: Optional end date for filtering lots (ISO format YYYY-MM-DD, inclusive)
        sort_by: Field to sort by (default: "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        PortfolioAssetLotsResponse containing paginated list of lots

    Raises:
        HTTPException: 400 if date format is invalid, start_date > end_date, or sort_by field is invalid
        HTTPException: 404 if ticker is not found
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Asset lots request received from user: {username}, ticker={ticker}, "
        f"page={page}, size={size}, start_date={start_date}, end_date={end_date}, "
        f"sort_by={sort_by}, sort_order={sort_order}"
    )

    # Parse and validate date parameters
    start_date_obj = None
    end_date_obj = None

    if start_date is not None:
        start_date_obj = _parse_date_string(start_date, "start_date")

    if end_date is not None:
        end_date_obj = _parse_date_string(end_date, "end_date")

    # Validate date range
    if start_date_obj is not None and end_date_obj is not None:
        if start_date_obj > end_date_obj:
            logger.warning(f"Invalid date range: start_date={start_date_obj} > end_date={end_date_obj}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"start_date ({start_date_obj}) must be less than or equal to end_date ({end_date_obj})",
            )

    # Validate sort_by parameter
    if sort_by is not None and sort_by not in VALID_LOT_SORT_FIELDS:
        logger.warning(f"Invalid sort_by field requested: {sort_by}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_LOT_SORT_FIELDS)}",
        )

    try:
        # Get lots with date filtering and sorting
        lots = get_asset_lots(
            composite_portfolio,
            ticker,
            price_service,
            start_date=start_date_obj,
            end_date=end_date_obj,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Apply pagination
        paginated_result = paginate(lots, params=Params(page=page, size=size))

        logger.info(
            f"Asset lots response sent to user: {username}, ticker={ticker}, "
            f"total={paginated_result.total}, page={paginated_result.page}, "
            f"size={paginated_result.size}, pages={paginated_result.pages}"
        )

        return PortfolioAssetLotsResponse(lots=paginated_result)
    except ValueError as e:
        # Handle ticker not found, invalid sort_by, or other value errors
        logger.warning(f"Error retrieving lots for ticker {ticker}: {e}")
        # Check if it's a sort_by validation error
        if "Invalid sort_by field" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving lots for ticker {ticker}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error while retrieving lots for ticker {ticker}",
        )


def get_historical_portfolio(request: Request) -> CompositePortfolio:
    """
    Dependency function to get historical portfolio from app state.

    Args:
        request: FastAPI Request object to access app.state

    Returns:
        Historical CompositePortfolio instance from app state

    Raises:
        HTTPException: 500 if historical portfolio is not available
    """
    portfolio = getattr(request.app.state, "historical_portfolio", None)
    if portfolio is None:
        logger.error("Historical portfolio not available in application state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Historical portfolio data not available",
        )
    return portfolio


@router.get("/portfolio/all/performance", response_model=PortfolioPerformanceResponse)
def get_portfolio_performance_endpoint(
    username: str = Depends(get_current_user),
    historical_portfolio: CompositePortfolio = Depends(get_historical_portfolio),
    price_service: PriceService = Depends(get_price_service),
    end_date: Optional[str] = Query(None, description="End date for performance tracking (ISO format YYYY-MM-DD)"),
) -> PortfolioPerformanceResponse:
    """
    GET endpoint to retrieve historical portfolio performance data.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        historical_portfolio: Historical composite portfolio instance (injected via dependency)
        price_service: Price service instance (injected via dependency)
        end_date: Optional end date for performance tracking (ISO format YYYY-MM-DD, defaults to today)

    Returns:
        PortfolioPerformanceResponse containing list of PortfolioHistoryPoint objects

    Raises:
        HTTPException: 400 if date format is invalid or date range is invalid
        HTTPException: 500 if historical portfolio is not available
    """
    logger.info(
        f"Portfolio performance request received from user: {username}, end_date={end_date}"
    )
    
    # Get start_date from portfolio
    start_date_obj = historical_portfolio.start_date
    if start_date_obj is None:
        logger.warning("Portfolio has no start_date, cannot retrieve performance data")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio has no start date (no trades found)",
        )
    
    # Parse end_date if provided, default to today if not provided
    if end_date is not None:
        end_date_obj = _parse_date_string(end_date, "end_date")
    else:
        end_date_obj = date.today()
    
    # Validate date range
    if end_date_obj < start_date_obj:
        logger.warning(f"Invalid date range: end_date={end_date_obj} < start_date={start_date_obj}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"end_date ({end_date_obj}) must be greater than or equal to start_date ({start_date_obj})",
        )
    
    try:
        # Get portfolio performance
        history_points = get_portfolio_performance(
            historical_portfolio,
            price_service,
            start_date_obj,
            end_date_obj,
        )
        
        logger.info(
            f"Portfolio performance response sent to user: {username}, "
            f"history_points_count={len(history_points)}, start_date={start_date_obj}, end_date={end_date_obj}"
        )
        
        return PortfolioPerformanceResponse(history_points=history_points)
    except ValueError as e:
        # Handle invalid date range or other value errors
        logger.warning(f"Error retrieving portfolio performance: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving portfolio performance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving portfolio performance",
        )

