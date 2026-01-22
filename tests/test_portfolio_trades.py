"""Unit and integration tests for portfolio trades endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import get_all_positions, get_asset_trades, get_portfolio_performance


# Tests for /portfolio/trades/<ticker> endpoint
def test_get_asset_trades_service(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() service function."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_trades
    from wpm.models import Asset, Trade as WPMTrade

    # Create mock asset - need to use same object for price map lookup
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    # Mock get_asset_trades method
    mock_composite_portfolio.get_asset_trades.return_value = [trade1, trade2]

    trades = get_asset_trades(mock_composite_portfolio, "AAPL")

    assert len(trades) == 2

    # Check buy trade
    buy_trade = next(t for t in trades if t.action == "Buy")
    assert buy_trade.ticker == "AAPL"
    assert buy_trade.asset_type == "Stock"
    assert buy_trade.action == "Buy"
    assert buy_trade.quantity == 100.0
    assert buy_trade.price == 150.0
    assert buy_trade.broker == "IBKR"

    # Check sell trade
    sell_trade = next(t for t in trades if t.action == "Sell")
    assert sell_trade.ticker == "AAPL"
    assert sell_trade.action == "Sell"
    assert sell_trade.quantity == 50.0
    assert sell_trade.price == 160.0
    assert sell_trade.broker == "Futu"


def test_get_asset_trades_with_date_filtering(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() with date filtering."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_trades
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Buy"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Sell"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    mock_composite_portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    # Filter by date range
    trades = get_asset_trades(
        mock_composite_portfolio,
        "AAPL",
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 28),
    )

    # Should only return trade2 (within date range)
    assert len(trades) == 1
    assert trades[0].date == "2024-02-20"


def test_get_asset_trades_without_prices(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() when market price is not available."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_trades
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    mock_composite_portfolio.get_asset_trades.return_value = [trade1]

    trades = get_asset_trades(mock_composite_portfolio, "AAPL")

    assert len(trades) == 1
    buy_trade = trades[0]
    assert buy_trade.action == "Buy"
    assert buy_trade.broker == "IBKR"


def test_get_asset_trades_invalid_ticker(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() raises ValueError for invalid ticker."""
    from wpm_backend.services.portfolio_service import get_asset_trades

    # Mock get_asset_trades to raise an exception
    mock_composite_portfolio.get_asset_trades.side_effect = ValueError("Ticker not found")

    with pytest.raises(ValueError, match="Failed to retrieve trades"):
        get_asset_trades(mock_composite_portfolio, "INVALID", mock_price_service)


def test_get_asset_trades_sorting_service(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() service function with sorting."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_trades
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 2, 20)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 1, 15)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    # Mock get_asset_trades method - return in non-chronological order
    mock_composite_portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    # Test sorting by date ascending (default)
    trades_asc = get_asset_trades(
        mock_composite_portfolio, "AAPL", sort_by="date", sort_order="asc"
    )

    assert len(trades_asc) == 3
    # Should be sorted ascending by date
    assert trades_asc[0].date == "2024-01-15"
    assert trades_asc[1].date == "2024-02-20"
    assert trades_asc[2].date == "2024-03-10"

    # Test sorting by date descending
    trades_desc = get_asset_trades(
        mock_composite_portfolio, "AAPL", sort_by="date", sort_order="desc"
    )

    assert len(trades_desc) == 3
    # Should be sorted descending by date
    assert trades_desc[0].date == "2024-03-10"
    assert trades_desc[1].date == "2024-02-20"
    assert trades_desc[2].date == "2024-01-15"


