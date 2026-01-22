"""Unit and integration tests for portfolio lots endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import get_all_positions, get_asset_brokers, get_asset_lots, get_asset_positions_by_broker, get_portfolio_performance


def test_get_asset_lots_service(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() service function."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset, Trade as WPMTrade

    # Create mock asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create mock lot
    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0

    # Create mock matched sell
    matched_sell_trade = Mock(spec=WPMTrade)
    matched_sell_trade.date = date(2024, 2, 20)
    matched_sell_trade.asset = asset
    matched_sell_trade.action = "Sell"
    matched_sell_trade.order_instruction = "Limit"
    matched_sell_trade.quantity = Decimal("25.0")
    matched_sell_trade.price = 160.0
    matched_sell_trade.broker = "IBKR"

    matched_sell = Mock()
    matched_sell.trade = matched_sell_trade
    matched_sell.consumed_quantity = Decimal("25.0")

    lot.matched_sells = [matched_sell]
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    # Mock get_asset_lots method
    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    api_lot = lots[0]
    assert api_lot.ticker == "AAPL"
    assert api_lot.asset_type == "Stock"
    assert api_lot.date == "2024-01-15"
    assert api_lot.original_quantity == 100.0
    assert api_lot.remaining_quantity == 75.0
    assert api_lot.cost_basis == 15000.0
    assert len(api_lot.matched_sells) == 1
    assert api_lot.matched_sells[0].consumed_quantity == 25.0
    assert api_lot.matched_sells[0].trade.action == "Sell"
    assert api_lot.matched_sells[0].trade.broker == "IBKR"
    assert api_lot.broker == "IBKR"
    assert api_lot.realized_pnl == 250.0
    assert api_lot.unrealized_pnl == 500.0
    assert api_lot.total_pnl == 750.0


def test_get_asset_lots_with_date_filtering(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() with date filtering."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    lot3 = Mock()
    lot3.purchase_date = date(2024, 3, 10)
    lot3.asset = asset
    lot3.original_quantity = Decimal("25.0")
    lot3.remaining_quantity = Decimal("25.0")
    lot3.cost_basis = 3750.0
    lot3.matched_sells = []
    lot3.broker = "IBKR"
    lot3.get_realized_pnl = Mock(return_value=0.0)
    lot3.get_unrealized_pnl = Mock(return_value=50.0)
    lot3.get_total_pnl = Mock(return_value=50.0)

    # Mock get_asset_lots to return filtered lots when dates are provided
    def mock_get_asset_lots(ticker, start_date=None, end_date=None, brokers=None, prices=None):
        all_lots = [lot1, lot2, lot3]
        filtered = []
        for lot in all_lots:
            lot_date = lot.purchase_date
            if start_date is not None and lot_date < start_date:
                continue
            if end_date is not None and lot_date > end_date:
                continue
            filtered.append(lot)
        return filtered

    mock_composite_portfolio.get_asset_lots.side_effect = mock_get_asset_lots

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Filter by date range
        lots = get_asset_lots(
            mock_composite_portfolio,
            "AAPL",
            mock_price_service,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 28),
        )

    # Should only return lot2 (within date range)
    assert len(lots) == 1
    assert lots[0].date == "2024-02-20"


def test_get_asset_lots_sorting(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() service function with sorting."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 2, 20)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("75.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 1, 15)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 5000.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    lot3 = Mock()
    lot3.purchase_date = date(2024, 3, 10)
    lot3.asset = asset
    lot3.original_quantity = Decimal("25.0")
    lot3.remaining_quantity = Decimal("25.0")
    lot3.cost_basis = 2500.0
    lot3.matched_sells = []
    lot3.broker = "IBKR"
    lot3.get_realized_pnl = Mock(return_value=0.0)
    lot3.get_unrealized_pnl = Mock(return_value=50.0)
    lot3.get_total_pnl = Mock(return_value=50.0)

    # Mock get_asset_lots method - return in non-chronological order
    mock_composite_portfolio.get_asset_lots.return_value = [lot1, lot2, lot3]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test sorting by date ascending (default)
        lots_asc = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="date", sort_order="asc"
        )

        assert len(lots_asc) == 3
        # Should be sorted ascending by date
        assert lots_asc[0].date == "2024-01-15"
        assert lots_asc[1].date == "2024-02-20"
        assert lots_asc[2].date == "2024-03-10"

        # Test sorting by date descending
        lots_desc = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="date", sort_order="desc"
        )

        assert len(lots_desc) == 3
        # Should be sorted descending by date
        assert lots_desc[0].date == "2024-03-10"
        assert lots_desc[1].date == "2024-02-20"
        assert lots_desc[2].date == "2024-01-15"

        # Test sorting by original_quantity
        lots_qty = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="original_quantity", sort_order="asc"
        )

        assert len(lots_qty) == 3
        assert lots_qty[0].original_quantity == 25.0
        assert lots_qty[1].original_quantity == 50.0
        assert lots_qty[2].original_quantity == 100.0

        # Test sorting by cost_basis
        lots_cost = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="cost_basis", sort_order="desc"
        )

    assert len(lots_cost) == 3
    assert lots_cost[0].cost_basis == 15000.0
    assert lots_cost[1].cost_basis == 5000.0
    assert lots_cost[2].cost_basis == 2500.0


def test_get_asset_lots_sorting_invalid_field(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() raises ValueError for invalid sort_by field."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("100.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=0.0)
    lot.get_unrealized_pnl = Mock(return_value=100.0)
    lot.get_total_pnl = Mock(return_value=100.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with pytest.raises(ValueError, match="Invalid sort_by field"):
            get_asset_lots(
                mock_composite_portfolio, "AAPL", mock_price_service, sort_by="invalid_field"
            )


def test_get_asset_lots_invalid_ticker(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() raises ValueError for invalid ticker."""
    from wpm_backend.services.portfolio_service import get_asset_lots

    # Mock get_asset_lots to raise an exception
    mock_composite_portfolio.get_asset_lots.side_effect = ValueError("Ticker not found")

    with pytest.raises(ValueError, match="Failed to retrieve lots"):
        get_asset_lots(mock_composite_portfolio, "INVALID", mock_price_service)


