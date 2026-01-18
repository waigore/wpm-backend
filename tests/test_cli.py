"""Unit and integration tests for CLI commands."""

from io import StringIO
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from wpm_backend.cli import InteractiveCLI
from wpm_backend.main import create_app


@pytest.fixture
def cli_instance(client_with_portfolio, mock_asset_service):
    """Create InteractiveCLI instance with mocked app state."""
    app = client_with_portfolio.app
    app.state.asset_service = mock_asset_service
    return InteractiveCLI(client_with_portfolio, app)


def test_metadata_command_single_ticker_success(cli_instance, mock_asset_service):
    """Test metadata_command() with single ticker (success case)."""
    from wpm.models import Asset

    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    cli_instance.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup mock asset service
    mock_metadata = {
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }
    mock_asset_service.get_metadata.return_value = mock_metadata

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["AAPL"])
        output = fake_out.getvalue()

    # Verify output contains metadata
    assert "METADATA for AAPL" in output
    assert "Apple Inc." in output
    assert "Technology" in output


def test_metadata_command_multiple_tickers_success(cli_instance, mock_asset_service):
    """Test metadata_command() with multiple tickers (success case)."""
    from wpm.models import Asset

    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset1 = Mock(spec=Asset)
    asset1.ticker = "AAPL"
    asset1.asset_type = "Stock"

    asset2 = Mock(spec=Asset)
    asset2.ticker = "GOOGL"
    asset2.asset_type = "Stock"

    cli_instance.app.state.composite_portfolio.get_assets.return_value = {
        "AAPL": asset1,
        "GOOGL": asset2,
    }

    # Setup mock asset service
    mock_asset_service.get_metadata.side_effect = [
        {"name": "Apple Inc.", "sector": "Technology"},
        {"name": "Alphabet Inc.", "sector": "Technology"},
    ]

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["AAPL", "GOOGL"])
        output = fake_out.getvalue()

    # Verify output contains metadata for both tickers
    assert "METADATA for AAPL" in output
    assert "Apple Inc." in output
    assert "METADATA for GOOGL" in output
    assert "Alphabet Inc." in output


def test_metadata_command_ticker_not_found(cli_instance):
    """Test metadata_command() when ticker is not found (404 error)."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Setup mock portfolio to return empty assets
    cli_instance.app.state.composite_portfolio.get_assets.return_value = {}

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["INVALID"])
        output = fake_out.getvalue()

    # Verify error message
    assert "Error" in output
    assert "INVALID" in output
    assert "not found" in output.lower()


def test_metadata_command_authentication_error(cli_instance):
    """Test metadata_command() with authentication error (401)."""
    # Don't set token (not logged in)
    cli_instance.token = None

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["AAPL"])
        output = fake_out.getvalue()

    # Verify error message
    assert "Error" in output
    assert "Not logged in" in output
    assert "login" in output.lower()


def test_metadata_command_no_tickers(cli_instance):
    """Test metadata_command() with no tickers provided."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command([])
        output = fake_out.getvalue()

    # Verify error message
    assert "Error" in output
    assert "At least one ticker is required" in output


def test_metadata_command_partial_failure(cli_instance, mock_asset_service):
    """Test metadata_command() when some tickers fail."""
    from wpm.models import Asset

    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Setup mock portfolio - only AAPL exists
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    cli_instance.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Setup mock asset service
    mock_metadata = {"name": "Apple Inc."}
    mock_asset_service.get_metadata.return_value = mock_metadata

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["AAPL", "INVALID"])
        output = fake_out.getvalue()

    # Verify both results are shown (success and error)
    assert "METADATA for AAPL" in output
    assert "Apple Inc." in output
    assert "INVALID" in output
    assert "not found" in output.lower()


def test_metadata_command_server_error(cli_instance, mock_asset_service):
    """Test metadata_command() with server error (500)."""
    from wpm.models import Asset

    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Setup mock portfolio
    asset = Mock(spec=Asset)
    asset.ticker = "AAPL"
    asset.asset_type = "Stock"
    cli_instance.app.state.composite_portfolio.get_assets.return_value = {"AAPL": asset}

    # Make the endpoint return 500 by removing asset_service
    delattr(cli_instance.app.state, "asset_service")

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.metadata_command(["AAPL"])
        output = fake_out.getvalue()

    # Verify error message
    assert "Error" in output
    assert "Server error" in output or "asset service" in output.lower()


def test_help_includes_metadata_command(cli_instance):
    """Test that help command includes metadata command."""
    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.show_help()
        output = fake_out.getvalue()

    # Verify metadata command is in help
    assert "metadata" in output.lower()
    assert "ticker" in output.lower()


