"""Unit and integration tests for reference portfolio performance endpoints."""

import cachetools
from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint
from wpm_backend.services.portfolio_service import get_reference_portfolio_performance


def test_get_reference_portfolio_performance_service(mock_composite_portfolio, mock_price_service):
    """Test get_reference_portfolio_performance() service function."""
    from wpm.models import Asset, PortfolioHistoryPoint as WPMPortfolioHistoryPoint
    from wpm.reference.portfolio import create_reference_portfolio
    from wpm.reference.strategy import BuyAndHoldStrategy
    
    # Mock reference portfolio
    mock_reference_portfolio = MagicMock()
    
    # Mock get_historical_performance to return history points
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 16),
            total_market_value=25500.0,
            asset_positions={"SPY": 25500.0},
            prices={"SPY": 510.00},
            quantities={"SPY": 50.0},
            percentage_return=12.0,
        ),
    ]
    
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            history_points = get_reference_portfolio_performance(
                mock_composite_portfolio,
                "SPY",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 16),
            )
    
    assert len(history_points) == 2
    
    # Check first history point
    hp1 = history_points[0]
    assert hp1.date == "2024-01-15"
    assert hp1.total_market_value == 25000.0
    assert hp1.asset_positions == {"SPY": 25000.0}
    assert hp1.prices == {"SPY": 500.00}
    assert hp1.percentage_return == 10.5
    
    # Check second history point
    hp2 = history_points[1]
    assert hp2.date == "2024-01-16"
    assert hp2.total_market_value == 25500.0
    assert hp2.asset_positions == {"SPY": 25500.0}
    assert hp2.prices == {"SPY": 510.00}
    assert hp2.percentage_return == 12.0


def test_get_reference_portfolio_performance_cache_none(mock_composite_portfolio, mock_price_service):
    """Test get_reference_portfolio_performance() with no cache: create_reference_portfolio called every time."""
    from wpm.models import PortfolioHistoryPoint as WPMPortfolioHistoryPoint

    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
    ]
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio) as mock_create:
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            get_reference_portfolio_performance(
                mock_composite_portfolio,
                "SPY",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 15),
                reference_portfolio_cache=None,
            )
    assert mock_create.call_count == 1


def test_get_reference_portfolio_performance_cache_miss(mock_composite_portfolio, mock_price_service):
    """Test get_reference_portfolio_performance() cache miss: creates reference portfolio and stores in cache."""
    from wpm.models import PortfolioHistoryPoint as WPMPortfolioHistoryPoint

    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
    ]
    cache = cachetools.FIFOCache(maxsize=5)
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            result = get_reference_portfolio_performance(
                mock_composite_portfolio,
                "SPY",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 15),
                reference_portfolio_cache=cache,
            )
    assert len(result) == 1
    assert result[0].date == "2024-01-15"
    key = ("SPY", "Stock")
    assert key in cache
    assert cache[key] is mock_reference_portfolio


def test_get_reference_portfolio_performance_cache_hit(mock_composite_portfolio, mock_price_service):
    """Test get_reference_portfolio_performance() cache hit: create_reference_portfolio not called."""
    from wpm.models import PortfolioHistoryPoint as WPMPortfolioHistoryPoint

    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
    ]
    cache = cachetools.FIFOCache(maxsize=5)
    key = ("SPY", "Stock")
    cache[key] = mock_reference_portfolio
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio") as mock_create:
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            result = get_reference_portfolio_performance(
                mock_composite_portfolio,
                "SPY",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 15),
                reference_portfolio_cache=cache,
            )
    mock_create.assert_not_called()
    assert len(result) == 1
    assert result[0].date == "2024-01-15"


