"""Unit and integration tests for portfolio endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import get_all_positions, get_portfolio_performance


def test_get_all_positions_service(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() service function with default sorting."""
    from wpm.models import Asset

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations
    # Total market value: 17550.0 + 7500.0 = 25050.0
    # AAPL allocation: (17550.0 / 25050.0) * 100 = 70.06%
    # GOOGL allocation: (7500.0 / 25050.0) * 100 = 29.94%
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl for each asset
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    assert len(positions) == 2

    # With default sorting (ticker asc), AAPL should come first
    position1 = positions[0]
    assert position1.ticker == "AAPL"
    assert position1.asset_type == "Stock"
    assert position1.quantity == 100.0
    assert position1.cost_basis == 15000.0
    assert position1.cost_basis_method == "fifo"
    assert position1.current_price == 175.50
    assert position1.market_value == 17550.0  # 100 * 175.50
    assert position1.unrealized_gain_loss == 2550.0  # 17550 - 15000
    assert position1.allocation_percentage == 70.06
    assert position1.realized_gain_loss == 500.0

    # Check second position (GOOGL)
    position2 = positions[1]
    assert position2.ticker == "GOOGL"
    assert position2.asset_type == "Stock"
    assert position2.quantity == 50.0
    assert position2.cost_basis == 5000.0
    assert position2.cost_basis_method == "average"
    assert position2.current_price == 150.00
    assert position2.market_value == 7500.0  # 50 * 150.00
    assert position2.unrealized_gain_loss == 2500.0  # 7500 - 5000
    assert position2.allocation_percentage == 29.94
    assert position2.realized_gain_loss == -200.0


def test_get_all_positions_without_prices(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() when prices are not available."""
    # Mock fetch_price_map to return None for all assets
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: None,
        assets[1]: None,
    }

    # Mock get_positions_with_allocations - when prices are None, allocations should be 0.00
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("0.00")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("0.00")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    assert len(positions) == 2

    # Mock get_asset_realized_pnl for each asset
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 100.0,
        "GOOGL": 50.0,
    }.get(ticker, 0.0)

    # Check that market_value and unrealized_gain_loss are None
    for position in positions:
        assert position.current_price is None
        assert position.market_value is None
        assert position.unrealized_gain_loss is None
        assert position.allocation_percentage == 0.00
        # Realized P/L should still be available (doesn't require prices)
        assert position.realized_gain_loss is not None


def test_get_all_positions_partial_prices(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() when only some prices are available."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL has price
        assets[1]: None,  # GOOGL has no price
    }

    # Mock get_positions_with_allocations
    # AAPL market value: 17550.0, GOOGL market value: 0 (no price)
    # Total: 17550.0, so AAPL = 100%, GOOGL = 0%
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("100.00")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("0.00")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    assert len(positions) == 2

    # First position should have price data
    position1 = positions[0]
    assert position1.current_price == 175.50
    assert position1.market_value is not None
    assert position1.unrealized_gain_loss is not None
    assert position1.allocation_percentage == 100.00

    # Second position should not have price data
    position2 = positions[1]
    assert position2.current_price is None
    assert position2.market_value is None
    assert position2.unrealized_gain_loss is None
    assert position2.allocation_percentage == 0.00


def test_portfolio_all_endpoint(client_with_portfolio, test_settings):
    """Test /portfolio/all endpoint with default pagination and portfolio totals."""
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Mock fetch_price_map
    from wpm.models import Asset

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    
    # Check PortfolioAllResponse structure
    assert "positions" in data
    assert "total_market_value" in data
    assert "total_cost_basis" in data
    assert "total_unrealized_gain_loss" in data
    assert "total_realized_gain_loss" in data
    
    # Check positions (paginated)
    positions = data["positions"]
    assert "items" in positions
    assert "total" in positions
    assert "page" in positions
    assert "size" in positions
    assert "pages" in positions
    assert positions["total"] == 2
    assert positions["page"] == 1
    assert positions["size"] == 20
    assert positions["pages"] == 1
    assert len(positions["items"]) == 2
    
    # Check that allocation_percentage is present in position items
    for item in positions["items"]:
        assert "allocation_percentage" in item
        assert item["allocation_percentage"] is not None
        assert 0 <= item["allocation_percentage"] <= 100
    
    # Check totals
    assert data["total_cost_basis"] == 20000.0
    assert data["total_market_value"] == 25050.0
    assert data["total_unrealized_gain_loss"] == 5050.0
    assert data["total_realized_gain_loss"] == 300.0
    
    # Check that realized_gain_loss is present in position items
    for item in positions["items"]:
        assert "realized_gain_loss" in item
        assert item["realized_gain_loss"] is not None


def test_portfolio_all_endpoint_no_portfolio(client, test_settings):
    """Test /portfolio/all endpoint when portfolio is not available."""
    # First, get a token
    login_response = client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Access endpoint without portfolio in app state
    response = client.get(
        "/portfolio/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert "detail" in response.json()


def test_portfolio_all_endpoint_no_price_service(client, mock_composite_portfolio, test_settings):
    """Test /portfolio/all endpoint when price service is not available."""
    # First, get a token
    login_response = client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    # Set portfolio but not price_service in app state
    client.app.state.composite_portfolio = mock_composite_portfolio
    client.app.state.price_service = None

    # Access endpoint without price service in app state
    response = client.get(
        "/portfolio/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500
    assert "detail" in response.json()
    assert "Price service" in response.json()["detail"]


def test_data_transformation_decimal_to_float(mock_composite_portfolio, mock_price_service):
    """Test that Decimal quantities are correctly converted to float."""
    from wpm.models import Asset

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    # Verify quantities are floats, not Decimals
    for position in positions:
        assert isinstance(position.quantity, float)
        assert isinstance(position.average_price, float)
        assert isinstance(position.cost_basis, float)
        assert isinstance(position.allocation_percentage, float)


def test_average_price_calculation(mock_composite_portfolio, mock_price_service):
    """Test that average_price is calculated correctly."""
    from wpm.models import Asset

    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    # Check average_price calculation: cost_basis / quantity
    position1 = positions[0]
    expected_avg_price = 15000.0 / 100.0
    assert position1.average_price == expected_avg_price

    position2 = positions[1]
    expected_avg_price = 5000.0 / 50.0
    assert position2.average_price == expected_avg_price


def test_get_all_positions_sorting_service(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() service function with sorting."""
    from wpm.models import Asset

    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Test sorting by ticker descending
            positions = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="ticker", sort_order="desc"
            )

    assert len(positions) == 2
    # Should be sorted descending, so GOOGL comes first
    assert positions[0].ticker == "GOOGL"
    assert positions[1].ticker == "AAPL"


