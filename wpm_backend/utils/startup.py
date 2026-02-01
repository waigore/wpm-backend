"""Application startup logic utilities."""

import logging
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import FastAPI

from wpm import importer
from wpm.asset import AssetService
from wpm.pricing import PriceService
from wpm.portfolio import CompositePortfolio, get_historical_performance

from wpm_backend.config import Settings
from wpm_backend.models.portfolio import PortfolioHistoryPoint
from wpm_backend.services.portfolio_utils import parse_date_to_iso_string
from wpm_backend.utils.openapi_generator import generate_openapi_spec

logger = logging.getLogger(__name__)


def _transform_history_points_to_cache(
    wpm_history_points: list,
) -> Dict[str, PortfolioHistoryPoint]:
    """
    Transform wpm PortfolioHistoryPoint objects to API models and create cache dictionary.
    
    Args:
        wpm_history_points: List of wpm PortfolioHistoryPoint objects
        
    Returns:
        Dictionary keyed by ISO date string, mapping to PortfolioHistoryPoint API models
    """
    performance_cache = {}
    for wpm_history_point in wpm_history_points:
        try:
            # Extract date and convert to ISO format string
            history_date_str = parse_date_to_iso_string(wpm_history_point.date)
            
            # Extract total_market_value
            total_market_value = float(wpm_history_point.total_market_value)
            
            # Extract asset_positions (already Dict[str, float])
            asset_positions = wpm_history_point.asset_positions
            
            # Extract prices (already Dict[str, float])
            prices = wpm_history_point.prices
            
            # Extract percentage_return and validate it's not None
            if wpm_history_point.percentage_return is None:
                logger.error(f"percentage_return is unavailable for history point at date {history_date_str}")
                raise ValueError(f"percentage_return is unavailable for history point at date {history_date_str}")
            percentage_return = float(wpm_history_point.percentage_return)
            
            # Create API PortfolioHistoryPoint model
            api_history_point = PortfolioHistoryPoint(
                date=history_date_str,
                total_market_value=total_market_value,
                asset_positions=asset_positions,
                prices=prices,
                percentage_return=percentage_return,
            )
            
            # Store in cache dictionary keyed by date string
            performance_cache[history_date_str] = api_history_point
        except ValueError as e:
            # Re-raise ValueError for percentage_return issues (data integrity)
            error_str = str(e)
            if "percentage_return is unavailable" in error_str:
                logger.error(f"Error transforming history point: {e}", exc_info=True)
                raise
            # For other ValueErrors, log and continue
            logger.error(f"Error transforming history point: {e}", exc_info=True)
            continue
        except Exception as e:
            logger.error(f"Error transforming history point: {e}", exc_info=True)
            continue
    
    return performance_cache


def _calculate_performance_cache(
    historical_portfolio: CompositePortfolio,
    price_service: PriceService,
    start_date: date,
    end_date: date,
) -> Tuple[Dict[str, PortfolioHistoryPoint], date]:
    """
    Calculate performance cache from historical portfolio.
    
    Args:
        historical_portfolio: Cloned historical portfolio
        price_service: PriceService instance for fetching prices
        start_date: Start date for performance calculation
        end_date: End date for performance calculation
        
    Returns:
        Tuple of (cache dictionary, end_date)
        
    Raises:
        Exception: If cache calculation fails
    """
    logger.info(f"Calculating performance cache from {start_date} to {end_date}")
    
    # Get history points from wpm library
    wpm_history_points = get_historical_performance(
        historical_portfolio, price_service, start_date, end_date
    )
    logger.info(f"Retrieved {len(wpm_history_points)} history points from wpm library")
    
    # Transform wpm PortfolioHistoryPoint objects to API models and store in cache
    performance_cache = _transform_history_points_to_cache(wpm_history_points)
    
    logger.info(
        f"Performance cache created with {len(performance_cache)} history points "
        f"(from {start_date} to {end_date})"
    )
    
    return performance_cache, end_date


