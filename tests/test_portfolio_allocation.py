"""Unit and integration tests for portfolio allocation endpoint."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from wpm_backend.models.portfolio import AllocationPosition, PortfolioAllocationResponse
from wpm_backend.services.portfolio_service import get_portfolio_allocation


def test_get_portfolio_allocation_no_filters(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() service function with no filters."""
    from wpm.models import Asset

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations (no filters)
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl for each asset
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
        "GOOGL": assets[1],
    }

    # Mock metadata batch retrieval
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio, mock_price_service, mock_asset_service
            )

    assert len(positions) == 2
    assert all(isinstance(p, AllocationPosition) for p in positions)

    # Check first position (AAPL)
    position1 = positions[0]
    assert position1.ticker == "AAPL"
    assert position1.asset_type == "Stock"
    assert position1.quantity == 100.0
    assert position1.allocation_percentage == 70.06
    assert position1.metadata == {"name": "Apple Inc.", "sector": "Technology"}

    # Check second position (GOOGL)
    position2 = positions[1]
    assert position2.ticker == "GOOGL"
    assert position2.asset_type == "Stock"
    assert position2.quantity == 50.0
    assert position2.allocation_percentage == 29.94
    assert position2.metadata == {"name": "Alphabet Inc.", "sector": "Technology"}


def test_get_portfolio_allocation_filter_by_asset_types(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() service function filtering by asset types only."""
    from wpm.models import Asset

    # Create additional crypto asset
    asset3 = Mock(spec=Asset)
    asset3.ticker = "BTC-USD"
    asset3.asset_type = "Crypto"

    position3 = Mock()
    position3.asset = asset3
    position3.quantity = Decimal("1.0")
    position3.cost_basis = 50000.0
    position3.cost_basis_method = "fifo"

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    assets.append(asset3)
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
        asset3: 60000.00,  # BTC price
    }

    # Mock get_positions_with_allocations with Stock filter (should only return Stock assets)
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("70.06")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("29.94")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
        "GOOGL": assets[1],
    }

    # Mock metadata batch retrieval
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio,
                mock_price_service,
                mock_asset_service,
                asset_types=["Stock"],
            )

    assert len(positions) == 2
    assert all(p.asset_type == "Stock" for p in positions)
    # Verify allocations sum to 100% of filtered assets
    total_allocation = sum(p.allocation_percentage or 0 for p in positions)
    assert abs(total_allocation - 100.0) < 0.01


def test_get_portfolio_allocation_filter_by_tickers(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() service function filtering by tickers only."""
    from wpm.models import Asset

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
    }

    # Mock get_positions_with_allocations with ticker filter (only AAPL)
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("100.00")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
    }

    # Mock metadata batch retrieval
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio,
                mock_price_service,
                mock_asset_service,
                tickers=["AAPL"],
            )

    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].allocation_percentage == 100.00  # Only one asset, so 100%


def test_get_portfolio_allocation_filter_by_both(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() service function with both filters (OR logic)."""
    from wpm.models import Asset

    # Create crypto asset
    asset3 = Mock(spec=Asset)
    asset3.ticker = "BTC-USD"
    asset3.asset_type = "Crypto"

    position3 = Mock()
    position3.asset = asset3
    position3.quantity = Decimal("1.0")
    position3.cost_basis = 50000.0
    position3.cost_basis_method = "fifo"

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    assets.append(asset3)
    mock_price_map = {
        assets[0]: 175.50,  # AAPL price
        assets[1]: 150.00,  # GOOGL price
        asset3: 60000.00,  # BTC price
    }

    # Mock get_positions_with_allocations with OR filter (Crypto OR AAPL)
    # Should return AAPL (matches ticker) and BTC (matches asset_type)
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("22.64")),
        asset3: (position3, Decimal("77.36")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "BTC-USD": 0.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
        "BTC-USD": asset3,
    }

    # Mock metadata batch retrieval (grouped by asset_type)
    def mock_get_metadata_batch(tickers, asset_type):
        if asset_type == "Stock":
            return {"AAPL": {"name": "Apple Inc.", "sector": "Technology"}}
        elif asset_type == "Crypto":
            return {"BTC-USD": {"name": "Bitcoin", "category": "Crypto"}}
        return {}

    mock_asset_service.get_metadata_batch.side_effect = mock_get_metadata_batch

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio,
                mock_price_service,
                mock_asset_service,
                asset_types=["Crypto"],
                tickers=["AAPL"],
            )

    assert len(positions) == 2
    tickers = {p.ticker for p in positions}
    assert "AAPL" in tickers
    assert "BTC-USD" in tickers
    # Verify allocations sum to 100% of filtered assets
    total_allocation = sum(p.allocation_percentage or 0 for p in positions)
    assert abs(total_allocation - 100.0) < 0.01


def test_get_portfolio_allocation_metadata_none(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() when metadata retrieval fails."""
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

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
        "GOOGL": assets[1],
    }

    # Mock metadata batch retrieval to return None
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": None,
        "GOOGL": None,
    }

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio, mock_price_service, mock_asset_service
            )

    assert len(positions) == 2
    assert all(p.metadata is None for p in positions)


