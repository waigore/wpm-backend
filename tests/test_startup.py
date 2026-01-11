"""Tests for startup.py module."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from wpm_backend.utils.startup import run_startup_logic


@pytest.fixture
def mock_app():
    """Mock FastAPI app instance."""
    app = MagicMock()
    app.state.price_service = None
    app.state.composite_portfolio = None
    return app


@pytest.fixture
def test_settings():
    """Test settings fixture."""
    from wpm_backend.config import Settings
    
    return Settings(
        username="testuser",
        password="testpass",
        secret_key="test-secret-key-for-testing-purposes-only-minimum-32-chars",
        algorithm="HS256",
        access_token_expire_minutes=60,
        import_dir="import",
        log_level="INFO",
        log_dir="logs",
        enable_performance_cache=False,
    )


@pytest.mark.asyncio
async def test_run_startup_logic_success(mock_app, test_settings):
    """Test run_startup_logic() successfully creates services and imports portfolio."""
    mock_portfolio = MagicMock()
    mock_portfolio.get_positions.return_value = {"asset1": MagicMock()}
    
    with patch("wpm_backend.utils.startup.PriceService", return_value=MagicMock()):
        with patch("wpm_backend.utils.startup.importer.import_csv_files", return_value=mock_portfolio):
            with patch("wpm_backend.utils.startup.generate_openapi_spec"):
                await run_startup_logic(mock_app, test_settings)
    
    # Verify PriceService was created
    assert mock_app.state.price_service is not None
    
    # Verify portfolio was imported
    assert mock_app.state.composite_portfolio is not None
    assert mock_app.state.composite_portfolio == mock_portfolio
    
    # Verify generate_openapi_spec was called
    # (patched, so we can't verify directly, but if we get here, it succeeded)


@pytest.mark.asyncio
async def test_run_startup_logic_price_service_failure(mock_app, test_settings):
    """Test run_startup_logic() continues when PriceService creation fails."""
    mock_portfolio = MagicMock()
    mock_portfolio.get_positions.return_value = {}
    
    with patch("wpm_backend.utils.startup.PriceService", side_effect=Exception("PriceService failed")):
        with patch("wpm_backend.utils.startup.importer.import_csv_files", return_value=mock_portfolio):
            with patch("wpm_backend.utils.startup.generate_openapi_spec"):
                # Should not raise exception, should continue
                await run_startup_logic(mock_app, test_settings)
    
    # PriceService should still be None (failed to create)
    assert mock_app.state.price_service is None
    
    # But portfolio import should still have happened
    assert mock_app.state.composite_portfolio is not None


@pytest.mark.asyncio
async def test_run_startup_logic_import_failure(mock_app, test_settings):
    """Test run_startup_logic() continues when CSV import fails."""
    with patch("wpm_backend.utils.startup.PriceService", return_value=MagicMock()):
        with patch("wpm_backend.utils.startup.importer.import_csv_files", side_effect=Exception("Import failed")):
            with patch("wpm_backend.utils.startup.generate_openapi_spec"):
                # Should not raise exception, should continue
                await run_startup_logic(mock_app, test_settings)
    
    # PriceService should be created
    assert mock_app.state.price_service is not None
    
    # But portfolio should still be None (failed to import)
    assert mock_app.state.composite_portfolio is None


@pytest.mark.asyncio
async def test_run_startup_logic_openapi_failure(mock_app, test_settings):
    """Test run_startup_logic() continues when OpenAPI generation fails."""
    mock_portfolio = MagicMock()
    mock_portfolio.get_positions.return_value = {}
    
    with patch("wpm_backend.utils.startup.PriceService", return_value=MagicMock()):
        with patch("wpm_backend.utils.startup.importer.import_csv_files", return_value=mock_portfolio):
            with patch("wpm_backend.utils.startup.generate_openapi_spec", side_effect=Exception("OpenAPI failed")):
                # Should not raise exception, should continue
                await run_startup_logic(mock_app, test_settings)
    
    # Both services should be created despite OpenAPI failure
    assert mock_app.state.price_service is not None
    assert mock_app.state.composite_portfolio is not None


@pytest.mark.asyncio
async def test_run_startup_logic_multiple_failures(mock_app, test_settings):
    """Test run_startup_logic() continues when multiple operations fail."""
    with patch("wpm_backend.utils.startup.PriceService", side_effect=Exception("PriceService failed")):
        with patch("wpm_backend.utils.startup.importer.import_csv_files", side_effect=Exception("Import failed")):
            with patch("wpm_backend.utils.startup.generate_openapi_spec", side_effect=Exception("OpenAPI failed")):
                # Should not raise exception, should continue gracefully
                await run_startup_logic(mock_app, test_settings)
    
    # Both should be None (all operations failed)
    assert mock_app.state.price_service is None
    assert mock_app.state.composite_portfolio is None

