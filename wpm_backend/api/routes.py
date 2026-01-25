"""API route definitions (login, portfolio endpoints)."""

import logging
import re
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi_pagination import Page, Params, paginate
from fastapi.security import OAuth2PasswordBearer

from wpm.asset import AssetService
from wpm.portfolio import CompositePortfolio, fetch_price_map
from wpm.pricing import PriceService

from wpm_backend.auth.auth import authenticate_user, create_access_token, verify_token
from wpm_backend.config import Settings, get_settings
from wpm_backend.models.auth import LoginRequest, LoginResponse
from wpm_backend.models.portfolio import AllocationPosition, AssetBrokersResponse, AssetMetadataAllResponse, AssetMetadataResponse, AssetPriceHistoryResponse, PortfolioAllocationResponse, PortfolioHistoryPoint, PortfolioPerformanceResponse, Position, PortfolioAllResponse, PortfolioAssetLotsResponse, PortfolioAssetTradesAllResponse, PortfolioAssetTradesResponse
from wpm_backend.services.portfolio_service import apply_granularity_filter, get_all_asset_metadata, get_all_positions, get_asset_brokers, get_asset_lots, get_asset_metadata, get_asset_positions_by_broker, get_asset_price_history, get_asset_trades, get_cached_portfolio_performance, get_portfolio_allocation, get_portfolio_performance, VALID_LOT_SORT_FIELDS, VALID_SORT_FIELDS, VALID_TRADE_SORT_FIELDS

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


def get_asset_service(request: Request) -> AssetService:
    """
    Dependency function to get asset service from app state.

    Args:
        request: FastAPI Request object to access app.state

    Returns:
        AssetService instance from app state

    Raises:
        HTTPException: 500 if asset service is not available
    """
    asset_service = getattr(request.app.state, "asset_service", None)
    if asset_service is None:
        logger.error("AssetService not available in application state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Asset service not available",
        )
    return asset_service


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
        total_realized_gain_loss = composite_portfolio.get_total_realized_pnl()

        logger.info(
            f"Portfolio response sent to user: {username}, "
            f"total={paginated_result.total}, page={paginated_result.page}, "
            f"size={paginated_result.size}, pages={paginated_result.pages}, "
            f"total_cost_basis={total_cost_basis}, total_market_value={total_market_value}, "
            f"total_unrealized_gain_loss={total_unrealized_gain_loss}, "
            f"total_realized_gain_loss={total_realized_gain_loss}"
        )

        return PortfolioAllResponse(
            positions=paginated_result,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            total_unrealized_gain_loss=total_unrealized_gain_loss,
            total_realized_gain_loss=total_realized_gain_loss,
        )
    except ValueError as e:
        # Handle invalid sort_by from service layer
        logger.warning(f"Invalid sort parameter: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/portfolio/allocation", response_model=PortfolioAllocationResponse)
