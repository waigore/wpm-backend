"""Unit and integration tests for CLI commands."""

from io import StringIO
from unittest.mock import MagicMock, Mock, patch
from datetime import date

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


def test_portfolio_all_command_displays_totals(cli_instance):
    """Test portfolio_all_command() displays portfolio totals including realized P/L."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response with all totals
    mock_response = {
        "positions": {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 20,
            "pages": 0,
        },
        "total_cost_basis": 20000.0,
        "total_market_value": 25050.0,
        "total_unrealized_gain_loss": 5050.0,
        "total_realized_gain_loss": 300.0,
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.portfolio_all_command()
            output = fake_out.getvalue()

        # Verify API was called
        mock_get.assert_called_once_with(
            "/portfolio/all",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify portfolio totals are displayed
    assert "PORTFOLIO TOTALS" in output
    assert "Total Cost Basis" in output
    assert "$20,000.00" in output or "20000.00" in output
    assert "Total Market Value" in output
    assert "$25,050.00" in output or "25050.00" in output
    assert "Total Unrealized P&L" in output
    assert "+$5,050.00" in output or "+5050.00" in output
    assert "Total Realized P&L" in output
    assert "+$300.00" in output or "+300.00" in output


def test_portfolio_all_command_displays_negative_realized_pnl(cli_instance):
    """Test portfolio_all_command() displays negative realized P/L correctly."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response with negative realized P/L
    mock_response = {
        "positions": {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 20,
            "pages": 0,
        },
        "total_cost_basis": 20000.0,
        "total_market_value": 25050.0,
        "total_unrealized_gain_loss": 5050.0,
        "total_realized_gain_loss": -500.0,
    }

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            cli_instance.portfolio_all_command()
            output = fake_out.getvalue()

    # Verify negative realized P/L is displayed (no + sign)
    assert "Total Realized P&L" in output
    assert "-$500.00" in output or "-500.00" in output
    # Verify no + sign before negative value
    assert "+-$500.00" not in output


def test_reference_performance_command_minimal_args(cli_instance):
    """Test ref command with minimal args uses today's date and no granularity."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    # Mock the API response
    mock_history_points = [{"date": f"2024-01-{day:02d}"} for day in range(1, 15)]
    mock_response = {"history_points": mock_history_points}

    today_iso = date.today().isoformat()

    # Mock the client.get method
    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        # Capture output
        with patch("sys.stdout", new=StringIO()) as fake_out:
            # Invoke via command parser to exercise argument handling
            with patch("builtins.input", side_effect=["ref SPY ETF", "exit"]):
                cli_instance.run()
            output = fake_out.getvalue()

        # Verify API called with today's date and no granularity
        mock_get.assert_any_call(
            f"/reference/SPY/performance?asset_type=ETF&end_date={today_iso}",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )

    # Verify output shows last 10 points and note about truncation
    assert "PORTFOLIO PERFORMANCE (Last 10 Points)" in output
    assert '"date": "2024-01-14"' in output
    assert "Note: Showing last 10 of 14 total history points" in output


def test_reference_performance_command_with_end_date_only(cli_instance):
    """Test ref command with explicit end_date only."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    mock_response = {"history_points": []}

    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        with patch("sys.stdout", new=StringIO()):
            with patch("builtins.input", side_effect=["ref SPY ETF 2024-01-31", "exit"]):
                cli_instance.run()

        mock_get.assert_any_call(
            "/reference/SPY/performance?asset_type=ETF&end_date=2024-01-31",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )


def test_reference_performance_command_with_granularity_only(cli_instance):
    """Test ref command with granularity only."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    mock_response = {"history_points": []}

    today_iso = date.today().isoformat()

    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        with patch("sys.stdout", new=StringIO()):
            with patch("builtins.input", side_effect=["ref SPY ETF weekly", "exit"]):
                cli_instance.run()

        mock_get.assert_any_call(
            f"/reference/SPY/performance?asset_type=ETF&end_date={today_iso}&granularity=weekly",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )


def test_reference_performance_command_with_end_date_and_granularity(cli_instance):
    """Test ref command with both end_date and granularity."""
    # Setup authentication
    login_response = cli_instance.client.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert login_response.status_code == 200
    cli_instance.token = login_response.json()["access_token"]

    mock_response = {"history_points": []}

    with patch.object(cli_instance.client, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_response

        with patch("sys.stdout", new=StringIO()):
            with patch(
                "builtins.input",
                side_effect=["ref SPY ETF 2024-01-31 monthly", "exit"],
            ):
                cli_instance.run()

        mock_get.assert_any_call(
            "/reference/SPY/performance?asset_type=ETF&end_date=2024-01-31&granularity=monthly",
            headers={"Authorization": f"Bearer {cli_instance.token}"},
        )


def test_reference_performance_command_not_logged_in(cli_instance):
    """Test ref command when not logged in."""
    cli_instance.token = None

    with patch.object(cli_instance.client, "get") as mock_get:
        with patch("sys.stdout", new=StringIO()) as fake_out:
            with patch("builtins.input", side_effect=["ref SPY ETF", "exit"]):
                cli_instance.run()
            output = fake_out.getvalue()

        # Ensure no API call was made
        mock_get.assert_not_called()

    assert "Error: Not logged in" in output
    assert "login" in output.lower()


def test_help_includes_ref_command(cli_instance):
    """Test that help command includes ref command."""
    with patch("sys.stdout", new=StringIO()) as fake_out:
        cli_instance.show_help()
        output = fake_out.getvalue()

    assert "ref <ticker> <asset_type> [YYYY-MM-DD] [granularity]" in output