def test_get_all_positions_sorting_by_allocation_percentage(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() service function with sorting by allocation_percentage."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations
    # AAPL: 70.06%, GOOGL: 29.94%
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Test sorting by allocation_percentage ascending (smallest first)
            positions_asc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="allocation_percentage", sort_order="asc"
            )

            # Test sorting by allocation_percentage descending (largest first)
            positions_desc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="allocation_percentage", sort_order="desc"
            )

    assert len(positions_asc) == 2
    assert len(positions_desc) == 2

    # Ascending: GOOGL (29.94%) should come first, then AAPL (70.06%)
    assert positions_asc[0].ticker == "GOOGL"
    assert positions_asc[0].allocation_percentage == 29.94
    assert positions_asc[1].ticker == "AAPL"
    assert positions_asc[1].allocation_percentage == 70.06

    # Descending: AAPL (70.06%) should come first, then GOOGL (29.94%)
    assert positions_desc[0].ticker == "AAPL"
    assert positions_desc[0].allocation_percentage == 70.06
    assert positions_desc[1].ticker == "GOOGL"
    assert positions_desc[1].allocation_percentage == 29.94


def test_get_all_positions_sorting_allocation_percentage_with_none(mock_composite_portfolio, mock_price_service):
    """Test sorting by allocation_percentage when some values are None."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL has price
        assets[1]: None,  # GOOGL has no price
    }

    # Mock get_positions_with_allocations - one with allocation, one without
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("100.00")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("0.00")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Test sorting by allocation_percentage ascending (None should come first)
            positions_asc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="allocation_percentage", sort_order="asc"
            )

            # Test sorting by allocation_percentage descending (None should come last)
            positions_desc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="allocation_percentage", sort_order="desc"
            )

    assert len(positions_asc) == 2
    assert len(positions_desc) == 2

    # Ascending: 0.00 should come first, then 100.00
    assert positions_asc[0].allocation_percentage == 0.00
    assert positions_asc[1].allocation_percentage == 100.00

    # Descending: 100.00 should come first, then 0.00
    assert positions_desc[0].allocation_percentage == 100.00
    assert positions_desc[1].allocation_percentage == 0.00


def test_get_all_positions_sorting_by_realized_gain_loss(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() sorting by realized_gain_loss."""
    from wpm.models import Asset

    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl - AAPL has higher realized P/L
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Sort ascending by realized_gain_loss
            positions_asc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="realized_gain_loss", sort_order="asc"
            )
            # Sort descending by realized_gain_loss
            positions_desc = get_all_positions(
                mock_composite_portfolio, mock_price_service, sort_by="realized_gain_loss", sort_order="desc"
            )

    # Ascending: GOOGL (-200.0) should come before AAPL (500.0)
    assert positions_asc[0].ticker == "GOOGL"
    assert positions_asc[0].realized_gain_loss == -200.0
    assert positions_asc[1].ticker == "AAPL"
    assert positions_asc[1].realized_gain_loss == 500.0

    # Descending: AAPL (500.0) should come before GOOGL (-200.0)
    assert positions_desc[0].ticker == "AAPL"
    assert positions_desc[0].realized_gain_loss == 500.0
    assert positions_desc[1].ticker == "GOOGL"
    assert positions_desc[1].realized_gain_loss == -200.0