def get_portfolio_allocation_endpoint(
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    price_service: PriceService = Depends(get_price_service),
    asset_service: AssetService = Depends(get_asset_service),
    asset_types: Optional[str] = Query(None, description="Comma-separated list of asset types to filter by (e.g., 'Stock,ETF')"),
    tickers: Optional[str] = Query(None, description="Comma-separated list of ticker symbols to filter by (e.g., 'AAPL,GOOG')"),
) -> PortfolioAllocationResponse:
    """
    GET endpoint to retrieve filtered portfolio positions with metadata for allocation display.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        price_service: Price service instance (injected via dependency)
        asset_service: Asset service instance (injected via dependency)
        asset_types: Optional comma-separated list of asset types to filter by (e.g., "Stock,ETF")
        tickers: Optional comma-separated list of ticker symbols to filter by (e.g., "AAPL,GOOG")

    Returns:
        PortfolioAllocationResponse containing list of filtered positions with metadata

    Raises:
        HTTPException: 400 if parameter format is invalid
        HTTPException: 500 if portfolio or services are unavailable

    Note:
        Filtering uses OR logic: assets are included if they match any specified asset_type OR any specified ticker.
        Allocations are automatically recalculated against the filtered asset list only (sum to 100% of filtered assets).
    """
    logger.info(
        f"Portfolio allocation request received from user: {username}, "
        f"asset_types={asset_types}, tickers={tickers}"
    )

    # Parse comma-separated query parameters into lists
    asset_types_list = None
    if asset_types:
        asset_types_list = [at.strip() for at in asset_types.split(",") if at.strip()]
        if not asset_types_list:
            asset_types_list = None

    tickers_list = None
    if tickers:
        tickers_list = [t.strip() for t in tickers.split(",") if t.strip()]
        if not tickers_list:
            tickers_list = None

    try:
        # Get filtered positions with metadata
        assets = get_portfolio_allocation(
            composite_portfolio,
            price_service,
            asset_service,
            asset_types=asset_types_list,
            tickers=tickers_list,
        )

        logger.info(
            f"Portfolio allocation response sent to user: {username}, "
            f"assets_count={len(assets)}"
        )

        return PortfolioAllocationResponse(assets=assets)
    except Exception as e:
        logger.error(f"Unexpected error retrieving portfolio allocation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving portfolio allocation",
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


@router.get("/portfolio/trades/{ticker}/all", response_model=PortfolioAssetTradesAllResponse)
def get_asset_trades_all_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    start_date: Optional[str] = Query(None, description="Start date for filtering (ISO format YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for filtering (ISO format YYYY-MM-DD)"),
    sort_by: Optional[str] = Query("date", description="Field to sort by"),
    sort_order: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
) -> PortfolioAssetTradesAllResponse:
    """
    GET endpoint to retrieve all trades for a specific asset ticker without pagination, with date filtering and sorting support.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        start_date: Optional start date for filtering trades (ISO format YYYY-MM-DD, inclusive)
        end_date: Optional end date for filtering trades (ISO format YYYY-MM-DD, inclusive)
        sort_by: Field to sort by (default: "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        PortfolioAssetTradesAllResponse containing all trades (no pagination)

    Raises:
        HTTPException: 400 if date format is invalid, start_date > end_date, or sort_by field is invalid
        HTTPException: 404 if ticker is not found
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Asset trades (all) request received from user: {username}, ticker={ticker}, "
        f"start_date={start_date}, end_date={end_date}, "
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

        logger.info(
            f"Asset trades (all) response sent to user: {username}, ticker={ticker}, "
            f"total={len(trades)}"
        )

        return PortfolioAssetTradesAllResponse(trades=trades)
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
    brokers: Optional[str] = Query(None, description="Comma-separated list of broker names to filter by"),
    sort_by: Optional[str] = Query("date", description="Field to sort by"),
    sort_order: Optional[str] = Query("asc", pattern="^(asc|desc)$", description="Sort order: 'asc' or 'desc'"),
) -> PortfolioAssetLotsResponse:
    """
    GET endpoint to retrieve all lots for a specific asset ticker with pagination, date filtering, broker filtering, and sorting support.

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
        brokers: Optional comma-separated list of broker names to filter by
        sort_by: Field to sort by (default: "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        PortfolioAssetLotsResponse containing paginated list of lots, overall position, and per-broker positions

    Raises:
        HTTPException: 400 if date format is invalid, start_date > end_date, or sort_by field is invalid
        HTTPException: 404 if ticker is not found
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Asset lots request received from user: {username}, ticker={ticker}, "
        f"page={page}, size={size}, start_date={start_date}, end_date={end_date}, "
        f"brokers={brokers}, sort_by={sort_by}, sort_order={sort_order}"
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

    # Parse brokers parameter (comma-separated list)
    brokers_list = None
    if brokers:
        brokers_list = [b.strip() for b in brokers.split(",") if b.strip()]
        if not brokers_list:
            brokers_list = None

    # Validate sort_by parameter
    if sort_by is not None and sort_by not in VALID_LOT_SORT_FIELDS:
        logger.warning(f"Invalid sort_by field requested: {sort_by}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_LOT_SORT_FIELDS)}",
        )

    try:
        # Get lots with date filtering, broker filtering, and sorting
        lots = get_asset_lots(
            composite_portfolio,
            ticker,
            price_service,
            start_date=start_date_obj,
            end_date=end_date_obj,
            brokers=brokers_list,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # Get positions by broker (with broker filtering if provided)
        overall_position, per_broker_positions = get_asset_positions_by_broker(
            composite_portfolio,
            ticker,
            price_service,
            brokers=brokers_list,
        )

        # Apply pagination
        paginated_result = paginate(lots, params=Params(page=page, size=size))

        logger.info(
            f"Asset lots response sent to user: {username}, ticker={ticker}, "
            f"total={paginated_result.total}, page={paginated_result.page}, "
            f"size={paginated_result.size}, pages={paginated_result.pages}, "
            f"brokers={brokers_list}, overall_qty={overall_position.quantity}, "
            f"broker_positions={len(per_broker_positions)}"
        )

        return PortfolioAssetLotsResponse(
            lots=paginated_result,
            overall_position=overall_position,
            per_broker_positions=per_broker_positions,
        )
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


def get_performance_cache(request: Request) -> tuple[dict[str, PortfolioHistoryPoint], Optional[date]]:
    """
    Dependency function to get performance cache from app state.

    Args:
        request: FastAPI Request object to access app.state

    Returns:
        Tuple of (cache_dict, cache_end_date)

    Raises:
        HTTPException: 500 if performance cache is not available
    """
    cache = getattr(request.app.state, "performance_cache", None)
    cache_end_date = getattr(request.app.state, "performance_cache_end_date", None)
    if cache is None:
        logger.error("Performance cache not available in application state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Performance cache not available",
        )
    return cache, cache_end_date


def _handle_performance_error(
    error_str: str,
    cache: dict[str, PortfolioHistoryPoint],
    cache_end_date: Optional[date],
    historical_portfolio: CompositePortfolio,
    price_service: PriceService,
    start_date_obj: date,
    end_date_obj: date,
    granularity: str,
) -> Optional[PortfolioPerformanceResponse]:
    """
    Handle performance calculation errors with fallback strategies.
    
    Uses guard clauses to flatten nested conditionals and handle different error types.
    
    Args:
        error_str: Error message string
        cache: Performance cache dictionary
        cache_end_date: Maximum date in cache
        historical_portfolio: Historical portfolio instance
        price_service: Price service instance
        start_date_obj: Start date for performance calculation
        end_date_obj: End date for performance calculation
        granularity: Granularity level for filtering
        
    Returns:
        PortfolioPerformanceResponse if partial data can be returned, None otherwise
        
    Raises:
        HTTPException: For various error conditions that cannot be handled
    """
    # Guard: Handle invalid granularity errors
    if "Invalid granularity" in error_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_str,
        )
    
    # Guard: Handle cache-related errors
    if "exceeds maximum available date" in error_str or "cache_end_date is None" in error_str:
        if cache_end_date is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{error_str}. Maximum available date is {cache_end_date.isoformat()}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Performance cache is not available",
        )
    
    # Guard: Only attempt partial data recovery for historical price errors
    if "Historical prices unavailable" not in error_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_str,
        )
    
    # Handle historical prices unavailable error
    logger.error(f"Historical prices unavailable for requested date range: {error_str}")
    
    # Guard: Skip partial recovery if cache is available (use cache instead)
    if cache and cache_end_date is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot calculate portfolio performance: {error_str}. "
                   f"Some tickers may not have historical price data available for the requested date range. "
                   f"Please try a different date range or check that all tickers have price data available.",
        )
    
    # Try to extract problematic date from error message
    # Error format: "Historical prices unavailable for tickers on YYYY-MM-DD: TICKER1, TICKER2"
    date_match = re.search(r'on (\d{4}-\d{2}-\d{2})', error_str)
    if not date_match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot calculate portfolio performance: {error_str}. "
                   f"Some tickers may not have historical price data available for the requested date range. "
                   f"Please try a different date range or check that all tickers have price data available.",
        )
    
    problematic_date_str = date_match.group(1)
    try:
        problematic_date = date.fromisoformat(problematic_date_str)
    except (ValueError, AttributeError) as parse_e:
        logger.warning(f"Could not parse problematic date from error message: {parse_e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot calculate portfolio performance: {error_str}. "
                   f"Some tickers may not have historical price data available for the requested date range. "
                   f"Please try a different date range or check that all tickers have price data available.",
        )
    
    logger.info(
        f"Attempting to calculate performance by excluding problematic date {problematic_date_str}. "
        f"Will try date ranges: [{start_date_obj}, {problematic_date - timedelta(days=1)}] "
        f"and [{problematic_date + timedelta(days=1)}, {end_date_obj}]"
    )
    
    # Try to get performance data for dates before and after the problematic date
    history_points = []
    
    # Calculate performance before problematic date
    if start_date_obj < problematic_date:
        try:
            before_points = get_portfolio_performance(
                historical_portfolio,
                price_service,
                start_date_obj,
                problematic_date - timedelta(days=1),
            )
            history_points.extend(before_points)
            logger.info(f"Retrieved {len(before_points)} history points before problematic date {problematic_date_str}")
        except Exception as before_e:
            logger.warning(f"Could not calculate performance before {problematic_date_str}: {before_e}")
    
    # Calculate performance after problematic date
    if problematic_date < end_date_obj:
        try:
            after_points = get_portfolio_performance(
                historical_portfolio,
                price_service,
                problematic_date + timedelta(days=1),
                end_date_obj,
            )
            history_points.extend(after_points)
            logger.info(f"Retrieved {len(after_points)} history points after problematic date {problematic_date_str}")
        except Exception as after_e:
            logger.warning(f"Could not calculate performance after {problematic_date_str}: {after_e}")
    
    # Guard: If no data was retrieved, raise error
    if not history_points:
        logger.error(f"Could not calculate any performance data after excluding {problematic_date_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot calculate portfolio performance: {error_str}. "
                   f"Some tickers may not have historical price data available for the requested date range. "
                   f"Please try a different date range or check that all tickers have price data available.",
        )
    
    # Sort by date to ensure chronological order
    history_points.sort(key=lambda p: p.date)
    
    # Apply granularity filter
    filtered_points = apply_granularity_filter(
        history_points,
        start_date_obj,
        end_date_obj,
        granularity,
    )
    
    logger.warning(
        f"Returning partial portfolio performance data: {len(filtered_points)} points. "
        f"Data for date {problematic_date_str} was excluded due to missing prices. "
        f"Original error: {error_str}"
    )
    
    return PortfolioPerformanceResponse(history_points=filtered_points)


