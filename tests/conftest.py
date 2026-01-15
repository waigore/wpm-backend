"""Pytest configuration and shared fixtures."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from wpm_backend.config import Settings, get_settings
from wpm_backend.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Settings fixture with test credentials."""
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


@pytest.fixture
def mock_composite_portfolio():
    """Mock CompositePortfolio fixture."""
    from wpm.models import Asset, Position as WPMPosition

    # Create mock assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    # Create mock positions
    position1 = Mock(spec=WPMPosition)
    position1.asset = asset1
    position1.quantity = Decimal("100.0")
    position1.cost_basis = 15000.0
    position1.cost_basis_method = "fifo"

    position2 = Mock(spec=WPMPosition)
    position2.asset = asset2
    position2.quantity = Decimal("50.0")
    position2.cost_basis = 5000.0
    position2.cost_basis_method = "average"

    # Create mock composite portfolio
    composite = MagicMock()
    composite.get_positions.return_value = {
        asset1: position1,
        asset2: position2,
    }

    return composite


@pytest.fixture
def mock_price_service():
    """Mock PriceService fixture."""
    return MagicMock()


@pytest.fixture
def mock_asset_service():
    """Mock AssetService fixture."""
    return MagicMock()


@pytest.fixture
def mock_price_map(mock_composite_portfolio):
    """Mock price map fixture."""
    from wpm.models import Asset

    assets = list(mock_composite_portfolio.get_positions().keys())
    return {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }


@pytest.fixture(autouse=True)
def reset_settings():
    """Auto-use fixture to reset global settings before each test."""
    import wpm_backend.config
    wpm_backend.config._settings = None
    yield
    wpm_backend.config._settings = None


@pytest.fixture
def app(test_settings):
    """FastAPI app fixture with test settings."""
    # Reset global settings
    import wpm_backend.config
    wpm_backend.config._settings = None
    
    # Patch get_settings in all modules that import it
    with patch("wpm_backend.config.get_settings", return_value=test_settings):
        with patch("wpm_backend.main.get_settings", return_value=test_settings):
            with patch("wpm_backend.api.routes.get_settings", return_value=test_settings):
                # Also override the dependency in FastAPI
                app = create_app()
                # Override the dependency
                app.dependency_overrides[get_settings] = lambda: test_settings
                yield app
                app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def client_with_portfolio(app, mock_composite_portfolio, mock_price_service):
    """TestClient with mock portfolio and price service in app state."""
    app.state.composite_portfolio = mock_composite_portfolio
    app.state.historical_portfolio = mock_composite_portfolio  # Use same mock for historical portfolio in tests
    app.state.price_service = mock_price_service
    return TestClient(app)