def test_get_all_positions_sorting_invalid_field(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() raises ValueError for invalid sort_by field."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            with pytest.raises(ValueError, match="Invalid sort_by field"):
                get_all_positions(
                    mock_composite_portfolio, mock_price_service, sort_by="invalid_field"
                )


def test_get_all_positions_exception_handling(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() handles exceptions when transforming positions."""
    from wpm.models import Asset

    # Mock a position that will raise an exception when accessing quantity
    bad_asset = Mock(spec=Asset)
    bad_asset.ticker = "BAD"
    bad_asset.asset_type = "Stock"

    bad_position = Mock()
    bad_position.asset = bad_asset
    # Make quantity raise an exception when accessed
    type(bad_position).quantity = PropertyMock(side_effect=ValueError("Test error"))
    bad_position.cost_basis = 1000.0
    bad_position.cost_basis_method = "fifo"

    # Add the bad position to the mock portfolio
    positions_dict = mock_composite_portfolio.get_positions()
    positions_dict[bad_asset] = bad_position

    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
        bad_asset: 100.00,
    }

    # Mock get_positions_with_allocations - include the bad position
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
        bad_asset: (bad_position, Decimal("0.00")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    # Should still return the 2 valid positions, skipping the bad one
    assert len(positions) == 2


# Pagination tests
def test_portfolio_pagination_default_page_size(client_with_portfolio, test_settings):
    """Test pagination with default page size."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/all",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    positions = data["positions"]
    assert positions["size"] == 20  # Default page size
    assert positions["page"] == 1  # Default page


def test_portfolio_pagination_custom_page_size(client_with_portfolio, test_settings):
    """Test pagination with custom page size."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all?size=1",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    positions = data["positions"]
    assert positions["size"] == 1
    assert positions["page"] == 1
    assert positions["total"] == 2
    assert positions["pages"] == 2
    assert len(positions["items"]) == 1


def test_portfolio_pagination_page_navigation(client_with_portfolio, test_settings):
    """Test pagination page navigation."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Get first page
            response1 = client_with_portfolio.get(
                "/portfolio/all?size=1&page=1",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response1.status_code == 200
            data1 = response1.json()
            positions1 = data1["positions"]
            assert positions1["page"] == 1
            assert len(positions1["items"]) == 1

            # Get second page
            response2 = client_with_portfolio.get(
                "/portfolio/all?size=1&page=2",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response2.status_code == 200
            data2 = response2.json()
            positions2 = data2["positions"]
            assert positions2["page"] == 2
            assert len(positions2["items"]) == 1

            # Verify different items on different pages
        assert positions1["items"][0]["ticker"] != positions2["items"][0]["ticker"]


def test_portfolio_pagination_page_beyond_total(client_with_portfolio, test_settings):
    """Test pagination when requesting page beyond total pages."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/all?size=1&page=10",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    positions = data["positions"]
    assert positions["page"] == 10
    assert len(positions["items"]) == 0  # Empty page


def test_portfolio_pagination_max_page_size(client_with_portfolio, test_settings):
    """Test pagination respects maximum page size limit."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Try to request more than max page size
        response = client_with_portfolio.get(
            "/portfolio/all?size=200",
            headers={"Authorization": f"Bearer {token}"},
        )

    # Should return validation error
    assert response.status_code == 422


# Sorting tests
def test_portfolio_sorting_by_ticker_asc(client_with_portfolio, test_settings):
    """Test sorting by ticker in ascending order."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all?sort_by=ticker&sort_order=asc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # Should be sorted by ticker ascending (AAPL before GOOGL)
    assert items[0]["ticker"] == "AAPL"
    assert items[1]["ticker"] == "GOOGL"


def test_portfolio_sorting_by_ticker_desc(client_with_portfolio, test_settings):
    """Test sorting by ticker in descending order."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all?sort_by=ticker&sort_order=desc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # Should be sorted by ticker descending (GOOGL before AAPL)
    assert items[0]["ticker"] == "GOOGL"
    assert items[1]["ticker"] == "AAPL"


def test_portfolio_sorting_by_quantity(client_with_portfolio, test_settings):
    """Test sorting by quantity."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all?sort_by=quantity&sort_order=asc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # AAPL has 100.0, GOOGL has 50.0, so GOOGL should come first in ascending order
    assert items[0]["quantity"] == 50.0
    assert items[1]["quantity"] == 100.0


def test_portfolio_sorting_by_cost_basis(client_with_portfolio, test_settings):
    """Test sorting by cost_basis."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all?sort_by=cost_basis&sort_order=asc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # GOOGL has 5000.0, AAPL has 15000.0, so GOOGL should come first
    assert items[0]["cost_basis"] == 5000.0
    assert items[1]["cost_basis"] == 15000.0


def test_portfolio_sorting_by_allocation_percentage(client_with_portfolio, test_settings):
    """Test sorting by allocation_percentage."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    # AAPL: 70.06%, GOOGL: 29.94%
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Test ascending
            response_asc = client_with_portfolio.get(
                "/portfolio/all?sort_by=allocation_percentage&sort_order=asc",
                headers={"Authorization": f"Bearer {token}"},
            )

            # Test descending
            response_desc = client_with_portfolio.get(
                "/portfolio/all?sort_by=allocation_percentage&sort_order=desc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response_asc.status_code == 200
    assert response_desc.status_code == 200

    # Ascending: GOOGL (29.94%) should come first
    data_asc = response_asc.json()
    items_asc = data_asc["positions"]["items"]
    assert items_asc[0]["ticker"] == "GOOGL"
    assert items_asc[0]["allocation_percentage"] == 29.94
    assert items_asc[1]["ticker"] == "AAPL"
    assert items_asc[1]["allocation_percentage"] == 70.06

    # Descending: AAPL (70.06%) should come first
    data_desc = response_desc.json()
    items_desc = data_desc["positions"]["items"]
    assert items_desc[0]["ticker"] == "AAPL"
    assert items_desc[0]["allocation_percentage"] == 70.06
    assert items_desc[1]["ticker"] == "GOOGL"
    assert items_desc[1]["allocation_percentage"] == 29.94


def test_portfolio_sorting_default_ticker_asc(client_with_portfolio, test_settings):
    """Test default sorting (ticker ascending)."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # Default should be ticker ascending
    assert items[0]["ticker"] == "AAPL"
    assert items[1]["ticker"] == "GOOGL"


def test_portfolio_sorting_invalid_field(client_with_portfolio, test_settings):
    """Test sorting with invalid sort_by field."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/all?sort_by=invalid_field",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 400
    assert "Invalid sort_by field" in response.json()["detail"]


def test_portfolio_sorting_all_fields(client_with_portfolio, test_settings):
    """Test that all Position fields are sortable."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    valid_fields = [
        "ticker",
        "asset_type",
        "quantity",
        "average_price",
        "cost_basis",
        "cost_basis_method",
        "current_price",
        "market_value",
        "unrealized_gain_loss",
        "allocation_percentage",
    ]

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            for field in valid_fields:
                response = client_with_portfolio.get(
                    f"/portfolio/all?sort_by={field}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response.status_code == 200, f"Field {field} should be sortable"


def test_portfolio_sorting_with_none_values(client_with_portfolio, test_settings):
    """Test sorting handles None values correctly."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    # Set one price to None to test None handling
    mock_price_map = {
        assets[0]: None,  # AAPL has no price
        assets[1]: 150.00,  # GOOGL has price
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 15000.0  # Only GOOGL has price
    portfolio.get_total_unrealized_pnl = lambda prices: -5000.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("0.00")),  # AAPL has no price
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("100.00")),  # GOOGL has price
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Sort by current_price ascending - None should come first
            response = client_with_portfolio.get(
                "/portfolio/all?sort_by=current_price&sort_order=asc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    items = data["positions"]["items"]
    # None value should come first in ascending order
    assert items[0]["current_price"] is None
    assert items[1]["current_price"] == 150.00


# Combined pagination and sorting tests
def test_portfolio_pagination_and_sorting(client_with_portfolio, test_settings):
    """Test combined pagination and sorting."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Get first page, sorted by ticker descending
            response = client_with_portfolio.get(
                "/portfolio/all?page=1&size=1&sort_by=ticker&sort_order=desc",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    positions = data["positions"]
    assert positions["page"] == 1
    assert positions["size"] == 1
    assert len(positions["items"]) == 1
    # Should be sorted descending, so GOOGL should be first
    assert positions["items"][0]["ticker"] == "GOOGL"


# Portfolio totals tests
def test_portfolio_all_endpoint_with_totals(client_with_portfolio, test_settings):
    """Test /portfolio/all endpoint returns portfolio totals."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0
    portfolio.get_asset_realized_pnl = lambda ticker: {
        assets[0].ticker: 500.0,
        assets[1].ticker: -200.0,
    }.get(ticker, 0.0)

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "positions" in data
    assert "total_market_value" in data
    assert "total_cost_basis" in data
    assert "total_unrealized_gain_loss" in data
    assert "total_realized_gain_loss" in data
    
    # Verify totals match mocked values
    assert data["total_cost_basis"] == 20000.0
    assert data["total_market_value"] == 25050.0
    assert data["total_unrealized_gain_loss"] == 5050.0
    assert data["total_realized_gain_loss"] == 300.0


def test_portfolio_all_endpoint_totals_with_none_values(client_with_portfolio, test_settings):
    """Test /portfolio/all endpoint handles None values in totals."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: None,  # No prices available
        assets[1]: None,
    }

    # Mock portfolio totals methods - market value and P&L return None
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: None
    portfolio.get_total_unrealized_pnl = lambda prices: None
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations - when no prices, allocations are 0.00
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("0.00")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("0.00")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            response = client_with_portfolio.get(
                "/portfolio/all",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    
    # Verify cost basis is always available
    assert data["total_cost_basis"] == 20000.0
    
    # Verify optional fields can be None
    assert data["total_market_value"] is None
    assert data["total_unrealized_gain_loss"] is None


def test_portfolio_totals_pagination_independence(client_with_portfolio, test_settings):
    """Test that portfolio totals are independent of pagination parameters."""
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]

    assets = list(client_with_portfolio.app.state.composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Mock portfolio totals methods
    portfolio = client_with_portfolio.app.state.composite_portfolio
    portfolio.get_total_cost_basis = lambda: 20000.0
    portfolio.get_total_market_value = lambda prices: 25050.0
    portfolio.get_total_unrealized_pnl = lambda prices: 5050.0
    portfolio.get_total_realized_pnl = lambda: 300.0

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch("wpm_backend.services.portfolio_service.get_positions_with_allocations", return_value=positions_with_allocations):
            # Test with different pagination parameters
            response1 = client_with_portfolio.get(
                "/portfolio/all?page=1&size=1",
                headers={"Authorization": f"Bearer {token}"},
            )
            response2 = client_with_portfolio.get(
                "/portfolio/all?page=2&size=1",
                headers={"Authorization": f"Bearer {token}"},
            )
            response3 = client_with_portfolio.get(
                "/portfolio/all?page=1&size=100",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response1.status_code == 200
    assert response2.status_code == 200
    assert response3.status_code == 200
    
    data1 = response1.json()
    data2 = response2.json()
    data3 = response3.json()
    
    # Totals should be the same regardless of pagination
    assert data1["total_cost_basis"] == data2["total_cost_basis"] == data3["total_cost_basis"] == 20000.0
    assert data1["total_market_value"] == data2["total_market_value"] == data3["total_market_value"] == 25050.0
    assert data1["total_unrealized_gain_loss"] == data2["total_unrealized_gain_loss"] == data3["total_unrealized_gain_loss"] == 5050.0
    
    # But positions should differ
    assert len(data1["positions"]["items"]) == 1
    assert len(data2["positions"]["items"]) == 1
    assert len(data3["positions"]["items"]) == 2