def test_get_portfolio_allocation_empty_result(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() when filter results in empty list."""
    # Mock fetch_price_map
    mock_price_map = {}

    # Mock get_positions_with_allocations to return empty dict
    positions_with_allocations = {}

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio,
                mock_price_service,
                mock_asset_service,
                tickers=["NONEXISTENT"],
            )

    assert len(positions) == 0
    # Verify metadata service was not called when there are no positions
    mock_asset_service.get_metadata_batch.assert_not_called()


def test_get_portfolio_allocation_metadata_batch_grouping(mock_composite_portfolio, mock_price_service, mock_asset_service):
    """Test get_portfolio_allocation() groups tickers by asset_type for metadata batch retrieval."""
    from wpm.models import Asset

    # Create assets with different asset types
    asset3 = Mock(spec=Asset)
    asset3.ticker = "BTC-USD"
    asset3.asset_type = "Crypto"

    position3 = Mock()
    position3.asset = asset3
    position3.quantity = Decimal("1.0")
    position3.cost_basis = 50000.0
    position3.cost_basis_method = "fifo"

    # Mock fetch_price_map
    assets = list(mock_composite_portfolio.get_positions().keys())
    assets.append(asset3)
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
        asset3: 60000.00,
    }

    # Mock get_positions_with_allocations
    positions_with_allocations = {
        assets[0]: (mock_composite_portfolio.get_positions()[assets[0]], Decimal("22.64")),
        assets[1]: (mock_composite_portfolio.get_positions()[assets[1]], Decimal("9.64")),
        asset3: (position3, Decimal("67.72")),
    }

    # Mock get_asset_realized_pnl
    mock_composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
        "BTC-USD": 0.0,
    }.get(ticker, 0.0)

    # Mock get_assets for metadata retrieval
    mock_composite_portfolio.get_assets.return_value = {
        "AAPL": assets[0],
        "GOOGL": assets[1],
        "BTC-USD": asset3,
    }

    # Track calls to get_metadata_batch to verify grouping
    metadata_calls = []

    def mock_get_metadata_batch(tickers, asset_type):
        metadata_calls.append((tickers, asset_type))
        if asset_type == "Stock":
            return {
                "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
                "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
            }
        elif asset_type == "Crypto":
            return {"BTC-USD": {"name": "Bitcoin", "category": "Crypto"}}
        return {}

    mock_asset_service.get_metadata_batch.side_effect = mock_get_metadata_batch

    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            positions = get_portfolio_allocation(
                mock_composite_portfolio, mock_price_service, mock_asset_service
            )

    assert len(positions) == 3
    # Verify get_metadata_batch was called separately for each asset_type
    assert len(metadata_calls) == 2
    # Verify Stock assets were grouped together
    stock_call = next((call for call in metadata_calls if call[1] == "Stock"), None)
    assert stock_call is not None
    assert set(stock_call[0]) == {"AAPL", "GOOGL"}
    # Verify Crypto assets were grouped separately
    crypto_call = next((call for call in metadata_calls if call[1] == "Crypto"), None)
    assert crypto_call is not None
    assert crypto_call[0] == ["BTC-USD"]


def test_portfolio_allocation_endpoint_no_filters(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint with no filters."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Setup positions with allocations
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("70.06")),
        assets[1]: (positions[assets[1]], Decimal("29.94")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Setup asset service
    client.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call allocation endpoint
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    assert isinstance(data["assets"], list)
    # Verify all assets have metadata field (may be None)
    for asset in data["assets"]:
        assert "metadata" in asset
        assert "ticker" in asset
        assert "allocation_percentage" in asset


def test_portfolio_allocation_endpoint_asset_types_filter(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint filtering by asset_types."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Setup positions with allocations (filtered to Stock only)
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("70.06")),
        assets[1]: (positions[assets[1]], Decimal("29.94")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Setup asset service
    client.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call allocation endpoint with asset_types filter
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation?asset_types=Stock",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    # Verify all returned assets are Stock type
    for asset in data["assets"]:
        assert asset["asset_type"] == "Stock"


def test_portfolio_allocation_endpoint_tickers_filter(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint filtering by tickers."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Setup positions with allocations (filtered to specified tickers)
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("70.06")),
        assets[1]: (positions[assets[1]], Decimal("29.94")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Setup asset service
    client.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call allocation endpoint with tickers filter
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation?tickers=AAPL,GOOGL",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    # Verify all returned assets match the tickers filter
    tickers = {asset["ticker"] for asset in data["assets"]}
    assert tickers.issubset({"AAPL", "GOOGL"})


def test_portfolio_allocation_endpoint_both_filters(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint with both filters (OR logic)."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset3 = Mock(spec=Asset)
    asset3.ticker = "BTC-USD"
    asset3.asset_type = "Crypto"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "BTC-USD": asset3,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        asset3: 60000.00,
    }

    # Setup positions with allocations (OR filter: Crypto OR AAPL)
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("22.64")),
        asset3: (Mock(quantity=Decimal("1.0"), cost_basis=50000.0, cost_basis_method="fifo"), Decimal("77.36")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "BTC-USD": 0.0,
    }.get(ticker, 0.0)

    # Setup asset service with grouped metadata
    client.app.state.asset_service = mock_asset_service
    def mock_get_metadata_batch(tickers, asset_type):
        if asset_type == "Stock":
            return {"AAPL": {"name": "Apple Inc.", "sector": "Technology"}}
        elif asset_type == "Crypto":
            return {"BTC-USD": {"name": "Bitcoin", "category": "Crypto"}}
        return {}

    mock_asset_service.get_metadata_batch.side_effect = mock_get_metadata_batch

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call allocation endpoint with both filters (OR logic)
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation?asset_types=Crypto&tickers=AAPL",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "assets" in data
    # Verify assets match either Crypto type OR AAPL ticker
    for asset in data["assets"]:
        assert asset["asset_type"] == "Crypto" or asset["ticker"] == "AAPL"


def test_portfolio_allocation_endpoint_comma_separated_parsing(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint parses comma-separated parameters correctly."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Setup positions with allocations
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("70.06")),
        assets[1]: (positions[assets[1]], Decimal("29.94")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Setup asset service
    client.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call allocation endpoint with multiple comma-separated values
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation?asset_types=Stock,ETF&tickers=AAPL,GOOGL,MSFT",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert response.status_code == 200
    data = response.json()
    assert "assets" in data


def test_portfolio_allocation_endpoint_authentication(client_with_portfolio):
    """Test /portfolio/allocation endpoint requires authentication."""
    from fastapi.testclient import TestClient

    client: TestClient = client_with_portfolio

    # Call allocation endpoint without token
    response = client.get("/portfolio/allocation")

    assert response.status_code == 401


def test_portfolio_allocation_endpoint_error_handling(client_with_portfolio, test_settings, mock_asset_service):
    """Test /portfolio/allocation endpoint error handling."""
    from decimal import Decimal
    from unittest.mock import patch
    from wpm.models import Asset

    client = client_with_portfolio

    # Setup mock portfolio assets
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    positions = client.app.state.composite_portfolio.get_positions()
    assets = list(positions.keys())

    # Setup get_assets for metadata retrieval
    client.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup price map
    mock_price_map = {
        assets[0]: 175.50,
        assets[1]: 150.00,
    }

    # Setup positions with allocations
    positions_with_allocations = {
        assets[0]: (positions[assets[0]], Decimal("70.06")),
        assets[1]: (positions[assets[1]], Decimal("29.94")),
    }

    # Setup get_asset_realized_pnl
    client.app.state.composite_portfolio.get_asset_realized_pnl = lambda ticker: {
        "AAPL": 500.0,
        "GOOGL": -200.0,
    }.get(ticker, 0.0)

    # Setup asset service
    client.app.state.asset_service = mock_asset_service
    mock_asset_service.get_metadata_batch.return_value = {
        "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
        "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    }

    # Login first
    login_response = client.post(
        "/login", json={"username": test_settings.username, "password": test_settings.password}
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Call with empty filters (should still work, returns all)
    with patch("wpm_backend.services.portfolio_service.fetch_price_map", return_value=mock_price_map):
        with patch(
            "wpm_backend.services.portfolio_service.get_positions_with_allocations",
            return_value=positions_with_allocations,
        ):
            response = client.get(
                "/portfolio/allocation?asset_types=&tickers=",
                headers={"Authorization": f"Bearer {token}"},
            )

    # Should return 200 with all assets (empty filters are treated as None)
    assert response.status_code == 200
