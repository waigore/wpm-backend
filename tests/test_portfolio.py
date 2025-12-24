"""Unit and integration tests for portfolio endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import Position
from wpm_backend.services.portfolio_service import get_all_positions


def test_get_all_positions_service(mock_composite_portfolio, mock_price_service):
    """Test get_all_positions() service function."""
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

    # Check first position (AAPL)
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
    """Test /portfolio/all endpoint."""
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

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        response = client_with_portfolio.get(
            "/portfolio/all",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "positions" in data
    assert "total_count" in data
    assert data["total_count"] == len(data["positions"])
    assert len(data["positions"]) == 2


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

