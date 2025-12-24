"""FastAPI application entry point, initializes app and includes routers."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from wpm import importer
from wpm.pricing import PriceService

from wpm_backend.api.routes import router
from wpm_backend.config import get_settings
from wpm_backend.utils.logging_config import setup_logging
from wpm_backend.utils.openapi_generator import generate_openapi_spec

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Factory function that creates and configures the FastAPI application instance.

    Returns:
        Configured FastAPI application instance
    """
    try:
        settings = get_settings()
    except Exception:
        # If settings can't be loaded (e.g., missing .env), use defaults
        from wpm_backend.config import Settings
        settings = Settings(
            username="admin",
            password="password",
            secret_key="default-secret-key-for-development-only",
            import_dir="import",
            log_level="INFO",
            log_dir="logs",
        )

    # Initialize logging (defensive - don't fail if logging setup fails)
    try:
        setup_logging(log_dir=settings.log_dir, log_level=settings.log_level)
    except Exception as e:
        # Log to stderr if file logging fails
        import sys
        print(f"Warning: Failed to setup logging: {e}", file=sys.stderr)

    # Create FastAPI app
    app = FastAPI(
        title="WPM Backend API",
        description="Wealth Portfolio Manager Backend API",
        version="0.1.0",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify actual origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(router)

    # Initialize app state variables (will be populated in startup)
    app.state.composite_portfolio = None
    app.state.price_service = None

    @app.on_event("startup")
    async def startup_event() -> None:
        """Event handler invoked on application startup."""
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
        except Exception as e:
            logger.error(f"Failed to import CSV files: {e}", exc_info=True)
            # Continue startup even if import fails - app can still run

        # Generate OpenAPI specification
        try:
            generate_openapi_spec(app)
        except Exception as e:
            logger.error(f"Failed to generate OpenAPI specification: {e}", exc_info=True)

        logger.info("Application startup completed")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        """Event handler invoked on application shutdown."""
        logger.info("Application shutdown initiated")
        # Add any cleanup logic here if needed
        logger.info("Application shutdown completed")

    return app


# Create app instance
# Note: Startup events will only fire when the app is actually run by uvicorn
app = create_app()

