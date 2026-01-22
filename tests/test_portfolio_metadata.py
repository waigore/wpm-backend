"""Unit and integration tests for portfolio metadata endpoints."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import get_all_asset_metadata, get_all_positions, get_asset_metadata, get_portfolio_performance


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
    asset_service = getattr(client_with_portfolio.app.state, "asset_service", None)
    if asset_service is not None:
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
    asset_service = getattr(client_with_portfolio.app.state, "asset_service", None)
    if asset_service is not None:
        delattr(client_with_portfolio.app.state, "asset_service")

    # Call endpoint
    response = client_with_portfolio.get(
        "/asset/metadata/all",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Verify response
    assert response.status_code == 500
    assert "asset service" in response.json()["detail"].lower()


