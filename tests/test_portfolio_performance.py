"""Unit and integration tests for portfolio performance endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import apply_granularity_filter, get_all_positions, get_cached_portfolio_performance, get_portfolio_performance


def test_get_portfolio_performance_service(mock_composite_portfolio, mock_price_service):
    """Test get_portfolio_performance() service function."""
    from datetime import date
    from wpm.models import PortfolioHistoryPoint
    
    # Mock get_historical_performance
    mock_history_points = [
        PortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0, "GOOGL": 7500.0},
            prices={"AAPL": 175.50, "GOOGL": 150.00},
            quantities={"AAPL": 100.0, "GOOGL": 50.0},
            percentage_return=10.5,
        ),
        PortfolioHistoryPoint(
            date=date(2024, 1, 16),
            total_market_value=25500.0,
            asset_positions={"AAPL": 18000.0, "GOOGL": 7500.0},
            prices={"AAPL": 180.00, "GOOGL": 150.00},
            quantities={"AAPL": 100.0, "GOOGL": 50.0},
            percentage_return=12.0,
        ),
    ]
    
    with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
        history_points = get_portfolio_performance(
            mock_composite_portfolio,
            mock_price_service,
            date(2024, 1, 15),
            date(2024, 1, 16),
        )
    
    assert len(history_points) == 2
    
    # Check first history point
    hp1 = history_points[0]
    assert hp1.date == "2024-01-15"
    assert hp1.total_market_value == 25000.0
    assert hp1.asset_positions == {"AAPL": 17550.0, "GOOGL": 7500.0}
    assert hp1.prices == {"AAPL": 175.50, "GOOGL": 150.00}
    assert hp1.percentage_return == 10.5
    
    # Check second history point
    hp2 = history_points[1]
    assert hp2.date == "2024-01-16"
    assert hp2.total_market_value == 25500.0
    assert hp2.asset_positions == {"AAPL": 18000.0, "GOOGL": 7500.0}
    assert hp2.prices == {"AAPL": 180.00, "GOOGL": 150.00}
    assert hp2.percentage_return == 12.0


def test_portfolio_performance_endpoint(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 1)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache manually (startup skips cache calculation during tests)
    cache_end_date = date(2024, 1, 16)
    performance_cache = {
        "2024-01-15": PortfolioHistoryPoint(
            date="2024-01-15",
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0, "GOOGL": 7500.0},
            prices={"AAPL": 175.50, "GOOGL": 150.00},
            percentage_return=10.5,
        ),
        "2024-01-16": PortfolioHistoryPoint(
            date="2024-01-16",
            total_market_value=25500.0,
            asset_positions={"AAPL": 18000.0, "GOOGL": 7500.0},
            prices={"AAPL": 180.00, "GOOGL": 150.00},
            percentage_return=12.0,
        ),
    }
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-16",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "history_points" in data
    assert len(data["history_points"]) == 2
    
    # Check first history point
    hp1 = data["history_points"][0]
    assert hp1["date"] == "2024-01-15"
    assert hp1["total_market_value"] == 25000.0
    assert hp1["asset_positions"] == {"AAPL": 17550.0, "GOOGL": 7500.0}
    assert hp1["prices"] == {"AAPL": 175.50, "GOOGL": 150.00}
    assert hp1["percentage_return"] == 10.5


def test_portfolio_performance_endpoint_no_historical_portfolio(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint when historical portfolio is not available."""
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Don't set historical_portfolio in app state
    client_with_portfolio.app.state.historical_portfolio = None
    
    # Access endpoint without historical portfolio
    response = client_with_portfolio.get(
        "/portfolio/all/performance",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 500
    assert "detail" in response.json()
    assert "Historical portfolio" in response.json()["detail"]