@router.get("/portfolio/all/performance", response_model=PortfolioPerformanceResponse)
def get_portfolio_performance_endpoint(
    username: str = Depends(get_current_user),
    historical_portfolio: CompositePortfolio = Depends(get_historical_portfolio),
    cache_data: tuple[dict[str, PortfolioHistoryPoint], Optional[date]] = Depends(get_performance_cache),
    price_service: PriceService = Depends(get_price_service),
    start_date: Optional[str] = Query(None, description="Start date for performance tracking (ISO format YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for performance tracking (ISO format YYYY-MM-DD)"),
    granularity: str = Query("daily", pattern="^(daily|weekly|monthly)$", description="Granularity of history points: 'daily' (default), 'weekly' (Monday-based), or 'monthly' (start of month)"),
) -> PortfolioPerformanceResponse:
    """
    GET endpoint to retrieve historical portfolio performance data.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        historical_portfolio: Historical composite portfolio instance (injected via dependency)
        cache_data: Performance cache and cache_end_date (injected via dependency)
        start_date: Optional start date for performance tracking (ISO format YYYY-MM-DD, defaults to portfolio start_date)
        end_date: Optional end date for performance tracking (ISO format YYYY-MM-DD, defaults to today)
        granularity: Granularity level - "daily" (default), "weekly" (Monday-based), or "monthly" (start of month)

    Returns:
        PortfolioPerformanceResponse containing filtered list of PortfolioHistoryPoint objects

    Raises:
        HTTPException: 400 if date format is invalid, date range is invalid, granularity is invalid, or end_date > cache_end_date
        HTTPException: 422 if granularity value is invalid (handled by FastAPI Query validation)
        HTTPException: 500 if historical portfolio or performance cache is not available
    """
    logger.info(
        f"Portfolio performance request received from user: {username}, start_date={start_date}, end_date={end_date}, granularity={granularity}"
    )
    
    # Unpack cache data
    cache, cache_end_date = cache_data
    
    # Validate cache is not empty
    if not cache:
        logger.error("Performance cache is empty")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Performance cache is empty",
        )
    
    # Get portfolio start_date
    portfolio_start_date = historical_portfolio.start_date
    if portfolio_start_date is None:
        logger.warning("Portfolio has no start_date, cannot retrieve performance data")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio has no start date (no trades found)",
        )
    
    # Parse start_date if provided, otherwise use portfolio start_date
    if start_date is not None:
        start_date_obj = _parse_date_string(start_date, "start_date")
    else:
        start_date_obj = portfolio_start_date
    
    # Parse end_date if provided, default to today if not provided
    if end_date is not None:
        end_date_obj = _parse_date_string(end_date, "end_date")
    else:
        end_date_obj = date.today()
    
    # Clamp dates to portfolio start_date if they are before it (no error thrown)
    if start_date_obj < portfolio_start_date:
        start_date_obj = portfolio_start_date
    if end_date_obj < portfolio_start_date:
        end_date_obj = portfolio_start_date
    
    # Validate date range (after clamping)
    if end_date_obj < start_date_obj:
        logger.warning(f"Invalid date range: end_date={end_date_obj} < start_date={start_date_obj}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"end_date ({end_date_obj}) must be greater than or equal to start_date ({start_date_obj})",
        )
    
    
    try:
        # Get portfolio performance either from cache (if available) or via on-demand calculation
        if cache and cache_end_date is not None:
            history_points = get_cached_portfolio_performance(
                cache,
                cache_end_date,
                start_date_obj,
                end_date_obj,
            )
        else:
            # On-demand calculation using historical portfolio and price service
            history_points = get_portfolio_performance(
                historical_portfolio,
                price_service,
                start_date_obj,
                end_date_obj,
            )
        
        # Apply granularity filter
        filtered_points = apply_granularity_filter(
            history_points,
            start_date_obj,
            end_date_obj,
            granularity,
        )
        
        logger.info(
            f"Portfolio performance response sent to user: {username}, "
            f"granularity={granularity}, history_points_count={len(filtered_points)}, "
            f"start_date={start_date_obj}, end_date={end_date_obj}"
        )
        
        return PortfolioPerformanceResponse(history_points=filtered_points)
    except ValueError as e:
        # Handle invalid date range, cache-related errors, or invalid granularity
        logger.warning(f"Error retrieving portfolio performance: {e}")
        error_str = str(e)
        
        # Use helper function to handle errors with guard clauses
        try:
            partial_response = _handle_performance_error(
                error_str,
                cache,
                cache_end_date,
                historical_portfolio,
                price_service,
                start_date_obj,
                end_date_obj,
                granularity,
            )
            if partial_response is not None:
                return partial_response
        except HTTPException:
            # Re-raise HTTPExceptions from helper function
            raise
    except Exception as e:
        logger.error(f"Unexpected error retrieving portfolio performance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving portfolio performance",
        )