def test_get_asset_trades_sorting_invalid_field(mock_composite_portfolio, mock_price_service):
    """Test get_asset_trades() raises ValueError for invalid sort_by field."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_trades
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    mock_composite_portfolio.get_asset_trades.return_value = [trade1]

    with pytest.raises(ValueError, match="Invalid sort_by field"):
        get_asset_trades(
            mock_composite_portfolio, "AAPL", sort_by="invalid_field"
        )


def test_portfolio_asset_trades_endpoint(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with default pagination."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Create mock trades
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    # Mock get_asset_trades
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "trades" in data
    trades = data["trades"]
    assert "items" in trades
    assert "total" in trades
    assert "page" in trades
    assert "size" in trades
    assert "pages" in trades

    assert trades["total"] == 2
    assert trades["page"] == 1
    assert trades["size"] == 20
    assert len(trades["items"]) == 2

    # Check buy trade
    buy_trade = next(t for t in trades["items"] if t["action"] == "Buy")
    assert buy_trade["action"] == "Buy"
    assert buy_trade["broker"] == "IBKR"

    # Check sell trade
    sell_trade = next(t for t in trades["items"] if t["action"] == "Sell")
    assert sell_trade["action"] == "Sell"
    assert sell_trade["broker"] == "Futu"


def test_portfolio_asset_trades_endpoint_with_date_filtering(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with date filtering."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Buy"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?start_date=2024-02-01&end_date=2024-02-28",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    # Should only return trade2 (within date range)
    assert trades["total"] == 1
    assert trades["items"][0]["date"] == "2024-02-20"


def test_portfolio_asset_trades_endpoint_invalid_date_format(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with invalid date format."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?start_date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid start_date format" in response.json()["detail"]


def test_portfolio_asset_trades_endpoint_invalid_date_range(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with invalid date range."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?start_date=2024-02-28&end_date=2024-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]
    assert "end_date" in response.json()["detail"]


def test_portfolio_asset_trades_endpoint_pagination(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with pagination."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create multiple trades
    trades = []
    for i in range(5):
        trade = Mock(spec=WPMTrade)
        trade.date = date(2024, 1, i + 1)
        trade.asset = asset
        trade.action = "Buy"
        trade.order_instruction = "buy"
        trade.quantity = Decimal("10.0")
        trade.price = 150.0 + i
        trade.broker = "IBKR"
        trades.append(trade)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = trades

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?page=1&size=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades_data = data["trades"]
    assert trades_data["total"] == 5
    assert trades_data["page"] == 1
    assert trades_data["size"] == 2
    assert trades_data["pages"] == 3
    assert len(trades_data["items"]) == 2
    # Verify action field is present
    assert "action" in trades_data["items"][0]
    assert trades_data["items"][0]["action"] == "Buy"


def test_portfolio_asset_trades_endpoint_invalid_ticker(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint with invalid ticker."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Mock get_asset_trades to raise ValueError
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.side_effect = ValueError("Ticker INVALID not found")

    response = client_with_portfolio.get(
        "/portfolio/trades/INVALID",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_portfolio_asset_trades_sorting_by_date_asc(client_with_portfolio, test_settings):
    """Test sorting by date in ascending order."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 2, 20)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 1, 15)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?sort_by=date&sort_order=asc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    assert trades["total"] == 3
    # Should be sorted by date ascending (oldest first)
    assert trades["items"][0]["date"] == "2024-01-15"
    assert trades["items"][1]["date"] == "2024-02-20"
    assert trades["items"][2]["date"] == "2024-03-10"


def test_portfolio_asset_trades_sorting_by_date_desc(client_with_portfolio, test_settings):
    """Test sorting by date in descending order."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?sort_by=date&sort_order=desc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    assert trades["total"] == 3
    # Should be sorted by date descending (newest first)
    assert trades["items"][0]["date"] == "2024-03-10"
    assert trades["items"][1]["date"] == "2024-02-20"
    assert trades["items"][2]["date"] == "2024-01-15"


def test_portfolio_asset_trades_sorting_default_date_asc(client_with_portfolio, test_settings):
    """Test default sorting (date ascending)."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 2, 20)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 1, 15)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    # No sort parameters - should default to date ascending
    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    assert trades["total"] == 3
    # Should be sorted by date ascending by default
    assert trades["items"][0]["date"] == "2024-01-15"
    assert trades["items"][1]["date"] == "2024-02-20"
    assert trades["items"][2]["date"] == "2024-03-10"


