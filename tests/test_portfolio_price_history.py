"""Unit and integration tests for portfolio price history endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import get_all_positions, get_asset_price_history, get_portfolio_performance


def test_get_asset_price_history_service_success(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function with successful price retrieval."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio to return asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}
    mock_composite_portfolio.start_date = date(2023, 1, 1)

    # Setup mock historical prices
    today = date.today()
    start_date = max(today - timedelta(days=730), mock_composite_portfolio.start_date)
    historical_prices = {
        "AAPL": {
            start_date: 150.0,
            start_date + timedelta(days=1): 151.0,
            start_date + timedelta(days=2): 152.0,
        }
    }
    mock_price_service.get_historical_prices.return_value = historical_prices
    mock_price_service.get_price.return_value = 175.50

    # Call service function
    result = get_asset_price_history(
        mock_composite_portfolio,
        "AAPL",
        mock_price_service,
        start_date=None,  # Use default
        end_date=None,  # Use default
    )

    # Verify result
    assert result.ticker == "AAPL"
    assert result.asset_type == "Stock"
    assert len(result.prices) == 3
    assert result.prices[0].date == start_date.isoformat()
    assert result.prices[0].price == 150.0
    assert result.prices[1].price == 151.0
    assert result.prices[2].price == 152.0
    assert result.current_price == 175.50

    # Verify service calls
    mock_composite_portfolio.get_assets.assert_called_once()
    mock_price_service.get_historical_prices.assert_called_once()
    mock_price_service.get_price.assert_called_once_with("AAPL", "Stock")


def test_get_asset_price_history_service_with_date_range(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function with explicit date range."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio to return asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup explicit date range
    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 5)

    # Setup mock historical prices
    historical_prices = {
        "AAPL": {
            start_date: 150.0,
            start_date + timedelta(days=1): 151.0,
            start_date + timedelta(days=2): 152.0,
        }
    }
    mock_price_service.get_historical_prices.return_value = historical_prices
    mock_price_service.get_price.return_value = 175.50

    # Call service function with explicit dates
    result = get_asset_price_history(
        mock_composite_portfolio,
        "AAPL",
        mock_price_service,
        start_date=start_date,
        end_date=end_date,
    )

    # Verify result
    assert result.ticker == "AAPL"
    assert len(result.prices) == 3
    mock_price_service.get_historical_prices.assert_called_once_with(
        ["AAPL"], "Stock", start_date, end_date
    )


def test_get_asset_price_history_service_default_start_date(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function default start_date calculation."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Test case 1: Portfolio start_date is more recent than 2 years ago
    portfolio_start = date.today() - timedelta(days=365)  # 1 year ago
    mock_composite_portfolio.start_date = portfolio_start

    historical_prices = {"AAPL": {portfolio_start: 150.0}}
    mock_price_service.get_historical_prices.return_value = historical_prices
    mock_price_service.get_price.return_value = 175.50

    result = get_asset_price_history(
        mock_composite_portfolio, "AAPL", mock_price_service, start_date=None, end_date=None
    )

    # Should use portfolio_start (more recent than 2 years ago)
    two_years_ago = date.today() - timedelta(days=730)
    expected_start = max(two_years_ago, portfolio_start)
    assert expected_start == portfolio_start
    mock_price_service.get_historical_prices.assert_called_once()
    call_args = mock_price_service.get_historical_prices.call_args
    assert call_args[0][2] == portfolio_start  # start_date should be portfolio_start

    # Test case 2: Portfolio start_date is older than 2 years ago
    portfolio_start_old = date.today() - timedelta(days=1000)  # ~2.7 years ago
    mock_composite_portfolio.start_date = portfolio_start_old

    historical_prices_old = {"AAPL": {two_years_ago: 150.0}}
    mock_price_service.get_historical_prices.return_value = historical_prices_old

    result2 = get_asset_price_history(
        mock_composite_portfolio, "AAPL", mock_price_service, start_date=None, end_date=None
    )

    # Should use 2 years ago (more recent than portfolio start)
    call_args2 = mock_price_service.get_historical_prices.call_args
    assert call_args2[0][2] == two_years_ago  # start_date should be 2 years ago


def test_get_asset_price_history_service_no_portfolio_start_date(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() when portfolio has no start_date."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio with no start_date
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}
    mock_composite_portfolio.start_date = None

    two_years_ago = date.today() - timedelta(days=730)
    historical_prices = {"AAPL": {two_years_ago: 150.0}}
    mock_price_service.get_historical_prices.return_value = historical_prices
    mock_price_service.get_price.return_value = 175.50

    result = get_asset_price_history(
        mock_composite_portfolio, "AAPL", mock_price_service, start_date=None, end_date=None
    )

    # Should use 2 years ago when portfolio start_date is None
    call_args = mock_price_service.get_historical_prices.call_args
    assert call_args[0][2] == two_years_ago


def test_get_asset_price_history_service_ticker_not_found(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function when ticker is not in portfolio."""
    from wpm_backend.services.portfolio_service import get_asset_price_history

    # Setup mock portfolio to return empty assets
    mock_composite_portfolio.get_assets.return_value = {}

    # Call service function and expect ValueError
    with pytest.raises(ValueError, match="Ticker INVALID not found in portfolio"):
        get_asset_price_history(mock_composite_portfolio, "INVALID", mock_price_service)

    # Verify price service was not called
    mock_price_service.get_historical_prices.assert_not_called()
    mock_price_service.get_price.assert_not_called()