@router.get("/asset/metadata/all", response_model=AssetMetadataAllResponse)
def get_all_asset_metadata_endpoint(
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    asset_service: AssetService = Depends(get_asset_service),
) -> AssetMetadataAllResponse:
    """
    GET endpoint to retrieve metadata for all tickers in the portfolio.

    Requires JWT authentication.

    Args:
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        asset_service: Asset service instance (injected via dependency)

    Returns:
        AssetMetadataAllResponse containing dictionary mapping ticker to metadata

    Raises:
        HTTPException: 500 if asset service is not available
    """
    logger.info(
        f"All asset metadata request received from user: {username}"
    )

    try:
        # Get metadata for all tickers from service layer
        metadata = get_all_asset_metadata(
            composite_portfolio,
            asset_service,
        )

        logger.info(
            f"All asset metadata response sent to user: {username}, "
            f"tickers_count={len(metadata)}, "
            f"metadata_available_count={len([m for m in metadata.values() if m is not None])}"
        )

        return AssetMetadataAllResponse(metadata=metadata)
    except Exception as e:
        logger.error(f"Unexpected error retrieving all asset metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving all asset metadata",
        )


@router.get("/asset/metadata/{ticker}", response_model=AssetMetadataResponse)
def get_asset_metadata_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    asset_service: AssetService = Depends(get_asset_service),
) -> AssetMetadataResponse:
    """
    GET endpoint to retrieve metadata for a specific asset ticker.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        asset_service: Asset service instance (injected via dependency)

    Returns:
        AssetMetadataResponse containing ticker and metadata dictionary

    Raises:
        HTTPException: 404 if ticker is not found in portfolio
        HTTPException: 500 if asset service is not available
    """
    logger.info(
        f"Asset metadata request received from user: {username}, ticker={ticker}"
    )

    try:
        # Get metadata from service layer
        metadata = get_asset_metadata(
            composite_portfolio,
            ticker,
            asset_service,
        )

        logger.info(
            f"Asset metadata response sent to user: {username}, ticker={ticker}, "
            f"metadata_available={metadata is not None}"
        )

        return AssetMetadataResponse(ticker=ticker, metadata=metadata)
    except ValueError as e:
        # Handle ticker not found
        logger.warning(f"Error retrieving metadata for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving metadata for ticker {ticker}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error while retrieving metadata for ticker {ticker}",
        )