def test_lots_command_without_brokers(cli_instance):
    """Test lots_command() without brokers parameter."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response
    mock_response = {
        "lots": {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 10,
            "pages": 0,
        },
        "overall_position": {
            "quantity": 100.0,
            "cost_basis": 15000.0,
            "market_value": 17550.0,
        },
        "per_broker_positions": [
            {
                "broker": "IBKR",
                "quantity": 50.0,
                "cost_basis": 7500.0,
                "market_value": 8775.0,
            },
            {
                "broker": "Futu",
                "quantity": 50.0,
                "cost_basis": 7500.0,
                "market_value": 8775.0,
            },
        ],
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.lots_command("AAPL")
            output = fake_out.getvalue()

        # Verify API called without brokers parameter
        mock_get.assert_called_once_with(
            "/portfolio/lots/AAPL",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify output contains lots, overall_position, and per_broker_positions
    assert "LOTS (Paginated)" in output
    assert "OVERALL POSITION" in output
    assert "PER-BROKER POSITIONS" in output
    assert "100.0" in output
    assert "15000.0" in output


def test_lots_command_with_single_broker(cli_instance):
    """Test lots_command() with single broker."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response
    mock_response = {
        "lots": {"items": [], "total": 0, "page": 1, "size": 10, "pages": 0},
        "overall_position": {
            "quantity": 50.0,
            "cost_basis": 7500.0,
            "market_value": 8775.0,
        },
        "per_broker_positions": [
            {
                "broker": "IBKR",
                "quantity": 50.0,
                "cost_basis": 7500.0,
                "market_value": 8775.0,
            },
        ],
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.lots_command("AAPL", "IBKR")
            output = fake_out.getvalue()

        # Verify API called with brokers parameter (URL-encoded)
        from urllib.parse import quote_plus

        mock_get.assert_called_once_with(
            f"/portfolio/lots/AAPL?brokers={quote_plus('IBKR')}",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify output
    assert "LOTS (Paginated)" in output
    assert "OVERALL POSITION" in output
    assert "PER-BROKER POSITIONS" in output


def test_lots_command_with_multiple_brokers(cli_instance):
    """Test lots_command() with multiple brokers (comma-separated)."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response
    mock_response = {
        "lots": {"items": [], "total": 0, "page": 1, "size": 10, "pages": 0},
        "overall_position": {
            "quantity": 100.0,
            "cost_basis": 15000.0,
            "market_value": 17550.0,
        },
        "per_broker_positions": [
            {"broker": "IBKR", "quantity": 50.0, "cost_basis": 7500.0, "market_value": 8775.0},
            {"broker": "Futu", "quantity": 50.0, "cost_basis": 7500.0, "market_value": 8775.0},
        ],
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.lots_command("AAPL", "IBKR,Futu")
            output = fake_out.getvalue()

        # Verify API called with comma-separated brokers (URL-encoded)
        from urllib.parse import quote_plus

        mock_get.assert_called_once_with(
            f"/portfolio/lots/AAPL?brokers={quote_plus('IBKR,Futu')}",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify output
    assert "LOTS (Paginated)" in output
    assert "OVERALL POSITION" in output
    assert "PER-BROKER POSITIONS" in output


def test_lots_command_with_quoted_broker_name(cli_instance):
    """Test lots_command() with quoted broker name containing spaces."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response
    mock_response = {
        "lots": {"items": [], "total": 0, "page": 1, "size": 10, "pages": 0},
        "overall_position": {
            "quantity": 50.0,
            "cost_basis": 7500.0,
            "market_value": 8775.0,
        },
        "per_broker_positions": [
            {
                "broker": "Some Broker",
                "quantity": 50.0,
                "cost_basis": 7500.0,
                "market_value": 8775.0,
            },
        ],
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.lots_command("AAPL", "Some Broker")
            output = fake_out.getvalue()

        # Verify API called with URL-encoded broker name (spaces become +)
        from urllib.parse import quote_plus

        mock_get.assert_called_once_with(
            f"/portfolio/lots/AAPL?brokers={quote_plus('Some Broker')}",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify output
    assert "LOTS (Paginated)" in output
    assert "OVERALL POSITION" in output


def test_lots_command_authentication_error(cli_instance):
    """Test lots_command() with authentication error (401)."""
    # Don't set token (not logged in)
    cli_instance.token = None

    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.lots_command("AAPL")
        output = fake_out.getvalue()

    # Verify error message
    assert "Error" in output
    assert "Not logged in" in output
    assert "login" in output.lower()


def test_help_includes_lots_command_with_brokers(cli_instance):
    """Test that help command includes lots command with brokers parameter."""
    # Capture output
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.show_help()
        output = fake_out.getvalue()

    # Verify lots command is in help with brokers parameter
    assert "lots" in output.lower()
    assert "brokers" in output.lower()
    assert "quotes" in output.lower() or "names with spaces" in output.lower()
