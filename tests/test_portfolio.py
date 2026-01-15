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

    # Check that market_value and unrealized_gain_loss are None
    for position in positions:
        assert position.current_price is None
        assert position.market_value is None
        assert position.unrealized_gain_loss is None
        assert position.allocation_percentage == 0.00


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
    
    # Verify totals match mocked values
    assert data["total_cost_basis"] == 20000.0
    assert data["total_market_value"] == 25050.0
    assert data["total_unrealized_gain_loss"] == 5050.0


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


# Tests for /portfolio/lots/<ticker> endpoint
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

    mock_composite_portfolio.get_asset_lots.return_value = [lot1, lot2, lot3]

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
    portfolio.get_asset_lots.return_value = [lot1, lot2]

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
        ),
        PortfolioHistoryPoint(
            date=date(2024, 1, 16),
            total_market_value=25500.0,
            asset_positions={"AAPL": 18000.0, "GOOGL": 7500.0},
            prices={"AAPL": 180.00, "GOOGL": 150.00},
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
    
    # Check second history point
    hp2 = history_points[1]
    assert hp2.date == "2024-01-16"
    assert hp2.total_market_value == 25500.0
    assert hp2.asset_positions == {"AAPL": 18000.0, "GOOGL": 7500.0}
    assert hp2.prices == {"AAPL": 180.00, "GOOGL": 150.00}


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
        ),
        "2024-01-16": PortfolioHistoryPoint(
            date="2024-01-16",
            total_market_value=25500.0,
            asset_positions={"AAPL": 18000.0, "GOOGL": 7500.0},
            prices={"AAPL": 180.00, "GOOGL": 150.00},
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


def test_portfolio_response_total_count():
    """Test PortfolioResponse.total_count computed field (deprecated model)."""
    from wpm_backend.models.portfolio import PortfolioResponse, Position
    
    # Create a PortfolioResponse with positions
    positions = [
        Position(
            ticker="AAPL",
            asset_type="Stock",
            quantity=100.0,
            average_price=150.0,
            cost_basis=15000.0,
            cost_basis_method="fifo",
        ),
        Position(
            ticker="GOOGL",
            asset_type="Stock",
            quantity=50.0,
            average_price=100.0,
            cost_basis=5000.0,
            cost_basis_method="average",
        ),
    ]
    
    portfolio_response = PortfolioResponse(positions=positions)
    assert portfolio_response.total_count == 2
    
    # Test with empty positions
    empty_response = PortfolioResponse(positions=[])
    assert empty_response.total_count == 0


def test_parse_date_to_iso_string_custom_objects():
    """Test parse_date_to_iso_string helper function with custom date-like objects."""
    from datetime import date
    from wpm_backend.services.portfolio_utils import parse_date_to_iso_string
    
    # Test with ISO string (validates and returns - covers line 95-96)
    assert parse_date_to_iso_string("2024-01-15") == "2024-01-15"
    
    # Test with custom date-like object with isoformat method (covers hasattr path)
    class CustomDateWithIsoformat:
        def isoformat(self):
            return "2024-01-15"
    
    custom_date = CustomDateWithIsoformat()
    assert parse_date_to_iso_string(custom_date) == "2024-01-15"
    
    # Test with custom date-like object with date method (covers hasattr date path)
    class CustomDateWithDate:
        def date(self):
            return date(2024, 1, 15)
    
    custom_date2 = CustomDateWithDate()
    assert parse_date_to_iso_string(custom_date2) == "2024-01-15"
    
    # Test with custom object (last resort - converts to string, covers line 111)
    class CustomDateStr:
        def __str__(self):
            return "2024-01-15"
    
    custom_date3 = CustomDateStr()
    assert parse_date_to_iso_string(custom_date3) == "2024-01-15"


def test_apply_granularity_filter_daily():
    """Test apply_granularity_filter with daily granularity (returns all points)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for a week
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    # Apply daily granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        start_date + timedelta(days=6),
        "daily",
    )
    
    # Should return all points
    assert len(filtered) == 7
    assert filtered == history_points


def test_apply_granularity_filter_weekly_monday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is Monday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for 3 weeks (21 days)
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Sunday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (Mondays of weeks 1, 2, 3)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-15"  # Monday, week 1
    assert filtered[1].date == "2024-01-22"  # Monday, week 2
    assert filtered[2].date == "2024-01-29"  # Monday, week 3


def test_apply_granularity_filter_weekly_non_monday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is not Monday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on Wednesday
    start_date = date(2024, 1, 17)  # Wednesday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Tuesday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (next Monday after start, then subsequent Mondays)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-22"  # Monday after start (Wed)
    assert filtered[1].date == "2024-01-29"  # Monday, week 2
    assert filtered[2].date == "2024-02-05"  # Monday, week 3


def test_apply_granularity_filter_weekly_sunday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is Sunday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on Sunday (next Monday is 1 day away)
    start_date = date(2024, 1, 14)  # Sunday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Saturday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (next Monday after Sunday, then subsequent Mondays)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-15"  # Monday (1 day after Sunday)
    assert filtered[1].date == "2024-01-22"  # Monday, week 2
    assert filtered[2].date == "2024-01-29"  # Monday, week 3


def test_apply_granularity_filter_monthly_first_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is first of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on first of month
    start_date = date(2024, 1, 1)
    history_points = []
    # Create points for 3 months (90 days)
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 3, 31)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Jan 1, Feb 1, Mar 1)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-01"
    assert filtered[1].date == "2024-02-01"
    assert filtered[2].date == "2024-03-01"


def test_apply_granularity_filter_monthly_non_first_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is not first of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start in middle of month
    start_date = date(2024, 1, 15)
    history_points = []
    # Create points for 3 months (90 days)
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 4, 15)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Feb 1, Mar 1, Apr 1 - skipping Jan since we start on 15th)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-02-01"  # First of month after start
    assert filtered[1].date == "2024-03-01"
    assert filtered[2].date == "2024-04-01"


def test_apply_granularity_filter_monthly_last_day_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is last day of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on last day of month
    start_date = date(2024, 1, 31)
    history_points = []
    # Create points for 3 months
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 4, 30)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Feb 1, Mar 1, Apr 1)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-02-01"  # First of next month
    assert filtered[1].date == "2024-03-01"
    assert filtered[2].date == "2024-04-01"


def test_apply_granularity_filter_invalid_granularity():
    """Test apply_granularity_filter with invalid granularity value."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    history_points = [
        PortfolioHistoryPoint(
            date="2024-01-15",
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    ]
    
    # Test with invalid granularity
    with pytest.raises(ValueError, match="Invalid granularity"):
        apply_granularity_filter(
            history_points,
            date(2024, 1, 15),
            date(2024, 1, 15),
            "invalid",
        )


def test_portfolio_performance_endpoint_with_granularity_daily(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with daily granularity (default)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 7 days
    cache_end_date = date(2024, 1, 21)
    performance_cache = {}
    for i in range(7):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with daily granularity (default)
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-21&granularity=daily",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return all 7 points
    assert len(data["history_points"]) == 7


def test_portfolio_performance_endpoint_with_granularity_weekly(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with weekly granularity."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)  # Monday
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 21 days (3 weeks)
    cache_end_date = date(2024, 2, 4)  # Sunday, 3rd week
    performance_cache = {}
    for i in range(21):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with weekly granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-02-04&granularity=weekly",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return 3 points (Mondays)
    assert len(data["history_points"]) == 3
    assert data["history_points"][0]["date"] == "2024-01-15"  # Monday, week 1
    assert data["history_points"][1]["date"] == "2024-01-22"  # Monday, week 2
    assert data["history_points"][2]["date"] == "2024-01-29"  # Monday, week 3


def test_portfolio_performance_endpoint_with_granularity_monthly(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with monthly granularity."""
    from datetime import date, timedelta
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
    
    # Set up performance cache with 90 days (3 months)
    cache_end_date = date(2024, 3, 31)
    performance_cache = {}
    for i in range(90):
        current_date = date(2024, 1, 1) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with monthly granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-03-31&granularity=monthly",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return 3 points (first of each month)
    assert len(data["history_points"]) == 3
    assert data["history_points"][0]["date"] == "2024-01-01"
    assert data["history_points"][1]["date"] == "2024-02-01"
    assert data["history_points"][2]["date"] == "2024-03-01"


def test_portfolio_performance_endpoint_invalid_granularity(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with invalid granularity value."""
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
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache
    cache_end_date = date(2024, 1, 16)
    performance_cache = {
        "2024-01-15": PortfolioHistoryPoint(
            date="2024-01-15",
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    }
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with invalid granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-16&granularity=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    # Should return 422 (FastAPI validation error)
    assert response.status_code == 422


def test_apply_granularity_filter_maintains_chronological_order():
    """Test that apply_granularity_filter maintains chronological order."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for a week
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=6)
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Verify chronological order
    assert len(filtered) >= 1
    for i in range(len(filtered) - 1):
        assert filtered[i].date < filtered[i + 1].date


def test_apply_granularity_filter_with_missing_dates():
    """Test apply_granularity_filter when some expected dates are missing from history points."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points but skip some Mondays (simulating missing cache entries)
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    # Only include some dates, not all Mondays
    dates_to_include = [
        date(2024, 1, 15),  # Monday, week 1
        date(2024, 1, 16),  # Tuesday (not Monday)
        date(2024, 1, 17),  # Wednesday (not Monday)
        # Skip Monday week 2
        date(2024, 1, 29),  # Monday, week 3
    ]
    
    for current_date in dates_to_include:
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0,
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 1, 29)
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should only return the Mondays that exist in history_points
    assert len(filtered) == 2
    assert filtered[0].date == "2024-01-15"
    assert filtered[1].date == "2024-01-29"


def test_apply_granularity_filter_single_day_range():
    """Test apply_granularity_filter with single day range."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Single day
    start_date = date(2024, 1, 15)  # Monday
    history_points = [
        PortfolioHistoryPoint(
            date=start_date.isoformat(),
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    ]
    
    # Daily granularity should return the single point
    filtered_daily = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "daily",
    )
    assert len(filtered_daily) == 1
    
    # Weekly granularity should return the point if it's a Monday
    filtered_weekly = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "weekly",
    )
    assert len(filtered_weekly) == 1  # Monday is included
    
    # Monthly granularity - Jan 15 is not first of month, so should be empty
    filtered_monthly = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "monthly",
    )
    assert len(filtered_monthly) == 0  # Jan 15 is not first of month


def test_portfolio_performance_endpoint_default_granularity(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with default granularity (daily)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 7 days
    cache_end_date = date(2024, 1, 21)
    performance_cache = {}
    for i in range(7):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint without granularity parameter (should default to daily)
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-21",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return all 7 points (daily is default)
    assert len(data["history_points"]) == 7


# Asset Metadata Service Function Tests

def test_get_asset_metadata_service_success(mock_composite_portfolio, mock_asset_service):
    """Test get_asset_metadata() service function with successful metadata retrieval."""
    from wpm_backend.services.portfolio_service import get_asset_metadata
    from wpm.models import Asset

    # Setup mock portfolio to return asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup mock asset service to return metadata
    mock_metadata = {
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "country": "United States",
        "market_cap": 3000000000000.0,
        "category": "Stock",
    }
    mock_asset_service.get_metadata.return_value = mock_metadata

    # Call service function
    result = get_asset_metadata(mock_composite_portfolio, "AAPL", mock_asset_service)

    # Verify result
    assert result == mock_metadata
    mock_composite_portfolio.get_assets.assert_called_once()
    mock_asset_service.get_metadata.assert_called_once_with("AAPL", "Stock")


def test_get_asset_metadata_service_failed_retrieval(mock_composite_portfolio, mock_asset_service):
    """Test get_asset_metadata() service function when metadata retrieval fails."""
    from wpm_backend.services.portfolio_service import get_asset_metadata
    from wpm.models import Asset

    # Setup mock portfolio to return asset
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    mock_composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup mock asset service to return None (retrieval failed)
    mock_asset_service.get_metadata.return_value = None

    # Call service function
    result = get_asset_metadata(mock_composite_portfolio, "AAPL", mock_asset_service)

    # Verify result is None
    assert result is None
    mock_asset_service.get_metadata.assert_called_once_with("AAPL", "Stock")


def test_get_asset_metadata_service_ticker_not_found(mock_composite_portfolio, mock_asset_service):
    """Test get_asset_metadata() service function when ticker is not in portfolio."""
    from wpm_backend.services.portfolio_service import get_asset_metadata

    # Setup mock portfolio to return empty assets
    mock_composite_portfolio.get_assets.return_value = {}

    # Call service function and expect ValueError
    with pytest.raises(ValueError, match="Ticker INVALID not found in portfolio"):
        get_asset_metadata(mock_composite_portfolio, "INVALID", mock_asset_service)

    # Verify asset service was not called
    mock_asset_service.get_metadata.assert_not_called()


def test_get_all_asset_metadata_service_success(mock_composite_portfolio, mock_asset_service):
    """Test get_all_asset_metadata() service function with successful metadata retrieval."""
    from wpm_backend.services.portfolio_service import get_all_asset_metadata
    from wpm.models import Asset

    # Setup mock portfolio to return multiple assets with different asset types
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    asset3 = Mock(spec=Asset)
    asset3.ticker = "BTC"
    asset3.asset_type = "Crypto"

    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
        "BTC": asset3,
    }

    # Setup mock asset service to return metadata for each batch
    mock_asset_service.get_metadata_batch.side_effect = [
        {
            "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
            "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
        },
        {
            "BTC": {"name": "Bitcoin", "category": "Cryptocurrency"},
        },
    ]

    # Call service function
    result = get_all_asset_metadata(mock_composite_portfolio, mock_asset_service)

    # Verify result
    assert len(result) == 3
    assert result["AAPL"] == {"name": "Apple Inc.", "sector": "Technology"}
    assert result["GOOGL"] == {"name": "Alphabet Inc.", "sector": "Technology"}
    assert result["BTC"] == {"name": "Bitcoin", "category": "Cryptocurrency"}

    # Verify get_metadata_batch was called twice (once for Stock, once for Crypto)
    assert mock_asset_service.get_metadata_batch.call_count == 2
    mock_asset_service.get_metadata_batch.assert_any_call(["AAPL", "GOOGL"], "Stock")
    mock_asset_service.get_metadata_batch.assert_any_call(["BTC"], "Crypto")


def test_get_all_asset_metadata_service_partial_failure(mock_composite_portfolio, mock_asset_service):
    """Test get_all_asset_metadata() service function when some metadata retrieval fails."""
    from wpm_backend.services.portfolio_service import get_all_asset_metadata
    from wpm.models import Asset

    # Setup mock portfolio to return assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup mock asset service to return partial results (one None)
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc."},
        "GOOGL": None,  # Retrieval failed for GOOGL
    }

    # Call service function
    result = get_all_asset_metadata(mock_composite_portfolio, mock_asset_service)

    # Verify result
    assert len(result) == 2
    assert result["AAPL"] == {"name": "Apple Inc."}
    assert result["GOOGL"] is None


def test_get_all_asset_metadata_service_empty_portfolio(mock_composite_portfolio, mock_asset_service):
    """Test get_all_asset_metadata() service function with empty portfolio."""
    from wpm_backend.services.portfolio_service import get_all_asset_metadata

    # Setup mock portfolio to return empty assets
    mock_composite_portfolio.get_assets.return_value = {}

    # Call service function
    result = get_all_asset_metadata(mock_composite_portfolio, mock_asset_service)

    # Verify result is empty
    assert result == {}
    mock_asset_service.get_metadata_batch.assert_not_called()


# Asset Metadata Endpoint Integration Tests

def test_get_asset_metadata_endpoint_success(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/{ticker} endpoint with successful metadata retrieval."""
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

    # Setup mock asset service
    client_with_portfolio.app.state.asset_service = mock_asset_service
    mock_metadata = {
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    mock_asset_service.get_metadata.return_value = mock_metadata

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["metadata"] == mock_metadata


def test_get_asset_metadata_endpoint_failed_retrieval(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/{ticker} endpoint when metadata retrieval fails."""
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

    # Setup mock asset service to return None
    client_with_portfolio.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata.return_value = None

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response (should still return 200, but metadata is None)
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["metadata"] is None


def test_get_asset_metadata_endpoint_ticker_not_found(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/{ticker} endpoint when ticker is not found."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio to return empty assets
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {}
    client_with_portfolio.app.state.asset_service = mock_asset_service

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/INVALID",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_asset_metadata_endpoint_unauthorized(client_with_portfolio):
    """Test GET /asset/metadata/{ticker} endpoint without authentication."""
    # Call endpoint without token
    response = client_with_portfolio.get("/asset/metadata/AAPL")

    # Verify response
    assert response.status_code == 401


def test_get_all_asset_metadata_endpoint_success(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/all endpoint with successful metadata retrieval."""
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup mock asset service
    client_with_portfolio.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert len(data["metadata"]) == 2
    assert data["metadata"]["AAPL"] == {"name": "Apple Inc.", "sector": "Technology"}
    assert data["metadata"]["GOOGL"] == {"name": "Alphabet Inc.", "sector": "Technology"}


def test_get_all_asset_metadata_endpoint_partial_failure(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/all endpoint when some metadata retrieval fails."""
    from wpm.models import Asset

    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup mock asset service to return partial results
    client_with_portfolio.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc."},
        "GOOGL": None,  # Retrieval failed
    }

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert len(data["metadata"]) == 2
    assert data["metadata"]["AAPL"] == {"name": "Apple Inc."}
    assert data["metadata"]["GOOGL"] is None


def test_get_all_asset_metadata_endpoint_empty_portfolio(client_with_portfolio, mock_asset_service):
    """Test GET /asset/metadata/all endpoint with empty portfolio."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Setup mock portfolio to return empty assets
    client_with_portfolio.app.state.composite_portfolio.get_assets.return_value = {}
    client_with_portfolio.app.state.asset_service = mock_asset_service

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"] == {}


def test_get_all_asset_metadata_endpoint_unauthorized(client_with_portfolio):
    """Test GET /asset/metadata/all endpoint without authentication."""
    # Call endpoint without token
    response = client_with_portfolio.get("/asset/metadata/all")

    # Verify response
    assert response.status_code == 401


def test_get_asset_metadata_endpoint_missing_asset_service(client_with_portfolio):
    """Test GET /asset/metadata/{ticker} endpoint when AssetService is not available."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Remove asset_service from app state
    if hasattr(client_with_portfolio.app.state, "asset_service"):
        delattr(client_with_portfolio.app.state, "asset_service")

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/AAPL",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 500
    assert "asset service" in response.json()["detail"].lower()


def test_get_all_asset_metadata_endpoint_missing_asset_service(client_with_portfolio):
    """Test GET /asset/metadata/all endpoint when AssetService is not available."""
    # Setup authentication
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Remove asset_service from app state
    if hasattr(client_with_portfolio.app.state, "asset_service"):
        delattr(client_with_portfolio.app.state, "asset_service")

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 500
    assert "asset service" in response.json()["detail"].lower()

