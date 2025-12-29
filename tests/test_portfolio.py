"""Unit and integration tests for portfolio endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import Position
from wpm_backend.services.portfolio_service import get_all_positions


def test_get_all_positions_service(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() service function with default sorting."""
    from wpm.models import Asset

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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


def test_get_all_positions_without_prices(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() when prices are not available."""
    # Mock fetch_price_map to return None for all assets
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: None,
        assets[1]: None,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    assert len(positions) == 2

    # Check that market_value and unrealized_gain_loss are None
    for position in positions:
        assert position.current_price is None
        assert position.market_value is None
        assert position.unrealized_gain_loss is None


def test_get_all_positions_partial_prices(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() when only some prices are available."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL has price
        assets[1]: None,  # GOOGL has no price
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    assert len(positions) == 2

    # First position should have price data
    position1 = positions[0]
    assert position1.current_price == 175.50
    assert position1.market_value is not None
    assert position1.unrealized_gain_loss is not None

    # Second position should not have price data
    position2 = positions[1]
    assert position2.current_price is None
    assert position2.market_value is None
    assert position2.unrealized_gain_loss is None


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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        positions = get_all_positions(mock_composite_portfolio, mock_price_service)

    # Verify quantities are floats, not Decimals
    for position in positions:
        assert isinstance(position.quantity, float)
        assert isinstance(position.average_price, float)
        assert isinstance(position.cost_basis, float)


def test_average_price_calculation(mock_composite_portfolio, mock_price_service):
    """Test that average_price is calculated correctly."""
    from wpm.models import Asset

    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        # Test sorting by ticker descending
        positions = get_all_positions(
            mock_composite_portfolio, mock_price_service, sort_by="ticker", sort_order="desc"
        )

    assert len(positions) == 2
    # Should be sorted descending, so GOOGL comes first
    assert positions[0].ticker == "GOOGL"
    assert positions[1].ticker == "AAPL"


def test_get_all_positions_sorting_invalid_field(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() raises ValueError for invalid sort_by field."""
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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
    ]

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
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

