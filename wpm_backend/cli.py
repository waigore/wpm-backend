"""Interactive command-line utility for testing and interacting with wpm-backend APIs."""

import asyncio
import json
import logging
import shlex
import sys
from datetime import date
from getpass import getpass
from typing import List, Optional
from urllib.parse import quote_plus

from fastapi import FastAPI
from fastapi.testclient import TestClient

from wpm_backend.config import Settings, get_settings
from wpm_backend.main import create_app
from wpm_backend.utils.startup import run_startup_logic

logger = logging.getLogger(__name__)


class InteractiveCLI:
    """Interactive CLI for interacting with wpm-backend APIs."""

    def __init__(self, client: TestClient, app: FastAPI) -> None:
        """
        Initialize the CLI with a TestClient instance.

        Args:
            client: FastAPI TestClient instance for making API requests
            app: FastAPI application instance for checking state
        """
        self.client = client
        self.app = app
        self.token: Optional[str] = None

    def login_command(self) -> None:
        """Prompt for username/password and authenticate via /login endpoint."""
        print("Login required to access protected endpoints.")
        username = input("Username: ").strip()
        if not username:
            print("Error: Username cannot be empty.")
            return

        password = getpass("Password: ")
        if not password:
            print("Error: Password cannot be empty.")
            return

        # Call login endpoint
        try:
            response = self.client.post(
                "/login",
                json={"username": username, "password": password},
            )

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                print("Login successful!")
            elif response.status_code == 401:
                print("Error: Invalid username or password.")
            else:
                print(f"Error: Login failed with status code {response.status_code}")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: Failed to connect to API: {e}")

    def portfolio_all_command(self) -> None:
        """Call /portfolio/all endpoint and display results with portfolio totals."""
        if not self.token:
            print("Error: Not logged in. Please run 'login' first.")
            return

        # Call portfolio/all endpoint with authentication
        try:
            response = self.client.get(
                "/portfolio/all",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if response.status_code == 200:
                data = response.json()
                
                # Display portfolio totals prominently
                print("\n" + "=" * 60)
                print("PORTFOLIO TOTALS")
                print("=" * 60)
                
                # Format total_cost_basis (always available)
                total_cost_basis = data.get("total_cost_basis", 0.0)
                print(f"Total Cost Basis:    ${total_cost_basis:,.2f}")
                
                # Format total_market_value (may be None)
                total_market_value = data.get("total_market_value")
                if total_market_value is not None:
                    print(f"Total Market Value:  ${total_market_value:,.2f}")
                else:
                    print("Total Market Value:  N/A (prices unavailable)")
                
                # Format total_unrealized_gain_loss (may be None)
                total_unrealized_gain_loss = data.get("total_unrealized_gain_loss")
                if total_unrealized_gain_loss is not None:
                    sign = "+" if total_unrealized_gain_loss >= 0 else ""
                    print(f"Total Unrealized P&L: {sign}${total_unrealized_gain_loss:,.2f}")
                else:
                    print("Total Unrealized P&L: N/A (prices unavailable)")
                
                print("=" * 60)
                print()
                
                # Display paginated positions
                positions_data = data.get("positions", {})
                print("POSITIONS (Paginated)")
                print("-" * 60)
                print(json.dumps(positions_data, indent=2))
            elif response.status_code == 401:
                print("Error: Authentication failed. Token may be expired. Please run 'login' again.")
                self.token = None  # Clear invalid token
            elif response.status_code == 500:
                print("Error: Server error. Portfolio data may not be available.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            else:
                print(f"Error: Request failed with status code {response.status_code}")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: Failed to connect to API: {e}")

    def trades_command(self, ticker: str) -> None:
        """Call /portfolio/trades/{ticker} endpoint and display results with paginated trades."""
        if not self.token:
            print("Error: Not logged in. Please run 'login' first.")
            return

        # Call portfolio/asset/{ticker} endpoint with authentication
        try:
            response = self.client.get(
                f"/portfolio/trades/{ticker}",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if response.status_code == 200:
                data = response.json()
                
                # Display paginated trades
                trades_data = data.get("trades", {})
                print("\nTRADES (Paginated)")
                print("-" * 60)
                print(json.dumps(trades_data, indent=2))
            elif response.status_code == 401:
                print("Error: Authentication failed. Token may be expired. Please run 'login' again.")
                self.token = None  # Clear invalid token
            elif response.status_code == 404:
                print(f"Error: Ticker '{ticker}' not found.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            elif response.status_code == 400:
                print("Error: Invalid request parameters.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            elif response.status_code == 500:
                print("Error: Server error. Trade data may not be available.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            else:
                print(f"Error: Request failed with status code {response.status_code}")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: Failed to connect to API: {e}")

    def lots_command(self, ticker: str, brokers: Optional[str] = None) -> None:
        """Call /portfolio/lots/{ticker} endpoint and display results with paginated lots, overall position, and per-broker positions."""
        if not self.token:
            print("Error: Not logged in. Please run 'login' first.")
            return

        # Build URL with optional brokers query parameter
        url = f"/portfolio/lots/{ticker}"
        if brokers:
            # URL-encode brokers parameter to handle special characters
            url += f"?brokers={quote_plus(brokers)}"

        # Call portfolio/lots/{ticker} endpoint with authentication
        try:
            response = self.client.get(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if response.status_code == 200:
                data = response.json()
                
                # Display paginated lots
                lots_data = data.get("lots", {})
                print("\nLOTS (Paginated)")
                print("-" * 60)
                print(json.dumps(lots_data, indent=2))
                
                # Display overall position
                overall_position = data.get("overall_position")
                if overall_position:
                    print("\nOVERALL POSITION")
                    print("-" * 60)
                    print(json.dumps(overall_position, indent=2))
                
                # Display per-broker positions
                per_broker_positions = data.get("per_broker_positions", [])
                if per_broker_positions:
                    print("\nPER-BROKER POSITIONS")
                    print("-" * 60)
                    print(json.dumps(per_broker_positions, indent=2))
            elif response.status_code == 401:
                print("Error: Authentication failed. Token may be expired. Please run 'login' again.")
                self.token = None  # Clear invalid token
            elif response.status_code == 404:
                print(f"Error: Ticker '{ticker}' not found.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            elif response.status_code == 400:
                print("Error: Invalid request parameters.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            elif response.status_code == 500:
                print("Error: Server error. Lot data may not be available.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            else:
                print(f"Error: Request failed with status code {response.status_code}")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: Failed to connect to API: {e}")

    def metadata_command(self, tickers: List[str]) -> None:
        """Call /asset/metadata/{ticker} endpoint for each ticker and display results."""
        if not self.token:
            print("Error: Not logged in. Please run 'login' first.")
            return

        if not tickers:
            print("Error: At least one ticker is required. Usage: metadata <ticker1> [ticker2] ...")
            return

        # Process each ticker independently
        for ticker in tickers:
            try:
                response = self.client.get(
                    f"/asset/metadata/{ticker}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )

                if response.status_code == 200:
                    data = response.json()
                    
                    # Display metadata for this ticker
                    print(f"\nMETADATA for {ticker}")
                    print("-" * 60)
                    print(json.dumps(data, indent=2))
                elif response.status_code == 401:
                    print(f"Error: Authentication failed for ticker '{ticker}'. Token may be expired. Please run 'login' again.")
                    self.token = None  # Clear invalid token
                    return  # Stop processing remaining tickers if auth fails
                elif response.status_code == 404:
                    print(f"Error: Ticker '{ticker}' not found.")
                    try:
                        error_detail = response.json().get("detail", "Unknown error")
                        print(f"Details: {error_detail}")
                    except Exception:
                        print(f"Response: {response.text}")
                elif response.status_code == 500:
                    print(f"Error: Server error while retrieving metadata for ticker '{ticker}'.")
                    try:
                        error_detail = response.json().get("detail", "Unknown error")
                        print(f"Details: {error_detail}")
                    except Exception:
                        print(f"Response: {response.text}")
                else:
                    print(f"Error: Request failed for ticker '{ticker}' with status code {response.status_code}")
                    try:
                        error_detail = response.json().get("detail", "Unknown error")
                        print(f"Details: {error_detail}")
                    except Exception:
                        print(f"Response: {response.text}")
            except Exception as e:
                print(f"Error: Failed to connect to API for ticker '{ticker}': {e}")

    def performance_command(self, end_date: Optional[str] = None, granularity: Optional[str] = None) -> None:
        """Call /portfolio/all/performance endpoint and display last 10 history points."""
        if not self.token:
            print("Error: Not logged in. Please run 'login' first.")
            return

        # Default to today if end_date is not provided
        if end_date is None:
            end_date = date.today().isoformat()

        # Build query parameters
        query_params = f"end_date={end_date}"
        if granularity is not None:
            query_params += f"&granularity={granularity}"

        # Call portfolio/all/performance endpoint with authentication
        try:
            response = self.client.get(
                f"/portfolio/all/performance?{query_params}",
                headers={"Authorization": f"Bearer {self.token}"},
            )

            if response.status_code == 200:
                data = response.json()
                
                # Extract history points
                history_points = data.get("history_points", [])
                
                # Display last 10 points only
                last_10_points = history_points[-10:] if len(history_points) > 10 else history_points
                
                print("\nPORTFOLIO PERFORMANCE (Last 10 Points)")
                print("-" * 60)
                print(json.dumps(last_10_points, indent=2))
                
                if len(history_points) > 10:
                    print(f"\nNote: Showing last 10 of {len(history_points)} total history points")
            elif response.status_code == 401:
                print("Error: Authentication failed. Token may be expired. Please run 'login' again.")
                self.token = None  # Clear invalid token
            elif response.status_code == 400:
                print("Error: Invalid request parameters.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            elif response.status_code == 500:
                print("Error: Server error. Historical portfolio data may not be available.")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
            else:
                print(f"Error: Request failed with status code {response.status_code}")
                try:
                    error_detail = response.json().get("detail", "Unknown error")
                    print(f"Details: {error_detail}")
                except Exception:
                    print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: Failed to connect to API: {e}")

    def status_command(self) -> None:
        """Check the status of portfolio data and services."""
        print("\nApplication Status:")
        
        # Check portfolio
        portfolio = getattr(self.app.state, "composite_portfolio", None)
        if portfolio is None:
            print("  Portfolio: Not loaded")
        else:
            try:
                positions = portfolio.get_positions()
                print(f"  Portfolio: Loaded ({len(positions)} positions)")
            except Exception as e:
                print(f"  Portfolio: Error accessing positions: {e}")
        
        # Check price service
        price_service = getattr(self.app.state, "price_service", None)
        if price_service is None:
            print("  Price Service: Not available")
        else:
            print("  Price Service: Available")
        
        # Check authentication
        if self.token:
            print("  Authentication: Logged in")
        else:
            print("  Authentication: Not logged in")
        
        print()

    def show_help(self) -> None:
        """Display help message with available commands."""
        print("\nAvailable commands:")
        print("  login           - Login with username/password (required for protected endpoints)")
        print("  portfolio all   - Get all portfolio positions (requires login)")
        print("  trades <ticker> - Get all trades for an asset ticker (requires login)")
        print("  lots <ticker> [brokers] - Get all lots for an asset ticker, optionally filtered by brokers (comma-separated, use quotes for names with spaces) (requires login)")
        print("  metadata <ticker1> [ticker2] ... - Get metadata for one or more asset tickers (requires login)")
        print("  performance [YYYY-MM-DD] [granularity] - Get portfolio performance up to date (requires login, defaults to today, optional granularity: daily/weekly/monthly)")
        print("  status          - Check application status (portfolio data, services)")
        print("  help            - Show this help message")
        print("  exit, quit      - Exit the CLI")
        print()

    def run(self) -> None:
        """Main interactive loop."""
        print("WPM Backend CLI")
        print("Type 'help' for available commands, 'exit' or 'quit' to exit.\n")

        while True:
            try:
                command = input("wpm-backend> ").strip()

                if not command:
                    continue

                # Parse command using shlex.split() to handle quoted strings properly
                try:
                    parts = shlex.split(command)
                except ValueError:
                    # If quote parsing fails, fall back to simple split
                    parts = command.split()
                cmd = parts[0].lower()

                if cmd in ("exit", "quit"):
                    print("Goodbye!")
                    break
                elif cmd == "help":
                    self.show_help()
                elif cmd == "login":
                    self.login_command()
                elif cmd == "portfolio" and len(parts) > 1 and parts[1].lower() == "all":
                    self.portfolio_all_command()
                elif cmd == "trades":
                    if len(parts) > 1:
                        ticker = parts[1]
                        self.trades_command(ticker)
                    else:
                        print("Error: Ticker is required. Usage: trades <ticker>")
                elif cmd == "lots":
                    if len(parts) > 1:
                        ticker = parts[1]
                        brokers = parts[2] if len(parts) > 2 else None
                        self.lots_command(ticker, brokers)
                    else:
                        print("Error: Ticker is required. Usage: lots <ticker> [brokers]")
                elif cmd == "metadata":
                    if len(parts) > 1:
                        tickers = parts[1:]
                        self.metadata_command(tickers)
                    else:
                        print("Error: At least one ticker is required. Usage: metadata <ticker1> [ticker2] ...")
                elif cmd == "performance":
                    if len(parts) > 2:
                        # Both end_date and granularity provided
                        end_date = parts[1]
                        granularity = parts[2]
                        self.performance_command(end_date, granularity)
                    elif len(parts) > 1:
                        # Only end_date provided (could be date or granularity)
                        # Try to parse as date first, if it fails assume it's granularity
                        try:
                            # Validate it's a date by trying to parse it
                            date.fromisoformat(parts[1])
                            end_date = parts[1]
                            self.performance_command(end_date)
                        except ValueError:
                            # Not a valid date, assume it's granularity
                            granularity = parts[1]
                            self.performance_command(None, granularity)
                    else:
                        # Call without arguments to use default (today, daily)
                        self.performance_command()
                elif cmd == "status":
                    self.status_command()
                else:
                    print(f"Unknown command: {command}")
                    print("Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except EOFError:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")


def main() -> None:
    """
    Entry point for the CLI utility.

    Initializes the FastAPI app, creates a TestClient, and starts the interactive CLI.
    """
    try:
        # Create FastAPI app instance
        app = create_app()

        # Explicitly trigger startup events
        # TestClient doesn't automatically trigger async startup events
        # We manually run the startup logic here
        try:
            # Get settings
            try:
                settings = get_settings()
            except Exception:
                # Use defaults if settings can't be loaded
                settings = Settings(
                    username="admin",
                    password="password",
                    secret_key="default-secret-key-for-development-only",
                    import_dir="import",
                    log_level="INFO",
                    log_dir="logs",
                )

            # Run startup logic in async context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_startup_logic(app, settings))
                print("Application startup completed.", file=sys.stderr)
            finally:
                loop.close()
        except Exception as e:
            print(f"Warning: Failed to trigger startup events: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            # Continue anyway - some features might not work

        # Create TestClient
        client = TestClient(app)

        # Create and run CLI
        cli = InteractiveCLI(client, app)
        cli.run()

    except Exception as e:
        print(f"Error: Failed to initialize CLI: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

