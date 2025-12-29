"""Interactive command-line utility for testing and interacting with wpm-backend APIs."""

import asyncio
import json
import logging
import sys
from getpass import getpass
from typing import Optional

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

                # Parse command (simple string splitting)
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

