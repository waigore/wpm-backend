"""Application startup logic utilities."""

import logging
from pathlib import Path

from fastapi import FastAPI

from wpm import importer
from wpm.pricing import PriceService

from wpm_backend.config import Settings
from wpm_backend.utils.openapi_generator import generate_openapi_spec

logger = logging.getLogger(__name__)


async def run_startup_logic(app: FastAPI, settings: Settings) -> None:
    """
    Execute application startup logic.

    This function performs all startup tasks:
    - Creates and stores PriceService instance
    - Imports CSV files and creates composite portfolio
    - Generates OpenAPI specification

    Args:
        app: FastAPI application instance
        settings: Application settings
    """
    logger.info("Application startup initiated")

    # Create shared PriceService instance
    try:
        app.state.price_service = PriceService()
        logger.info("PriceService instance created and stored in app state")
    except Exception as e:
        logger.error(f"Failed to create PriceService: {e}", exc_info=True)
        # Continue startup even if PriceService creation fails - may still work for some operations

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
        except Exception as e:
            logger.error(f"Failed to create cloned historical portfolio: {e}", exc_info=True)
            # Continue startup even if clone fails - performance endpoint won't work
    except Exception as e:
        logger.error(f"Failed to import CSV files: {e}", exc_info=True)
        # Continue startup even if import fails - app can still run

    # Generate OpenAPI specification
    try:
        generate_openapi_spec(app)
    except Exception as e:
        logger.error(f"Failed to generate OpenAPI specification: {e}", exc_info=True)

    logger.info("Application startup completed")