@router.get("/asset/brokers/{ticker}", response_model=AssetBrokersResponse)
def get_asset_brokers_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
) -> AssetBrokersResponse:
    """
    GET endpoint to retrieve list of broker names that have positions for a specific asset ticker.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)

    Returns:
        AssetBrokersResponse containing ticker and list of broker names

    Raises:
        HTTPException: 404 if ticker is not found in portfolio
        HTTPException: 500 if portfolio data is not available
    """
    logger.info(
        f"Asset brokers request received from user: {username}, ticker={ticker}"
    )

    try:
        # Get brokers from service layer
        brokers = get_asset_brokers(
            composite_portfolio,
            ticker,
        )

        logger.info(
            f"Asset brokers response sent to user: {username}, ticker={ticker}, "
            f"brokers_count={len(brokers)}"
        )

        return AssetBrokersResponse(ticker=ticker, brokers=brokers)
    except ValueError as e:
        # Handle ticker not found
        logger.warning(f"Error retrieving brokers for ticker {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving brokers for ticker {ticker}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error while retrieving brokers for ticker {ticker}",
        )


@router.get("/asset/prices/{ticker}", response_model=AssetPriceHistoryResponse)
def get_asset_price_history_endpoint(
    ticker: str,
    username: str = Depends(get_current_user),
    composite_portfolio: CompositePortfolio = Depends(get_composite_portfolio),
    price_service: PriceService = Depends(get_price_service),
    start_date: Optional[str] = Query(None, description="Start date for price history (ISO format YYYY-MM-DD, defaults to max of 2 years ago or portfolio start)"),
    end_date: Optional[str] = Query(None, description="End date for price history (ISO format YYYY-MM-DD, defaults to today)"),
) -> AssetPriceHistoryResponse:
    """
    GET endpoint to retrieve historical price data for a specific asset ticker.

    Requires JWT authentication.

    Args:
        ticker: Asset ticker symbol
        username: Authenticated username (from token)
        composite_portfolio: Composite portfolio instance (injected via dependency)
        price_service: PriceService instance (injected via dependency)
        start_date: Optional start date for price history (ISO format YYYY-MM-DD, defaults to max of 2 years ago or portfolio start)
        end_date: Optional end date for price history (ISO format YYYY-MM-DD, defaults to today)

    Returns:
        AssetPriceHistoryResponse containing historical price points and current price

    Raises:
        HTTPException: 400 if date format is invalid or date range is invalid
        HTTPException: 404 if ticker is not found in portfolio
        HTTPException: 500 if price service is unavailable or internal error occurs
    """
    logger.info(
        f"Asset price history request received from user: {username}, ticker={ticker}, "
        f"start_date={start_date}, end_date={end_date}"
    )

    # Parse date parameters if provided
    start_date_obj = None
    end_date_obj = None

    if start_date is not None:
        start_date_obj = _parse_date_string(start_date, "start_date")

    if end_date is not None:
        end_date_obj = _parse_date_string(end_date, "end_date")

    try:
        # Get price history from service
        price_history = get_asset_price_history(
            composite_portfolio,
            ticker,
            price_service,
            start_date=start_date_obj,
            end_date=end_date_obj,
        )

        logger.info(
            f"Asset price history response sent to user: {username}, ticker={ticker}, "
            f"price_points_count={len(price_history.prices)}, current_price={price_history.current_price}"
        )

        return price_history
    except ValueError as e:
        # Handle ticker not found or invalid date range
        error_message = str(e)
        if "not found" in error_message.lower():
            logger.warning(f"Ticker {ticker} not found: {e}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            )
        else:
            # Invalid date range or other validation errors
            logger.warning(f"Invalid request for ticker {ticker}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )
    except Exception as e:
        logger.error(f"Unexpected error retrieving price history for ticker {ticker}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error while retrieving price history for ticker {ticker}",
        )