def test_get_asset_lots_matched_sells(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() includes matched sells correctly."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create lot with multiple matched sells
    matched_sell1_trade = Mock(spec=WPMTrade)
    matched_sell1_trade.date = date(2024, 2, 20)
    matched_sell1_trade.asset = asset
    matched_sell1_trade.action = "Sell"
    matched_sell1_trade.order_instruction = "Limit"
    matched_sell1_trade.quantity = Decimal("15.0")
    matched_sell1_trade.price = 160.0
    matched_sell1_trade.broker = "IBKR"

    matched_sell1 = Mock()
    matched_sell1.trade = matched_sell1_trade
    matched_sell1.consumed_quantity = Decimal("15.0")

    matched_sell2_trade = Mock(spec=WPMTrade)
    matched_sell2_trade.date = date(2024, 3, 10)
    matched_sell2_trade.asset = asset
    matched_sell2_trade.action = "Sell"
    matched_sell2_trade.order_instruction = "Market"
    matched_sell2_trade.quantity = Decimal("10.0")
    matched_sell2_trade.price = 170.0
    matched_sell2_trade.broker = "Futu"

    matched_sell2 = Mock()
    matched_sell2.trade = matched_sell2_trade
    matched_sell2.consumed_quantity = Decimal("10.0")

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = [matched_sell1, matched_sell2]
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    api_lot = lots[0]
    assert len(api_lot.matched_sells) == 2
    assert api_lot.matched_sells[0].consumed_quantity == 15.0
    assert api_lot.matched_sells[0].trade.broker == "IBKR"
    assert api_lot.matched_sells[1].consumed_quantity == 10.0
    assert api_lot.matched_sells[1].trade.broker == "Futu"


def test_portfolio_asset_lots_endpoint(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with default pagination."""
    from datetime import date
    from wpm.models import Asset, Trade as WPMTrade

    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Create mock lot
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    # Mock get_asset_lots
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "lots" in data
    lots = data["lots"]
    assert "items" in lots
    assert "total" in lots
    assert "page" in lots
    assert "size" in lots
    assert "pages" in lots

    assert lots["total"] == 1
    assert lots["page"] == 1
    assert lots["size"] == 20
    assert len(lots["items"]) == 1
    assert lots["items"][0]["ticker"] == "AAPL"
    assert lots["items"][0]["date"] == "2024-01-15"
    # Verify new fields are present
    assert "broker" in lots["items"][0]
    assert lots["items"][0]["broker"] == "IBKR"
    assert "realized_pnl" in lots["items"][0]
    assert lots["items"][0]["realized_pnl"] == 250.0
    assert "unrealized_pnl" in lots["items"][0]
    assert lots["items"][0]["unrealized_pnl"] == 500.0
    assert "total_pnl" in lots["items"][0]
    assert lots["items"][0]["total_pnl"] == 750.0


def test_portfolio_asset_lots_endpoint_with_date_filtering(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with date filtering."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio

    # Mock get_asset_lots to return filtered lots when dates are provided
    def mock_get_asset_lots(ticker, start_date=None, end_date=None, brokers=None, prices=None):
        all_lots = [lot1, lot2]
        filtered = []
        for lot in all_lots:
            lot_date = lot.purchase_date
            if start_date is not None and lot_date < start_date:
                continue
            if end_date is not None and lot_date > end_date:
                continue
            filtered.append(lot)
        return filtered

    portfolio.get_asset_lots.side_effect = mock_get_asset_lots
    portfolio.get_asset_positions_by_broker.return_value = {}  # Empty positions for date-filtered test

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?start_date=2024-02-01&end_date=2024-02-28",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lots = data["lots"]
    # Should only return lot2 (within date range)
    assert lots["total"] == 1
    assert lots["items"][0]["date"] == "2024-02-20"


def test_portfolio_asset_lots_endpoint_invalid_date_format(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with invalid date format."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/lots/AAPL?start_date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid start_date format" in response.json()["detail"]


def test_portfolio_asset_lots_endpoint_invalid_date_range(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with invalid date range."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    response = client_with_portfolio.get(
        "/portfolio/lots/AAPL?start_date=2024-02-28&end_date=2024-02-01",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]
    assert "end_date" in response.json()["detail"]


def test_portfolio_asset_lots_endpoint_pagination(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with pagination."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create multiple lots
    lots = []
    for i in range(5):
        lot = Mock()
        lot.purchase_date = date(2024, 1, i + 1)
        lot.asset = asset
        lot.original_quantity = Decimal("10.0")
        lot.remaining_quantity = Decimal("10.0")
        lot.cost_basis = 1500.0 + i * 100
        lot.matched_sells = []
        lot.broker = "IBKR"
        lot.get_realized_pnl = Mock(return_value=0.0)
        lot.get_unrealized_pnl = Mock(return_value=100.0)
        lot.get_total_pnl = Mock(return_value=100.0)
        lots.append(lot)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = lots

    # Mock fetch_price_map
    mock_price_map = {asset: 110.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?page=1&size=2",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lots_data = data["lots"]
    assert lots_data["total"] == 5
    assert lots_data["page"] == 1
    assert lots_data["size"] == 2
    assert lots_data["pages"] == 3
    assert len(lots_data["items"]) == 2


def test_portfolio_asset_lots_endpoint_invalid_ticker(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with invalid ticker."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Mock get_asset_lots to raise ValueError
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.side_effect = ValueError("Ticker INVALID not found")

    response = client_with_portfolio.get(
        "/portfolio/lots/INVALID",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "detail" in response.json()


def test_portfolio_asset_lots_sorting_by_date_asc(client_with_portfolio, test_settings):
    """Test sorting by date in ascending order."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 2, 20)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 1, 15)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 5000.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    lot3 = Mock()
    lot3.purchase_date = date(2024, 3, 10)
    lot3.asset = asset
    lot3.original_quantity = Decimal("25.0")
    lot3.remaining_quantity = Decimal("25.0")
    lot3.cost_basis = 2500.0
    lot3.matched_sells = []
    lot3.broker = "IBKR"
    lot3.get_realized_pnl = Mock(return_value=0.0)
    lot3.get_unrealized_pnl = Mock(return_value=50.0)
    lot3.get_total_pnl = Mock(return_value=50.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot1, lot2, lot3]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?sort_by=date&sort_order=asc",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lots = data["lots"]
    assert lots["total"] == 3
    # Should be sorted by date ascending (oldest first)
    assert lots["items"][0]["date"] == "2024-01-15"
    assert lots["items"][1]["date"] == "2024-02-20"
    assert lots["items"][2]["date"] == "2024-03-10"


def test_portfolio_asset_lots_sorting_by_date_desc(client_with_portfolio, test_settings):
    """Test sorting by date in descending order."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 5000.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    lot3 = Mock()
    lot3.purchase_date = date(2024, 3, 10)
    lot3.asset = asset
    lot3.original_quantity = Decimal("25.0")
    lot3.remaining_quantity = Decimal("25.0")
    lot3.cost_basis = 2500.0
    lot3.matched_sells = []
    lot3.broker = "IBKR"
    lot3.get_realized_pnl = Mock(return_value=0.0)
    lot3.get_unrealized_pnl = Mock(return_value=50.0)
    lot3.get_total_pnl = Mock(return_value=50.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot1, lot2, lot3]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?sort_by=date&sort_order=desc",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lots = data["lots"]
    assert lots["total"] == 3
    # Should be sorted by date descending (newest first)
    assert lots["items"][0]["date"] == "2024-03-10"
    assert lots["items"][1]["date"] == "2024-02-20"
    assert lots["items"][2]["date"] == "2024-01-15"


def test_portfolio_asset_lots_sorting_by_original_quantity(client_with_portfolio, test_settings):
    """Test sorting by original_quantity."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("25.0")
    lot2.remaining_quantity = Decimal("25.0")
    lot2.cost_basis = 2500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot1, lot2]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?sort_by=original_quantity&sort_order=asc",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lots = data["lots"]
    assert lots["total"] == 2
    # Should be sorted by original_quantity ascending
    assert lots["items"][0]["original_quantity"] == 25.0
    assert lots["items"][1]["original_quantity"] == 100.0


def test_portfolio_asset_lots_sorting_invalid_field(client_with_portfolio, test_settings):
    """Test sorting with invalid sort_by field."""
    from datetime import date
    from wpm.models import Asset

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("100.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=0.0)
    lot.get_unrealized_pnl = Mock(return_value=100.0)
    lot.get_total_pnl = Mock(return_value=100.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?sort_by=invalid_field",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 400
    assert "Invalid sort_by field" in response.json()["detail"]


def test_portfolio_asset_lots_endpoint_authentication_required(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint requires authentication."""
    response = client_with_portfolio.get("/portfolio/lots/AAPL")

    assert response.status_code == 401
    assert "detail" in response.json()


def test_portfolio_asset_lots_endpoint_matched_sells(client_with_portfolio, test_settings):
    """Test matched sells are included in lot response."""
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

    matched_sell_trade = Mock(spec=WPMTrade)
    matched_sell_trade.date = date(2024, 2, 20)
    matched_sell_trade.asset = asset
    matched_sell_trade.action = "Sell"
    matched_sell_trade.order_instruction = "Limit"
    matched_sell_trade.quantity = Decimal("25.0")
    matched_sell_trade.price = 160.0
    matched_sell_trade.broker = "IBKR"

    matched_sell = Mock()
    matched_sell.trade = matched_sell_trade
    matched_sell.consumed_quantity = Decimal("25.0")

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = [matched_sell]
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    lot_data = data["lots"]["items"][0]

    # Verify matched sells are present
    assert "matched_sells" in lot_data
    assert len(lot_data["matched_sells"]) == 1
    assert lot_data["matched_sells"][0]["consumed_quantity"] == 25.0
    assert lot_data["matched_sells"][0]["trade"]["action"] == "Sell"
    assert lot_data["matched_sells"][0]["trade"]["broker"] == "IBKR"

    # Verify new fields
    assert "broker" in lot_data
    assert lot_data["broker"] == "IBKR"
    assert "realized_pnl" in lot_data
    assert lot_data["realized_pnl"] == 250.0
    assert "unrealized_pnl" in lot_data
    assert lot_data["unrealized_pnl"] == 500.0
    assert "total_pnl" in lot_data
    assert lot_data["total_pnl"] == 750.0


def test_get_asset_lots_broker_field(mock_composite_portfolio, mock_price_service):
    """Test broker field is extracted correctly from wpm_lot.broker."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("100.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "Futu"
    lot.get_realized_pnl = Mock(return_value=0.0)
    lot.get_unrealized_pnl = Mock(return_value=100.0)
    lot.get_total_pnl = Mock(return_value=100.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].broker == "Futu"


def test_get_asset_lots_with_broker_filtering(mock_composite_portfolio, mock_price_service):
    """Test get_asset_lots() with broker filtering."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    lot3 = Mock()
    lot3.purchase_date = date(2024, 3, 10)
    lot3.asset = asset
    lot3.original_quantity = Decimal("25.0")
    lot3.remaining_quantity = Decimal("25.0")
    lot3.cost_basis = 2500.0
    lot3.matched_sells = []
    lot3.broker = "IBKR"
    lot3.get_realized_pnl = Mock(return_value=0.0)
    lot3.get_unrealized_pnl = Mock(return_value=50.0)
    lot3.get_total_pnl = Mock(return_value=50.0)

    # Mock get_asset_lots to return filtered lots when brokers parameter is provided
    def mock_get_asset_lots(ticker, start_date=None, end_date=None, brokers=None, prices=None):
        all_lots = [lot1, lot2, lot3]
        if brokers:
            return [lot for lot in all_lots if lot.broker in brokers]
        return all_lots

    mock_composite_portfolio.get_asset_lots.side_effect = mock_get_asset_lots

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test without broker filtering
        all_lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)
        assert len(all_lots) == 3

        # Test with broker filtering (IBKR only)
        ibkr_lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service, brokers=["IBKR"])
        assert len(ibkr_lots) == 2
        assert all(lot.broker == "IBKR" for lot in ibkr_lots)

        # Test with broker filtering (Futu only)
        futu_lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service, brokers=["Futu"])
        assert len(futu_lots) == 1
        assert futu_lots[0].broker == "Futu"

        # Test with multiple brokers
        multi_lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service, brokers=["IBKR", "Futu"])
        assert len(multi_lots) == 3


def test_get_asset_positions_by_broker(mock_composite_portfolio, mock_price_service):
    """Test get_asset_positions_by_broker() service function."""
    from wpm_backend.services.portfolio_service import get_asset_positions_by_broker
    from wpm.models import Asset, Position as WPMPosition

    # Create mock asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create mock positions for different brokers
    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    # Mock get_asset_positions_by_broker
    mock_composite_portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        overall_position, per_broker_positions = get_asset_positions_by_broker(
            mock_composite_portfolio, "AAPL", mock_price_service
        )

    # Verify overall position
    assert overall_position.quantity == 150.0  # 100 + 50
    assert overall_position.cost_basis == 22500.0  # 15000 + 7500
    assert overall_position.market_value == 26325.0  # (100 * 175.50) + (50 * 175.50) = 17550.0 + 8775.0

    # Verify per-broker positions
    assert len(per_broker_positions) == 2
    broker_dict = {bp.broker: bp for bp in per_broker_positions}
    
    ibkr_pos = broker_dict["IBKR"]
    assert ibkr_pos.quantity == 100.0
    assert ibkr_pos.cost_basis == 15000.0
    assert ibkr_pos.market_value == 17550.0  # 100 * 175.50

    futu_pos = broker_dict["Futu"]
    assert futu_pos.quantity == 50.0
    assert futu_pos.cost_basis == 7500.0
    assert futu_pos.market_value == 8775.0  # 50 * 175.50


def test_get_asset_positions_by_broker_with_filtering(mock_composite_portfolio, mock_price_service):
    """Test get_asset_positions_by_broker() with broker filtering."""
    from wpm_backend.services.portfolio_service import get_asset_positions_by_broker
    from wpm.models import Asset, Position as WPMPosition

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    position_crypto = Mock(spec=WPMPosition)
    position_crypto.asset = asset
    position_crypto.quantity = Decimal("25.0")
    position_crypto.cost_basis = 2500.0

    mock_composite_portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
        "Crypto": position_crypto,
    }

    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test with broker filtering (IBKR only)
        overall_position, per_broker_positions = get_asset_positions_by_broker(
            mock_composite_portfolio, "AAPL", mock_price_service, brokers=["IBKR"]
        )

    # Verify filtered results
    assert overall_position.quantity == 100.0
    assert overall_position.cost_basis == 15000.0
    assert overall_position.market_value == 16000.0  # 100 * 160.0

    assert len(per_broker_positions) == 1
    assert per_broker_positions[0].broker == "IBKR"
    assert per_broker_positions[0].quantity == 100.0


def test_get_asset_positions_by_broker_missing_price(mock_composite_portfolio, mock_price_service):
    """Test get_asset_positions_by_broker() when price is unavailable."""
    from wpm_backend.services.portfolio_service import get_asset_positions_by_broker
    from wpm.models import Asset, Position as WPMPosition

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    position = Mock(spec=WPMPosition)
    position.asset = asset
    position.quantity = Decimal("100.0")
    position.cost_basis = 15000.0

    mock_composite_portfolio.get_asset_positions_by_broker.return_value = {"IBKR": position}

    # Mock fetch_price_map with None price
    mock_price_map = {asset: None}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        overall_position, per_broker_positions = get_asset_positions_by_broker(
            mock_composite_portfolio, "AAPL", mock_price_service
        )

    # Verify market_value is None when price unavailable
    assert overall_position.quantity == 100.0
    assert overall_position.cost_basis == 15000.0
    assert overall_position.market_value is None

    assert len(per_broker_positions) == 1
    assert per_broker_positions[0].market_value is None


def test_get_asset_brokers(mock_composite_portfolio):
    """Test get_asset_brokers() service function."""
    from wpm_backend.services.portfolio_service import get_asset_brokers
    from wpm.models import Asset, Position as WPMPosition

    # Create mock asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create mock positions for different brokers
    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    # Mock get_asset_positions_by_broker
    mock_composite_portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    # Test service function
    brokers = get_asset_brokers(mock_composite_portfolio, "AAPL")

    # Verify broker list
    assert len(brokers) == 2
    assert "IBKR" in brokers
    assert "Futu" in brokers
    # Verify order matches dictionary keys order
    assert brokers == ["IBKR", "Futu"] or brokers == ["Futu", "IBKR"]


def test_get_asset_brokers_empty(mock_composite_portfolio):
    """Test get_asset_brokers() when ticker has no positions."""
    from wpm_backend.services.portfolio_service import get_asset_brokers

    # Mock get_asset_positions_by_broker to return empty dict
    mock_composite_portfolio.get_asset_positions_by_broker.return_value = {}

    # Test service function
    brokers = get_asset_brokers(mock_composite_portfolio, "AAPL")

    # Verify empty list
    assert brokers == []


def test_get_asset_brokers_ticker_not_found(mock_composite_portfolio):
    """Test get_asset_brokers() when ticker doesn't exist."""
    from wpm_backend.services.portfolio_service import get_asset_brokers

    # Mock get_asset_positions_by_broker to raise ValueError
    mock_composite_portfolio.get_asset_positions_by_broker.side_effect = ValueError("Ticker INVALID not found")

    # Test that ValueError is raised
    with pytest.raises(ValueError, match="Ticker INVALID not found"):
        get_asset_brokers(mock_composite_portfolio, "INVALID")


def test_portfolio_asset_lots_endpoint_with_brokers(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with brokers parameter."""
    from datetime import date
    from wpm.models import Asset, Position as WPMPosition

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create lots for different brokers
    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    # Create positions for different brokers
    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    portfolio = client_with_portfolio.app.state.composite_portfolio

    # Mock get_asset_lots to filter by brokers
    def mock_get_asset_lots(ticker, start_date=None, end_date=None, brokers=None, prices=None):
        all_lots = [lot1, lot2]
        if brokers:
            return [lot for lot in all_lots if lot.broker in brokers]
        return all_lots

    portfolio.get_asset_lots.side_effect = mock_get_asset_lots
    portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test with brokers parameter
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?brokers=IBKR",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()

    # Verify lots are filtered
    assert "lots" in data
    assert len(data["lots"]["items"]) == 1
    assert data["lots"]["items"][0]["broker"] == "IBKR"

    # Verify overall_position is present
    assert "overall_position" in data
    assert data["overall_position"]["quantity"] == 100.0
    assert data["overall_position"]["cost_basis"] == 15000.0
    assert data["overall_position"]["market_value"] == 17550.0  # 100 * 175.50

    # Verify per_broker_positions is present and filtered
    assert "per_broker_positions" in data
    assert len(data["per_broker_positions"]) == 1
    assert data["per_broker_positions"][0]["broker"] == "IBKR"
    assert data["per_broker_positions"][0]["quantity"] == 100.0


def test_portfolio_asset_lots_endpoint_without_brokers(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint without brokers parameter returns all positions."""
    from datetime import date
    from wpm.models import Asset, Position as WPMPosition

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_lots.return_value = [lot1, lot2]
    portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()

    # Verify all lots are returned
    assert len(data["lots"]["items"]) == 2

    # Verify overall_position aggregates all brokers
    assert data["overall_position"]["quantity"] == 150.0  # 100 + 50
    assert data["overall_position"]["cost_basis"] == 22500.0  # 15000 + 7500
    assert data["overall_position"]["market_value"] == 26325.0  # (100 * 175.50) + (50 * 175.50) = 17550.0 + 8775.0

    # Verify all per_broker_positions are returned
    assert len(data["per_broker_positions"]) == 2
    brokers = [bp["broker"] for bp in data["per_broker_positions"]]
    assert "IBKR" in brokers
    assert "Futu" in brokers


def test_portfolio_asset_lots_endpoint_brokers_comma_separated(client_with_portfolio, test_settings):
    """Test /portfolio/lots/<ticker> endpoint with comma-separated brokers."""
    from datetime import date
    from wpm.models import Asset, Position as WPMPosition

    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "IBKR"
    lot1.get_realized_pnl = Mock(return_value=0.0)
    lot1.get_unrealized_pnl = Mock(return_value=100.0)
    lot1.get_total_pnl = Mock(return_value=100.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 7500.0
    lot2.matched_sells = []
    lot2.broker = "Futu"
    lot2.get_realized_pnl = Mock(return_value=0.0)
    lot2.get_unrealized_pnl = Mock(return_value=200.0)
    lot2.get_total_pnl = Mock(return_value=200.0)

    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    portfolio = client_with_portfolio.app.state.composite_portfolio

    def mock_get_asset_lots(ticker, start_date=None, end_date=None, brokers=None, prices=None):
        all_lots = [lot1, lot2]
        if brokers:
            return [lot for lot in all_lots if lot.broker in brokers]
        return all_lots

    portfolio.get_asset_lots.side_effect = mock_get_asset_lots
    portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test with comma-separated brokers
        response = client_with_portfolio.get(
            "/portfolio/lots/AAPL?brokers=IBKR,Futu",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()

    # Verify both brokers are included
    assert len(data["lots"]["items"]) == 2
    assert len(data["per_broker_positions"]) == 2
    brokers = [bp["broker"] for bp in data["per_broker_positions"]]
    assert "IBKR" in brokers
    assert "Futu" in brokers


def test_get_asset_lots_realized_pnl(mock_composite_portfolio, mock_price_service):
    """Test that get_realized_pnl() is called and value is included."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset, Trade as WPMTrade

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    # Create lot with matched sells
    matched_sell_trade = Mock(spec=WPMTrade)
    matched_sell_trade.date = date(2024, 2, 20)
    matched_sell_trade.asset = asset
    matched_sell_trade.action = "Sell"
    matched_sell_trade.order_instruction = "Limit"
    matched_sell_trade.quantity = Decimal("25.0")
    matched_sell_trade.price = 160.0
    matched_sell_trade.broker = "IBKR"

    matched_sell = Mock()
    matched_sell.trade = matched_sell_trade
    matched_sell.consumed_quantity = Decimal("25.0")

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = [matched_sell]
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].realized_pnl == 250.0
    lot.get_realized_pnl.assert_called_once()


def test_get_asset_lots_unrealized_pnl(mock_composite_portfolio, mock_price_service):
    """Test that get_unrealized_pnl(current_price) is called with current_price and value is included."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=0.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=500.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map with price available
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].unrealized_pnl == 500.0
    lot.get_unrealized_pnl.assert_called_once_with(175.50)


def test_get_asset_lots_unrealized_pnl_no_price(mock_composite_portfolio, mock_price_service):
    """Test that unrealized_pnl is None when current_price is unavailable (method not called)."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=0.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=0.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map with no price (None)
    mock_price_map = {asset: None}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].unrealized_pnl is None
    # get_unrealized_pnl should not be called when price is None
    lot.get_unrealized_pnl.assert_not_called()


def test_get_asset_lots_total_pnl(mock_composite_portfolio, mock_price_service):
    """Test that get_total_pnl(current_price) is called and value is included."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=750.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map
    mock_price_map = {asset: 175.50}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].total_pnl == 750.0
    lot.get_total_pnl.assert_called_once_with(175.50)


def test_get_asset_lots_total_pnl_no_price(mock_composite_portfolio, mock_price_service):
    """Test that get_total_pnl(None) is called when price is unavailable."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot = Mock()
    lot.purchase_date = date(2024, 1, 15)
    lot.asset = asset
    lot.original_quantity = Decimal("100.0")
    lot.remaining_quantity = Decimal("75.0")
    lot.cost_basis = 15000.0
    lot.matched_sells = []
    lot.broker = "IBKR"
    lot.get_realized_pnl = Mock(return_value=250.0)
    lot.get_unrealized_pnl = Mock(return_value=500.0)
    lot.get_total_pnl = Mock(return_value=250.0)  # Only realized when price is None

    mock_composite_portfolio.get_asset_lots.return_value = [lot]

    # Mock fetch_price_map with no price (None)
    mock_price_map = {asset: None}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        lots = get_asset_lots(mock_composite_portfolio, "AAPL", mock_price_service)

    assert len(lots) == 1
    assert lots[0].total_pnl == 250.0
    lot.get_total_pnl.assert_called_once_with(None)


def test_get_asset_lots_sorting_new_fields(mock_composite_portfolio, mock_price_service):
    """Test sorting by broker, realized_pnl, unrealized_pnl, total_pnl."""
    from datetime import date
    from wpm_backend.services.portfolio_service import get_asset_lots
    from wpm.models import Asset

    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"

    lot1 = Mock()
    lot1.purchase_date = date(2024, 1, 15)
    lot1.asset = asset
    lot1.original_quantity = Decimal("100.0")
    lot1.remaining_quantity = Decimal("100.0")
    lot1.cost_basis = 15000.0
    lot1.matched_sells = []
    lot1.broker = "Futu"
    lot1.get_realized_pnl = Mock(return_value=100.0)
    lot1.get_unrealized_pnl = Mock(return_value=200.0)
    lot1.get_total_pnl = Mock(return_value=300.0)

    lot2 = Mock()
    lot2.purchase_date = date(2024, 2, 20)
    lot2.asset = asset
    lot2.original_quantity = Decimal("50.0")
    lot2.remaining_quantity = Decimal("50.0")
    lot2.cost_basis = 5000.0
    lot2.matched_sells = []
    lot2.broker = "IBKR"
    lot2.get_realized_pnl = Mock(return_value=200.0)
    lot2.get_unrealized_pnl = Mock(return_value=300.0)
    lot2.get_total_pnl = Mock(return_value=500.0)

    mock_composite_portfolio.get_asset_lots.return_value = [lot1, lot2]

    # Mock fetch_price_map
    mock_price_map = {asset: 160.0}
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test sorting by broker
        lots_broker = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="broker", sort_order="asc"
        )
        assert lots_broker[0].broker == "Futu"
        assert lots_broker[1].broker == "IBKR"

        # Test sorting by realized_pnl
        lots_realized = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="realized_pnl", sort_order="asc"
        )
        assert lots_realized[0].realized_pnl == 100.0
        assert lots_realized[1].realized_pnl == 200.0

        # Test sorting by unrealized_pnl
        lots_unrealized = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="unrealized_pnl", sort_order="asc"
        )
        assert lots_unrealized[0].unrealized_pnl == 200.0
        assert lots_unrealized[1].unrealized_pnl == 300.0

        # Test sorting by total_pnl
        lots_total = get_asset_lots(
            mock_composite_portfolio, "AAPL", mock_price_service, sort_by="total_pnl", sort_order="asc"
        )
        assert lots_total[0].total_pnl == 300.0
        assert lots_total[1].total_pnl == 500.0



def test_get_asset_brokers_endpoint_success(client_with_portfolio):
    """Test GET /asset/brokers/{ticker} endpoint with successful retrieval."""
    from wpm.models import Asset, Position as WPMPosition

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

    position_ibkr = Mock(spec=WPMPosition)
    position_ibkr.asset = asset
    position_ibkr.quantity = Decimal("100.0")
    position_ibkr.cost_basis = 15000.0

    position_futu = Mock(spec=WPMPosition)
    position_futu.asset = asset
    position_futu.quantity = Decimal("50.0")
    position_futu.cost_basis = 7500.0

    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_positions_by_broker.return_value = {
        "IBKR": position_ibkr,
        "Futu": position_futu,
    }

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/brokers/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert len(data["brokers"]) == 2
    assert "IBKR" in data["brokers"]
    assert "Futu" in data["brokers"]


def test_get_asset_brokers_endpoint_empty(client_with_portfolio):
    """Test GET /asset/brokers/{ticker} endpoint when ticker has no positions."""
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio with empty positions
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_positions_by_broker.return_value = {}

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/brokers/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response (empty list is valid)
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["brokers"] == []


def test_get_asset_brokers_endpoint_not_found(client_with_portfolio):
    """Test GET /asset/brokers/{ticker} endpoint when ticker is not found."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio to raise ValueError
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_asset_positions_by_broker.side_effect = ValueError("Failed to retrieve brokers for ticker INVALID: Ticker not found")

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/brokers/INVALID",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower() or "INVALID" in response.json()["detail"]


def test_get_asset_brokers_endpoint_unauthorized(client_with_portfolio):
    """Test GET /asset/brokers/{ticker} endpoint without authentication."""
    # Call endpoint without token
    response = client_with_portfolio.get("/asset/brokers/AAPL")

    # Verify response
    assert response.status_code == 401


# Asset Price History Service Function Tests