def test_portfolio_asset_trades_sorting_invalid_field(client_with_portfolio, test_settings):
    """Test sorting with invalid sort_by field."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?sort_by=invalid_field",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid sort_by field" in response.json()["detail"]


def test_portfolio_asset_trades_sorting_with_date_filtering(client_with_portfolio, test_settings):
    """Test sorting works with date filtering."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Buy"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Sell"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    # Filter by date range and sort descending
    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?start_date=2024-02-01&end_date=2024-02-28&sort_by=date&sort_order=desc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    # Should only return trade2 (within date range), sorted descending
    assert trades["total"] == 1
    assert trades["items"][0]["date"] == "2024-02-20"


def test_portfolio_asset_trades_sorting_with_pagination(client_with_portfolio, test_settings):
    """Test sorting works with pagination."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create trades in non-chronological order
    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 3, 10)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("10.0")
    trade1.price = 170.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 1, 15)
    trade2.asset = asset
    trade2.action = "Buy"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("10.0")
    trade2.price = 150.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 2, 20)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("10.0")
    trade3.price = 160.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    # Sort descending, paginate with size=2
    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL?sort_by=date&sort_order=desc&page=1&size=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    assert trades["total"] == 3
    assert trades["page"] == 1
    assert trades["size"] == 2
    assert trades["pages"] == 2
    assert len(trades["items"]) == 2
    # Should be sorted descending, so newest dates first
    assert trades["items"][0]["date"] == "2024-03-10"
    assert trades["items"][1]["date"] == "2024-02-20"


def test_portfolio_asset_trades_endpoint_authentication_required(client_with_portfolio, test_settings):
    """Test /portfolio/trades/<ticker> endpoint requires authentication."""
    response = client_with_portfolio.get("/portfolio/trades/AAPL")

    assert response.status_code == 401
    assert "detail" in response.json()


def test_portfolio_asset_trades_endpoint_no_portfolio(client, test_settings):
    """Test /portfolio/trades/<ticker> endpoint when portfolio is not available."""
    login_response = client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/portfolio/trades/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert "detail" in response.json()


def test_portfolio_asset_trades_endpoint_broker_field(client_with_portfolio, test_settings):
    """Test broker field is included in trade response."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade = Mock(spec=WPMTrade)
    trade.date = date(2024, 1, 15)
    trade.asset = asset
    trade.action = "Buy"
    trade.order_instruction = "buy"
    trade.quantity = Decimal("100.0")
    trade.price = 150.0
    trade.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    buy_trade = data["trades"]["items"][0]

    # Verify broker field is present
    assert buy_trade["action"] == "Buy"
    assert buy_trade["broker"] == "IBKR"