def test_get_asset_price_history_service_invalid_date_range(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function with invalid date range."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Call with invalid date range (end_date < start_date)
    start_date = date(2024, 1, 5)
    end_date = date(2024, 1, 1)

    with pytest.raises(ValueError, match="end_date.*must be greater than or equal to start_date"):
        get_asset_price_history(
            mock_composite_portfolio,
            "AAPL",
            mock_price_service,
            start_date=start_date,
            end_date=end_date,
        )


def test_get_asset_price_history_service_price_retrieval_error(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() service function when price retrieval fails."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}
    # Set start_date to a proper date to avoid comparison issues
    mock_composite_portfolio.start_date = date(2023, 1, 1)

    # Setup mock to raise exception on historical prices
    mock_price_service.get_historical_prices.side_effect = Exception("Price service unavailable")

    with pytest.raises(ValueError, match="Failed to retrieve historical prices"):
        get_asset_price_history(mock_composite_portfolio, "AAPL", mock_price_service)


def test_get_asset_price_history_service_current_price_unavailable(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() when current price cannot be retrieved."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}
    mock_composite_portfolio.start_date = date(2023, 1, 1)

    # Setup historical prices (successful)
    today = date.today()
    start_date = max(today - timedelta(days=730), mock_composite_portfolio.start_date)
    historical_prices = {"AAPL": {start_date: 150.0}}
    mock_price_service.get_historical_prices.return_value = historical_prices

    # Setup current price to fail
    mock_price_service.get_price.side_effect = Exception("Current price unavailable")

    # Call service function
    result = get_asset_price_history(
        mock_composite_portfolio, "AAPL", mock_price_service, start_date=None, end_date=None
    )

    # Should still return result with current_price as None
    assert result.ticker == "AAPL"
    assert len(result.prices) == 1
    assert result.current_price is None


def test_get_asset_price_history_service_no_price_data(mock_composite_portfolio, mock_price_service):
    """Test get_asset_price_history() when no historical price data is available."""
    from datetime import date, timedelta
    from wpm_backend.services.portfolio_service import get_asset_price_history
    from wpm.models import Asset

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}
    mock_composite_portfolio.start_date = date(2023, 1, 1)

    # Setup mock to return empty price data
    mock_price_service.get_historical_prices.return_value = {}
    mock_price_service.get_price.return_value = 175.50

    result = get_asset_price_history(
        mock_composite_portfolio, "AAPL", mock_price_service, start_date=None, end_date=None
    )

    # Should return empty prices list but still have current_price
    assert result.ticker == "AAPL"
    assert len(result.prices) == 0
    assert result.current_price == 175.50


# Asset Price History Endpoint Integration Tests

def test_get_asset_price_history_endpoint_success(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint with successful price retrieval."""
    from datetime import date, timedelta
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}
    client_with_portfolio.app.state.composite_portfolio.start_date = date(2023, 1, 1)

    # Setup mock price service
    today = date.today()
    start_date = max(today - timedelta(days=730), date(2023, 1, 1))
    historical_prices = {
        "AAPL": {
            start_date: 150.0,
            start_date + timedelta(days=1): 151.0,
        }
    }
    client_with_portfolio.app.state.price_service.get_historical_prices.return_value = historical_prices
    client_with_portfolio.app.state.price_service.get_price.return_value = 175.50

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/prices/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["asset_type"] == "Stock"
    assert len(data["prices"]) == 2
    assert data["prices"][0]["date"] == start_date.isoformat()
    assert data["prices"][0]["price"] == 150.0
    assert data["current_price"] == 175.50


def test_get_asset_price_history_endpoint_with_date_range(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint with explicit date range."""
    from datetime import date
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup mock price service
    historical_prices = {"AAPL": {date(2024, 1, 1): 150.0, date(2024, 1, 2): 151.0}}
    client_with_portfolio.app.state.price_service.get_historical_prices.return_value = historical_prices
    client_with_portfolio.app.state.price_service.get_price.return_value = 175.50

    # Call endpoint with date range
    response = client_with_portfolio.get(
        "/asset/prices/AAPL?start_date=2024-01-01&end_date=2024-01-02",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert len(data["prices"]) == 2


def test_get_asset_price_history_endpoint_ticker_not_found(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint when ticker is not found."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio with empty assets
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {}

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/prices/INVALID",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_asset_price_history_endpoint_invalid_date_format(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint with invalid date format."""
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Call endpoint with invalid date format
    response = client_with_portfolio.get(
        "/asset/prices/AAPL?start_date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_get_asset_price_history_endpoint_invalid_date_range(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint with invalid date range."""
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Call endpoint with invalid date range (end_date < start_date)
    response = client_with_portfolio.get(
        "/asset/prices/AAPL?start_date=2024-01-05&end_date=2024-01-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 400
    assert "end_date" in response.json()["detail"].lower()


def test_get_asset_price_history_endpoint_unauthorized(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint without authentication."""
    # Call endpoint without token
    response = client_with_portfolio.get("/asset/prices/AAPL")

    # Verify response
    assert response.status_code == 401


def test_get_asset_price_history_endpoint_unexpected_error(client_with_portfolio):
    """Test GET /asset/prices/{ticker} endpoint when unexpected error occurs."""
    from datetime import date
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio to raise unexpected exception when get_assets is called
    # This will trigger the generic Exception handler in the route
    client_with_portfolio.app.state.composite_portfolio.get_assets.side_effect = RuntimeError("Unexpected error")

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/prices/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response - should return 500 for unexpected errors
    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]