def _initialize_performance_cache(
    historical_portfolio: CompositePortfolio,
    price_service: Optional[PriceService],
    settings: Settings,
) -> Tuple[Dict[str, PortfolioHistoryPoint], Optional[date]]:
    """
    Initialize performance cache based on settings and portfolio state.
    
    Args:
        historical_portfolio: Cloned historical portfolio
        price_service: PriceService instance (may be None if creation failed)
        settings: Application settings
        
    Returns:
        Tuple of (cache dictionary, end_date or None)
    """
    if not settings.enable_performance_cache:
        logger.info("Performance cache calculation is disabled")
        return {}, None
    
    if price_service is None:
        logger.warning(
            "PriceService is not available. Performance cache will not be created."
        )
        return {}, None
    
    try:
        start_date = historical_portfolio.start_date
        if start_date is None:
            # Treat as sanity error - start_date should always exist for historical portfolios
            logger.error(
                "Historical portfolio has no start_date (unexpected state). "
                "Performance cache will not be created."
            )
            return {}, None
        
        # Calculate history points from start_date to today
        end_date = date.today()
        performance_cache, cache_end_date = _calculate_performance_cache(
            historical_portfolio, price_service, start_date, end_date
        )
        return performance_cache, cache_end_date
        
    except Exception as e:
        logger.error(f"Failed to create performance cache: {e}", exc_info=True)
        # Continue startup even if cache creation fails - performance endpoint will fail with appropriate error
        return {}, None


async def run_startup_logic(app: FastAPI, settings: Settings) -> None:
    """
    Execute application startup logic.

    This function performs all startup tasks:
    - Creates and stores PriceService instance
    - Imports CSV files and creates composite portfolio
    - Creates and stores cloned historical portfolio for performance endpoint
    - Pre-calculates and caches portfolio performance history points
    - Generates OpenAPI specification

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    logger.info("Application startup initiated")

    # Create shared PriceService instance
    price_service = None
    try:
        price_service = PriceService()
        app.state.price_service = price_service
        logger.info("PriceService instance created and stored in app state")
    except Exception as e:
        logger.error(f"Failed to create PriceService: {e}", exc_info=True)
        # Continue startup even if PriceService creation fails - may still work for some operations

    # Create shared AssetService instance (requires PriceService for metadata retrieval)
    try:
        app.state.asset_service = AssetService(price_service=price_service)
        logger.info("AssetService instance created and stored in app state")
    except Exception as e:
        logger.error(f"Failed to create AssetService: {e}", exc_info=True)
        # Continue startup even if AssetService creation fails - metadata endpoints won't work

    # Import CSV files using wpm library
    import_dir = Path(settings.import_dir)
    logger.info(f"Importing CSV files from directory: {import_dir}")

    try:
        composite_portfolio = importer.import_csv_files(import_dir)
        app.state.composite_portfolio = composite_portfolio
        logger.info(
            f"Successfully imported CSV files. Composite portfolio created with "
            f"{len(composite_portfolio.get_positions())} positions"
        )
        
        # Create cloned historical portfolio for performance endpoint
        try:
            historical_portfolio = composite_portfolio.clone()
            app.state.historical_portfolio = historical_portfolio
            logger.info("Cloned historical portfolio created and stored in app state")
            
            # Pre-calculate and cache portfolio performance history points
            performance_cache, cache_end_date = _initialize_performance_cache(
                historical_portfolio, app.state.price_service, settings
            )
            app.state.performance_cache = performance_cache
            app.state.performance_cache_end_date = cache_end_date
        except Exception as e:
            logger.error(f"Failed to create cloned historical portfolio: {e}", exc_info=True)
            # Continue startup even if clone fails - performance endpoint won't work
            app.state.performance_cache = {}
            app.state.performance_cache_end_date = None
    except Exception as e:
        logger.error(f"Failed to import CSV files: {e}", exc_info=True)
        # Continue startup even if import fails - app can still run

    # Generate OpenAPI specification
    try:
        generate_openapi_spec(app)
    except Exception as e:
        logger.error(f"Failed to generate OpenAPI specification: {e}", exc_info=True)

    logger.info("Application startup completed")