def test_get_reference_portfolio_performance_fifo_eviction(mock_composite_portfolio, mock_price_service):
    """Test FIFO eviction: 6th key evicts first; evicted key is miss on next request."""
    from wpm.models import PortfolioHistoryPoint as WPMPortfolioHistoryPoint

    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"X": 25000.0},
            prices={"X": 100.0},
            quantities={"X": 250.0},
            percentage_return=0.0,
        ),
    ]
    cache = cachetools.FIFOCache(maxsize=5)
    # Fill with 5 distinct (ticker, asset_type) keys
    for i in range(5):
        mock_ref = MagicMock()
        cache[(f"T{i}", "Stock")] = mock_ref
    assert len(cache) == 5
    first_key = ("T0", "Stock")
    assert first_key in cache
    # Add 6th key; FIFO evicts T0
    mock_ref_5 = MagicMock()
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_ref_5):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            get_reference_portfolio_performance(
                mock_composite_portfolio,
                "T5",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 15),
                reference_portfolio_cache=cache,
            )
    assert len(cache) == 5
    assert first_key not in cache
    assert ("T5", "Stock") in cache
    # Request for evicted key T0 is cache miss and repopulates
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=MagicMock()) as mock_create:
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            get_reference_portfolio_performance(
                mock_composite_portfolio,
                "T0",
                "Stock",
                mock_price_service,
                date(2024, 1, 15),
                date(2024, 1, 15),
                reference_portfolio_cache=cache,
            )
    assert mock_create.call_count == 1
    assert first_key in cache


def test_get_reference_portfolio_performance_missing_percentage_return(mock_composite_portfolio, mock_price_service):
    """Test get_reference_portfolio_performance() when percentage_return is None."""
    from wpm.models import Asset
    from wpm.reference.portfolio import create_reference_portfolio
    
    # Mock reference portfolio
    mock_reference_portfolio = MagicMock()
    
    # Create a mock history point with percentage_return=None
    # We can't use WPMPortfolioHistoryPoint because it validates percentage_return
    mock_history_point = MagicMock()
    mock_history_point.date = date(2024, 1, 15)
    mock_history_point.total_market_value = 25000.0
    mock_history_point.asset_positions = {"SPY": 25000.0}
    mock_history_point.prices = {"SPY": 500.00}
    mock_history_point.percentage_return = None  # This should cause an error
    
    mock_history_points = [mock_history_point]
    
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            with pytest.raises(ValueError, match="percentage_return is unavailable"):
                get_reference_portfolio_performance(
                    mock_composite_portfolio,
                    "SPY",
                    "Stock",
                    mock_price_service,
                    date(2024, 1, 15),
                    date(2024, 1, 15),
                )


def test_reference_performance_endpoint(client_with_portfolio, test_settings):
    """Test /reference/{ticker}/performance endpoint."""
    from wpm.models import Asset, PortfolioHistoryPoint as WPMPortfolioHistoryPoint
    from wpm.reference.portfolio import create_reference_portfolio
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)
    
    # Mock reference portfolio and history points
    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 16),
            total_market_value=25500.0,
            asset_positions={"SPY": 25500.0},
            prices={"SPY": 510.00},
            quantities={"SPY": 50.0},
            percentage_return=12.0,
        ),
    ]
    
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            # Call endpoint
            response = client_with_portfolio.get(
                "/reference/SPY/performance?asset_type=ETF&start_date=2024-01-15&end_date=2024-01-16",
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
    assert hp1["asset_positions"] == {"SPY": 25000.0}
    assert hp1["prices"] == {"SPY": 500.00}
    assert hp1["percentage_return"] == 10.5


def test_reference_performance_endpoint_cache_hit(client_with_portfolio, test_settings):
    """Test two consecutive GETs for same ticker/asset_type: second request uses cache (create_reference_portfolio called once)."""
    from wpm.models import PortfolioHistoryPoint as WPMPortfolioHistoryPoint

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)

    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
    ]
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio) as mock_create:
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            response1 = client_with_portfolio.get(
                "/reference/SPY/performance?asset_type=ETF&start_date=2024-01-15&end_date=2024-01-15",
                headers={"Authorization": f"Bearer {token}"},
            )
            response2 = client_with_portfolio.get(
                "/reference/SPY/performance?asset_type=ETF&start_date=2024-01-15&end_date=2024-01-15",
                headers={"Authorization": f"Bearer {token}"},
            )
    assert response1.status_code == 200
    assert response2.status_code == 200
    assert mock_create.call_count == 1
    assert response1.json() == response2.json()