# Tests for /portfolio/trades/{ticker}/all endpoint
def test_portfolio_asset_trades_all_endpoint(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint returns all trades without pagination."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Create mock trades
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    # Mock get_asset_trades
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure - should be a list, not paginated
    assert "trades" in data
    trades = data["trades"]
    assert isinstance(trades, list)
    # Should NOT have pagination fields
    assert "items" not in trades
    assert "total" not in trades
    assert "page" not in trades
    assert "size" not in trades
    assert "pages" not in trades

    # Verify all trades are returned
    assert len(trades) == 2

    # Check buy trade
    buy_trade = next(t for t in trades if t["action"] == "Buy")
    assert buy_trade["action"] == "Buy"
    assert buy_trade["broker"] == "IBKR"
    assert buy_trade["date"] == "2024-01-15"

    # Check sell trade
    sell_trade = next(t for t in trades if t["action"] == "Sell")
    assert sell_trade["action"] == "Sell"
    assert sell_trade["broker"] == "Futu"
    assert sell_trade["date"] == "2024-02-20"


def test_portfolio_asset_trades_all_endpoint_with_date_filtering(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint with date filtering."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Buy"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?start_date=2024-02-01&end_date=2024-02-28",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    # Should only return trade2 (within date range)
    assert len(trades) == 1
    assert trades[0]["date"] == "2024-02-20"


def test_portfolio_asset_trades_all_endpoint_invalid_date_format(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint with invalid date format."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?start_date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid start_date format" in response.json()["detail"]


def test_portfolio_asset_trades_all_endpoint_invalid_date_range(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint with invalid date range."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?start_date=2024-02-28&end_date=2024-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]
    assert "end_date" in response.json()["detail"]


def test_portfolio_asset_trades_all_endpoint_invalid_ticker(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint with invalid ticker."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.side_effect = ValueError("Ticker INVALID not found")

    response = client_with_portfolio.get(
        "/portfolio/trades/INVALID/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_portfolio_asset_trades_all_endpoint_sorting_by_date_asc(client_with_portfolio, test_settings):
    """Test sorting by date in ascending order."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 2, 20)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 1, 15)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    trade3 = Mock(spec=WPMTrade)
    trade3.date = date(2024, 3, 10)
    trade3.asset = asset
    trade3.action = "Buy"
    trade3.order_instruction = "Limit"
    trade3.quantity = Decimal("25.0")
    trade3.price = 170.0
    trade3.broker = "IBKR"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2, trade3]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?sort_by=date&sort_order=asc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    # Should be sorted by date ascending
    assert trades[0]["date"] == "2024-01-15"
    assert trades[1]["date"] == "2024-02-20"
    assert trades[2]["date"] == "2024-03-10"


def test_portfolio_asset_trades_all_endpoint_sorting_by_date_desc(client_with_portfolio, test_settings):
    """Test sorting by date in descending order."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    trade1 = Mock(spec=WPMTrade)
    trade1.date = date(2024, 1, 15)
    trade1.asset = asset
    trade1.action = "Buy"
    trade1.order_instruction = "Limit"
    trade1.quantity = Decimal("100.0")
    trade1.price = 150.0
    trade1.broker = "IBKR"

    trade2 = Mock(spec=WPMTrade)
    trade2.date = date(2024, 2, 20)
    trade2.asset = asset
    trade2.action = "Sell"
    trade2.order_instruction = "Limit"
    trade2.quantity = Decimal("50.0")
    trade2.price = 160.0
    trade2.broker = "Futu"

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = [trade1, trade2]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?sort_by=date&sort_order=desc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    trades = data["trades"]
    # Should be sorted by date descending
    assert trades[0]["date"] == "2024-02-20"
    assert trades[1]["date"] == "2024-01-15"


def test_portfolio_asset_trades_all_endpoint_invalid_sort_by(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint with invalid sort_by field."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all?sort_by=invalid_field",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid sort_by field" in response.json()["detail"]


def test_portfolio_asset_trades_all_endpoint_authentication_required(client_with_portfolio, test_settings):
    """Test /portfolio/trades/{ticker}/all endpoint requires authentication."""
    response = client_with_portfolio.get("/portfolio/trades/AAPL/all")
    assert response.status_code == 401


def test_portfolio_asset_trades_all_endpoint_comparison_with_paginated(client_with_portfolio, test_settings):
    """Test that /all endpoint returns same trades as paginated endpoint (when all pages combined)."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create 5 trades
    trades = []
    for i in range(5):
        trade = Mock(spec=WPMTrade)
        trade.date = date(2024, 1, 15 + i)
        trade.asset = asset
        trade.action = "Buy" if i % 2 == 0 else "Sell"
        trade.order_instruction = "Limit"
        trade.quantity = Decimal(f"{100.0 + i * 10}")
        trade.price = 150.0 + i
        trade.broker = "IBKR" if i % 2 == 0 else "Futu"
        trades.append(trade)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_trades.return_value = trades

    # Get all trades from /all endpoint
    response_all = client_with_portfolio.get(
        "/portfolio/trades/AAPL/all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_all.status_code == 200
    all_trades = response_all.json()["trades"]

    # Get all trades from paginated endpoint (with size=100 to get all)
    response_paginated = client_with_portfolio.get(
        "/portfolio/trades/AAPL?size=100",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response_paginated.status_code == 200
    paginated_trades = response_paginated.json()["trades"]["items"]

    # Both should return the same trades (same count and same data)
    assert len(all_trades) == len(paginated_trades)
    assert len(all_trades) == 5

    # Verify trades match (comparing by date since order should be the same)
    all_dates = [t["date"] for t in all_trades]
    paginated_dates = [t["date"] for t in paginated_trades]
    assert sorted(all_dates) == sorted(paginated_dates)


# Tests for /portfolio/lots/<ticker> endpoint