def test_reference_performance_endpoint_default_parameters(client_with_portfolio, test_settings):
    """Test /reference/{ticker}/performance endpoint with default parameters."""
    from wpm.models import Asset, PortfolioHistoryPoint as WPMPortfolioHistoryPoint
    from datetime import date, timedelta
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)
    
    # Mock reference portfolio and history points
    mock_reference_portfolio = MagicMock()
    today = date.today()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=today - timedelta(days=1),
            total_market_value=25000.0,
            asset_positions={"SPY": 25000.0},
            prices={"SPY": 500.00},
            quantities={"SPY": 50.0},
            percentage_return=10.5,
        ),
        WPMPortfolioHistoryPoint(
            date=today,
            total_market_value=25500.0,
            asset_positions={"SPY": 25500.0},
            prices={"SPY": 510.00},
            quantities={"SPY": 50.0},
            percentage_return=12.0,
        ),
    ]
    
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            # Call endpoint without date parameters
            response = client_with_portfolio.get(
                "/reference/SPY/performance?asset_type=ETF",
                headers={"Authorization": f"Bearer {token}"},
            )
    
    assert response.status_code == 200
    data = response.json()
    assert "history_points" in data


def test_reference_performance_endpoint_granularity(client_with_portfolio, test_settings):
    """Test /reference/{ticker}/performance endpoint with different granularity options."""
    from wpm.models import Asset, PortfolioHistoryPoint as WPMPortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)
    
    # Mock reference portfolio and history points (7 days for weekly test)
    mock_reference_portfolio = MagicMock()
    mock_history_points = [
        WPMPortfolioHistoryPoint(
            date=date(2024, 1, 15 + i),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"SPY": 25000.0 + (i * 100)},
            prices={"SPY": 500.00 + (i * 2)},
            quantities={"SPY": 50.0},
            percentage_return=10.0 + (i * 0.5),
        )
        for i in range(7)
    ]
    
    with patch("wpm_backend.services.portfolio_service.create_reference_portfolio", return_value=mock_reference_portfolio):
        with patch("wpm_backend.services.portfolio_service.get_historical_performance", return_value=mock_history_points):
            # Test weekly granularity
            response = client_with_portfolio.get(
                "/reference/SPY/performance?asset_type=ETF&start_date=2024-01-15&end_date=2024-01-21&granularity=weekly",
                headers={"Authorization": f"Bearer {token}"},
            )
    
    assert response.status_code == 200
    data = response.json()
    assert "history_points" in data
    # Weekly should return fewer points than daily
    assert len(data["history_points"]) <= 7


def test_reference_performance_endpoint_invalid_date_format(client_with_portfolio, test_settings):
    """Test /reference/{ticker}/performance endpoint with invalid date format."""
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Mock portfolio
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)
    
    # Call endpoint with invalid date format
    response = client_with_portfolio.get(
        "/reference/SPY/performance?asset_type=ETF&start_date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 400
    assert "Invalid start_date format" in response.json()["detail"]


def test_reference_performance_endpoint_invalid_date_range(client_with_portfolio, test_settings):
    """Test /reference/{ticker}/performance endpoint with invalid date range."""
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Mock portfolio
    mock_composite_portfolio = client_with_portfolio.app.state.composite_portfolio
    mock_composite_portfolio.start_date = date(2024, 1, 1)
    
    # Call endpoint with invalid date range (end_date < start_date)
    response = client_with_portfolio.get(
        "/reference/SPY/performance?asset_type=ETF&start_date=2024-01-16&end_date=2024-01-15",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 400
    assert "end_date" in response.json()["detail"].lower()
    assert "start_date" in response.json()["detail"].lower()


def test_reference_performance_endpoint_authentication_required(client_with_portfolio):
    """Test /reference/{ticker}/performance endpoint requires authentication."""
    # Call endpoint without token
    response = client_with_portfolio.get("/reference/SPY/performance")
    
    assert response.status_code == 401
