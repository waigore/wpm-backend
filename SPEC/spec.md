# WPM Backend API Specification

## Purpose

This project provides a Python FastAPI backend that exposes Wealth Portfolio Manager (wpm) library functions as REST APIs for a React web frontend. The backend serves as an intermediary layer between the frontend and the wpm library, handling user authentication, CSV data import, and portfolio data retrieval. On application startup, the backend automatically imports all available trade CSV files using the wpm library's import functionality, loading them into a composite portfolio that can be queried via API endpoints.

## Package Layout

- **wpm_backend/**
  - **__init__.py**: Package initialization file
  - **main.py**: FastAPI application entry point, initializes app and includes routers
  - **config.py**: Application configuration and settings management
  - **auth/**
    - **__init__.py**: Auth module initialization
    - **auth.py**: User authentication logic and login endpoint handler
  - **api/**
    - **__init__.py**: API module initialization
    - **routes.py**: API route definitions (login, portfolio endpoints)
  - **services/**
    - **__init__.py**: Services module initialization
    - **portfolio_service.py**: Business logic for portfolio operations, wraps wpm library calls
  - **models/**
    - **__init__.py**: Models module initialization
    - **auth.py**: Pydantic models for authentication requests/responses
    - **portfolio.py**: Pydantic models for portfolio data structures
  - **utils/**
    - **__init__.py**: Utils module initialization
    - **logging_config.py**: Centralized logging configuration setup
    - **openapi_generator.py**: Utility to generate OpenAPI JSON specification from FastAPI app
  - **cli.py**: Interactive command-line utility for testing and interacting with the API
- **tests/**
  - **__init__.py**: Tests package initialization
  - **test_auth.py**: Unit and integration tests for authentication module
  - **test_portfolio.py**: Unit and integration tests for portfolio endpoints
  - **conftest.py**: Pytest configuration and shared fixtures
- **logs/**: Directory for application log files (gitignored)
- **pyproject.toml**: Project metadata, dependencies, and build configuration (managed by uv)
- **.env**: Environment variables file containing credentials (gitignored)
- **.gitignore**: Git ignore patterns (includes .env, logs/, __pycache__, etc.)

## Module Requirements

### wpm_backend/main.py
**Location**: `wpm_backend/main.py`

**Responsibilities**: 
- Initialize and configure the FastAPI application instance
- Register API routers
- Set up application lifecycle event handlers (startup/shutdown)
- Configure CORS, middleware, and other application-level settings

**Key Functions**:
- `create_app() -> FastAPI`: Factory function that creates and configures the FastAPI application instance
- `startup_event()`: Async event handler invoked on application startup; calls `wpm.importer.import_csv_files(import_dir: Path)` to import all available trade CSVs from the import directory. Stores the returned `CompositePortfolio` instance in application state (e.g., `app.state.composite_portfolio`) for use by portfolio endpoints. Logs import process at INFO level.

**Key Variables**:
- `app.state.composite_portfolio`: Stores the CompositePortfolio instance created during startup for access by portfolio endpoints

**Artifacts**: None

### wpm_backend/config.py
**Location**: `wpm_backend/config.py`

**Responsibilities**:
- Load and manage application configuration from environment variables
- Provide type-safe configuration access using Pydantic settings
- Handle credential loading from .env file

**Key Classes**:
- `Settings`: Pydantic BaseSettings class containing:
  - `username`: str - Static username for authentication (from .env)
  - `password`: str - Static password for authentication (from .env)
  - `secret_key`: str - Secret key for JWT token signing (from .env)
  - `algorithm`: str - JWT algorithm (default: "HS256")
  - `access_token_expire_minutes`: int - JWT token expiry time in minutes (default: 60)
  - `import_dir`: str - Directory path containing CSV files to import (default: "import")
  - `log_level`: str - Logging level (default: "INFO")
  - `log_dir`: str - Directory for log files (default: "logs")

**Artifacts**: None

### wpm_backend/auth/auth.py
**Location**: `wpm_backend/auth/auth.py`

**Responsibilities**:
- Handle user authentication logic
- Validate credentials against static username/password pairs stored in .env
- Generate JWT access tokens with expiry
- Verify and decode JWT tokens for protected endpoints
- Provide login function that can be extended in the future

**Key Functions**:
- `authenticate_user(username: str, password: str, settings: Settings) -> bool`: Validates provided credentials against settings. Returns True if credentials match, False otherwise. Logs authentication attempts at INFO level.
- `create_access_token(data: dict, settings: Settings, expires_delta: Optional[timedelta] = None) -> str`: Generates a JWT access token containing username and expiry time. Uses HS256 algorithm by default. Expiry defaults to 1 hour (60 minutes) from current time if expires_delta is None. Token payload includes: `sub` (username), `exp` (expiry timestamp), `iat` (issued at timestamp). Logs token creation at INFO level.
- `verify_token(token: str, settings: Settings) -> Optional[str]`: Verifies JWT token signature and expiry, extracts username from token payload. Returns username if token is valid, None if token is invalid or expired. Logs verification attempts at INFO level, token expiry at DEBUG level.

**Artifacts**: None

### wpm_backend/api/routes.py
**Location**: `wpm_backend/api/routes.py`

**Responsibilities**:
- Define all API endpoints
- Handle HTTP request/response logic
- Validate request data using Pydantic models
- Return appropriate HTTP status codes and error responses
- Configure OAuth2 scheme for JWT token extraction

**Key Variables**:
- `oauth2_scheme`: OAuth2PasswordBearer instance configured with tokenUrl="/login" for extracting JWT tokens from Authorization header

**Key Functions**:
- `login(request: LoginRequest, settings: Settings = Depends(get_settings)) -> LoginResponse`: POST endpoint at `/login` that accepts username/password, validates credentials via auth module, and returns JWT access token with 1-hour expiry. Logs request/response at INFO level.
- `get_all_positions_endpoint(...) -> PortfolioAllResponse`: GET endpoint at `/portfolio/all` that requires JWT authentication. Supports pagination and sorting via query parameters: `page` (default: 1), `size` (default: 20, max: 100), `sort_by` (default: "ticker"), and `sort_order` (default: "asc"). Verifies token via auth module, retrieves CompositePortfolio from application state, creates PriceService instance, calls portfolio_service.get_all_positions() with sorting parameters to fetch and transform positions, applies pagination using fastapi-pagination, retrieves portfolio totals using composite_portfolio.get_total_cost_basis(), get_total_market_value(), and get_total_unrealized_pnl(), then returns PortfolioAllResponse containing paginated positions and portfolio totals. Validates sort_by against allowed Position fields and returns 400 Bad Request for invalid fields. Logs request/response at INFO level.
- `get_asset_trades_endpoint(ticker: str, ...) -> PortfolioAssetTradesResponse`: GET endpoint at `/portfolio/trades/{ticker}` that requires JWT authentication. Supports pagination, date filtering, and sorting via query parameters: `page` (default: 1), `size` (default: 20, max: 100), `start_date` (optional, ISO format YYYY-MM-DD), `end_date` (optional, ISO format YYYY-MM-DD), `sort_by` (default: "date"), and `sort_order` (default: "asc"). Verifies token via auth module, retrieves CompositePortfolio from application state, calls portfolio_service.get_asset_trades() with ticker, date filtering, and sorting parameters to fetch and transform trades, applies pagination using fastapi-pagination, then returns PortfolioAssetTradesResponse containing paginated trades. Validates date formats and date range (start_date <= end_date), validates sort_by against allowed Trade fields, returns 400 Bad Request for invalid dates or sort_by field, 404 Not Found if ticker doesn't exist. Logs request/response at INFO level.
- `get_current_user(token: str = Depends(oauth2_scheme), settings: Settings = Depends(get_settings)) -> str`: Dependency function that extracts JWT token from Authorization header using OAuth2PasswordBearer, verifies it via auth module, and returns username. Raises HTTPException with 401 status if token is invalid or expired. Used to protect endpoints requiring authentication.

**Artifacts**: None

### wpm_backend/services/portfolio_service.py
**Location**: `wpm_backend/services/portfolio_service.py`

**Responsibilities**:
- Interface with the wpm library to retrieve portfolio data
- Transform wpm library data structures into API response models
- Handle errors from wpm library calls
- Provide abstraction layer between API and wpm library
- Manage PriceService for fetching current asset prices

**Key Functions**:
- `get_all_positions(composite: CompositePortfolio, price_service: PriceService, sort_by: Optional[str] = None, sort_order: Optional[str] = "asc") -> List[Position]`: Retrieves all positions from the wpm composite portfolio using `composite.get_positions()` which returns `Dict[Asset, Position]`. Fetches current prices using `wpm.portfolio.fetch_price_map(composite, price_service)` which returns `Dict[Asset, Optional[float]]`. Transforms wpm Position objects (containing Asset, Decimal quantity, cost_basis, cost_basis_method) into API Position models. Calculates market_value and unrealized_gain_loss when prices are available. Applies sorting based on `sort_by` and `sort_order` parameters. Validates `sort_by` against Position model fields. Handles None values for optional fields (current_price, market_value, unrealized_gain_loss) by treating None as smallest value. Defaults to ticker ascending if no sort parameters provided. Logs function entry/exit and wpm library calls at INFO level. Returns sorted list of API Position objects.
- `get_asset_trades(composite: CompositePortfolio, ticker: str, start_date: Optional[date] = None, end_date: Optional[date] = None, sort_by: Optional[str] = None, sort_order: Optional[str] = "asc") -> List[Trade]`: Retrieves all trades for a specific asset ticker from the wpm composite portfolio using `composite.get_asset_trades(ticker)` which returns a list of Trade objects. Filters trades by date range if `start_date` and/or `end_date` are provided (inclusive boundaries). Determines if a trade is a buy by checking the `action` field (from CSV "Action" column: "Buy" or "Sell"), with fallback to `order_instruction` field for backward compatibility. Transforms wpm Trade objects into API Trade models, extracting the broker field from the wpm Trade object. Applies sorting based on `sort_by` and `sort_order` parameters. Validates `sort_by` against Trade model fields. Defaults to date ascending if no sort parameters provided. Logs function entry/exit, date filtering, and sorting at INFO level. Returns sorted list of API Trade objects filtered by date range.

**Artifacts**: None

### wpm_backend/models/auth.py
**Location**: `wpm_backend/models/auth.py`

**Responsibilities**:
- Define Pydantic models for authentication-related data structures
- Provide request/response schemas for authentication endpoints
- Validate input data

**Key Classes**:
- `LoginRequest`: Request model for login endpoint
  - `username`: str (required, min_length=1)
  - `password`: str (required, min_length=1)
- `LoginResponse`: Response model for login endpoint
  - `access_token`: str (required)
  - `token_type`: str (default: "bearer")

**Artifacts**: None

### wpm_backend/models/portfolio.py
**Location**: `wpm_backend/models/portfolio.py`

**Responsibilities**:
- Define Pydantic models for portfolio-related data structures
- Provide request/response schemas for portfolio endpoints
- Ensure data validation and type safety

**Key Classes**:
- `Position`: Model representing a single portfolio position
  - Fields defined in Data Models section below
- `Trade`: Model representing a single trade for an asset
  - Fields defined in Data Models section below
- `PortfolioAllResponse`: Response model for `/portfolio/all` endpoint
  - `positions`: Page[Position] (required)
  - `total_market_value`: Optional[float]
  - `total_cost_basis`: float (required)
  - `total_unrealized_gain_loss`: Optional[float]
- `PortfolioAssetTradesResponse`: Response model for `/portfolio/trades/<ticker>` endpoint
  - `trades`: Page[Trade] (required)
- `PortfolioResponse`: Response model for portfolio endpoints (deprecated)
  - `positions`: List[Position] (required)
  - `total_count`: int (calculated, number of positions)

**Artifacts**: None

### wpm_backend/utils/logging_config.py
**Location**: `wpm_backend/utils/logging_config.py`

**Responsibilities**:
- Configure centralized logging using Python's built-in logging module
- Set up log file handlers and formatters
- Configure log levels for different components
- Ensure logs directory exists

**Key Functions**:
- `setup_logging(log_dir: str = "logs", log_level: str = "INFO") -> None`: Configures application-wide logging. Creates logs directory if it doesn't exist. Sets up file handler for logs/app.log with rotating file handler. Configures format: timestamp, level, module, message. Sets root logger level. Configures wpm library logger to also write to logs (if wpm uses standard logging).

**Artifacts**: 
- `logs/app.log`: Main application log file (gitignored)

### wpm_backend/utils/openapi_generator.py
**Location**: `wpm_backend/utils/openapi_generator.py`

**Responsibilities**:
- Generate OpenAPI JSON specification from FastAPI application
- Save specification to file for frontend consumption or documentation
- Ensure spec is updated whenever API schema changes

**Key Functions**:
- `generate_openapi_spec(app: FastAPI, output_path: str = "SPEC/openapi.json") -> None`: Generates OpenAPI 3.0 JSON specification from the FastAPI app instance using `app.openapi()`. Writes the JSON to the specified output path. Creates SPEC directory if it doesn't exist. Logs generation at INFO level.

**Artifacts**:
- `SPEC/openapi.json`: Generated OpenAPI 3.0 specification file

### wpm_backend/cli.py
**Location**: `wpm_backend/cli.py`

**Responsibilities**:
- Provide an interactive command-line interface for testing and interacting with wpm-backend APIs
- Use FastAPI's TestClient to start up the API instance without running a server
- Manage authentication tokens during the interactive session
- Execute API commands and display results in structured JSON format

**Key Classes**:
- `InteractiveCLI`: Manages the interactive CLI session, token storage, and command routing

**Key Functions**:
- `main() -> None`: Entry point function that initializes the FastAPI app using `create_app()`, creates a TestClient instance, and starts the interactive command loop. This function is registered as the `wpm-backend-cli` entry point in pyproject.toml.
- `InteractiveCLI.__init__(client: TestClient)`: Initializes the CLI with a TestClient instance and sets up token storage.
- `InteractiveCLI.login_command() -> None`: Prompts user for username and password (using `getpass.getpass()` for secure password input), calls POST `/login` endpoint via TestClient, stores the JWT access token in memory for subsequent authenticated requests. Displays success or error messages.
- `InteractiveCLI.portfolio_all_command() -> None`: Calls GET `/portfolio/all` endpoint via TestClient with stored JWT token in Authorization header. Displays the response in formatted JSON using `json.dumps()` with `indent=2`. Handles authentication errors by prompting user to login if token is missing or expired.
- `InteractiveCLI.trades_command(ticker: str) -> None`: Calls GET `/portfolio/trades/{ticker}` endpoint via TestClient with stored JWT token in Authorization header. Displays the response (paginated trades) in formatted JSON using `json.dumps()` with `indent=2`. Handles authentication errors (401), not found errors (404), validation errors (400), and server errors (500) with user-friendly error messages.
- `InteractiveCLI.run() -> None`: Main interactive loop that prompts for commands, parses input, routes to appropriate command handlers, and continues until user enters `exit` or `quit`.
- `InteractiveCLI.show_help() -> None`: Displays list of available commands and their descriptions, including the new `trades <ticker>` command.

**Key Variables**:
- `InteractiveCLI.client`: TestClient instance for making API requests
- `InteractiveCLI.token`: JWT access token stored in memory during the session (None if not logged in)

**Command Structure**:
- `login`: Prompts for username and password, authenticates via `/login` endpoint, stores token
- `portfolio all`: Retrieves all portfolio positions via `/portfolio/all` endpoint, displays formatted JSON
- `trades <ticker>`: Retrieves all trades for the specified asset ticker via `/portfolio/trades/{ticker}` endpoint, displays formatted JSON
- `help`: Lists available commands and their descriptions
- `exit`/`quit`: Terminates the interactive session

**Implementation Details**:
- Uses `from fastapi.testclient import TestClient` with `app = create_app()` to initialize the API
- TestClient automatically triggers FastAPI startup events, ensuring `composite_portfolio` and `price_service` are initialized in `app.state`
- Token is stored as instance variable and cleared on session end
- Uses `getpass.getpass()` for secure password input (masks password)
- Uses `json.dumps()` with `indent=2` for pretty-printed JSON output
- Handles HTTP errors (401, 500, etc.) with user-friendly error messages
- Simple string splitting for command parsing (e.g., `"portfolio all"` splits into `["portfolio", "all"]`)

**Artifacts**: None

**Entry Point Configuration**:
- Registered in `pyproject.toml` under `[project.scripts]` as `wpm-backend-cli = "wpm_backend.cli:main"`
- After package installation, the utility can be invoked from the command line as `wpm-backend-cli`

## Data Models

### LoginRequest
**Location**: `wpm_backend/models/auth.py`

Request model for the `/login` endpoint.

**Fields**:
- `username` (str, required)
  - Description: User's login username
  - Validation: Non-empty string, min_length=1
  - Example: "admin"
  
- `password` (str, required)
  - Description: User's login password
  - Validation: Non-empty string, min_length=1
  - Example: "secretpassword"

### LoginResponse
**Location**: `wpm_backend/models/auth.py`

Response model for the `/login` endpoint.

**Fields**:
- `access_token` (str, required)
  - Description: JWT (JSON Web Token) authentication token for subsequent API requests. Token contains username in `sub` claim and expires 1 hour after issuance.
  - Validation: Non-empty string, valid JWT format
  - Token Payload Structure:
    - `sub`: str - Username (subject)
    - `exp`: int - Expiration timestamp (Unix epoch)
    - `iat`: int - Issued at timestamp (Unix epoch)
  - Example: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTcwNTI5NDQwMCwiaWF0IjoxNzA1MjkwODAwfQ..."
  
- `token_type` (str, optional, default="bearer")
  - Description: Type of authentication token
  - Validation: String, typically "bearer"
  - Example: "bearer"

### Position
**Location**: `wpm_backend/models/portfolio.py`

Model representing a single position in the portfolio. This model is based on the actual wpm library's `Position` and `Asset` classes as used in the `cmd_show_all` function from `cli.py`.

**Fields**:
- `ticker` (str, required)
  - Description: Stock ticker symbol or asset identifier
  - Source: `position.asset.ticker` from wpm Position object
  - Validation: Non-empty string
  - Example: "AAPL"
  
- `asset_type` (str, required)
  - Description: Type of asset (e.g., "Stock", "Crypto", "Bond")
  - Source: `position.asset.asset_type` from wpm Position object
  - Validation: Non-empty string
  - Example: "Stock"
  
- `quantity` (float, required)
  - Description: Number of shares/units held (converted from Decimal to float for API)
  - Source: `float(position.quantity)` from wpm Position object (quantity is Decimal)
  - Validation: Non-negative float, ge=0
  - Example: 100.0
  
- `average_price` (float, required)
  - Description: Average purchase price per share/unit
  - Source: `position.get_average_cost()` or `position.average_cost` from wpm Position object
  - Calculation: `cost_basis / quantity` (handled by wpm Position.get_average_cost())
  - Validation: Non-negative float, ge=0
  - Example: 150.25
  
- `cost_basis` (float, required)
  - Description: Total cost basis of the position in USD
  - Source: `position.cost_basis` from wpm Position object
  - Validation: Non-negative float, ge=0
  - Example: 15025.0
  
- `cost_basis_method` (str, required)
  - Description: Method used to calculate cost basis ("fifo" or "average")
  - Source: `position.cost_basis_method` from wpm Position object
  - Validation: Must be "fifo" or "average"
  - Example: "fifo"
  
- `current_price` (float, optional)
  - Description: Current market price per share/unit in USD
  - Source: `price_map.get(asset)` from wpm fetch_price_map() result (may be None)
  - Validation: Non-negative float, ge=0 (if provided), None if price unavailable
  - Example: 175.50 or None
  
- `market_value` (float, optional, calculated)
  - Description: Current total market value of the position in USD
  - Calculation: `quantity * current_price` (only calculated if current_price is not None)
  - Validation: Non-negative float (if calculated), None if current_price unavailable
  - Example: 17550.0 or None
  
- `unrealized_gain_loss` (float, optional, calculated)
  - Description: Unrealized gain or loss on the position in USD
  - Calculation: `market_value - cost_basis` (only calculated if market_value is available)
  - Validation: Can be negative (loss) or positive (gain), None if market_value unavailable
  - Example: 2525.0 or None

### PortfolioAllResponse
**Location**: `wpm_backend/models/portfolio.py`

Response model for the `/portfolio/all` endpoint. Contains paginated positions and portfolio-level totals calculated across all positions in the composite portfolio (not just the current page).

**Fields**:
- `positions` (Page[Position], required)
  - Description: Paginated list of positions using fastapi-pagination Page structure
  - Contains: items, total, page, size, pages (see Page[Position] structure below)
  - Validation: Valid Page[Position] object
  - Example: Page[Position] with items=[Position(...), ...], total=100, page=1, size=20, pages=5
  
- `total_market_value` (float, optional)
  - Description: Total market value across all positions in the portfolio in USD
  - Source: `composite_portfolio.get_total_market_value()` from wpm library
  - Calculation: Sum of all position market values (handled by wpm library)
  - Validation: Non-negative float (if provided), None if prices unavailable for all positions
  - Example: 25050.0 or None
  
- `total_cost_basis` (float, required)
  - Description: Total cost basis across all positions in the portfolio in USD
  - Source: `composite_portfolio.get_total_cost_basis()` from wpm library
  - Calculation: Sum of all position cost bases (handled by wpm library)
  - Validation: Non-negative float, ge=0
  - Example: 20000.0
  
- `total_unrealized_gain_loss` (float, optional)
  - Description: Total unrealized gain or loss across all positions in the portfolio in USD
  - Source: `composite_portfolio.get_total_unrealized_pnl()` from wpm library
  - Calculation: Sum of all position unrealized gains/losses (handled by wpm library)
  - Validation: Can be negative (loss) or positive (gain), None if prices unavailable for all positions
  - Example: 5050.0 or None

**Note**: The totals are calculated from ALL positions in the composite portfolio, regardless of pagination parameters. This ensures the totals represent the entire portfolio, not just the positions on the current page.

### Trade
**Location**: `wpm_backend/models/portfolio.py`

Model representing a single trade for an asset. This model is based on the wpm library's `Trade` class.

**Fields**:
- `date` (str, required)
  - Description: Trade date in ISO format (YYYY-MM-DD)
  - Source: `trade.date` from wpm Trade object
  - Validation: ISO date string format
  - Example: "2024-01-15"
  
- `ticker` (str, required)
  - Description: Asset ticker symbol
  - Source: `trade.asset.ticker` or `trade.ticker` from wpm Trade object
  - Validation: Non-empty string
  - Example: "AAPL"
  
- `asset_type` (str, required)
  - Description: Type of asset (e.g., "Stock", "Crypto", "Bond")
  - Source: `trade.asset.asset_type` or `trade.asset_type` from wpm Trade object
  - Validation: Non-empty string
  - Example: "Stock"
  
- `action` (str, required)
  - Description: Trade action from CSV "Action" column indicating whether the trade is a buy or sell
  - Source: `trade.action` from wpm Trade object (from CSV "Action" column). If not available, derived from order_instruction for backward compatibility
  - Validation: Non-empty string, normalized to "Buy" or "Sell" (capitalized)
  - Example: "Buy" or "Sell"
  
- `order_instruction` (str, required)
  - Description: Order instruction type (e.g., "Limit", "Market", etc.) from the CSV "Order Instruction" column. Note: Buy/sell determination is based on the `action` field (from CSV "Action" column), not this field.
  - Source: `trade.order_instruction` from wpm Trade object
  - Validation: Non-empty string
  - Example: "Limit" or "Market"
  
- `quantity` (float, required)
  - Description: Number of shares/units traded
  - Source: `float(trade.quantity)` from wpm Trade object (quantity may be Decimal)
  - Validation: Non-negative float
  - Example: 100.0
  
- `price` (float, required)
  - Description: Price per share/unit at time of trade
  - Source: `float(trade.price)` from wpm Trade object
  - Validation: Non-negative float, ge=0
  - Example: 150.25
  
- `broker` (str, required)
  - Description: Broker name from which the trade originated (e.g., "IBKR", "Futu", "Crypto")
  - Source: `trade.broker` from wpm Trade object
  - Validation: Non-empty string
  - Example: "IBKR"

### PortfolioAssetTradesResponse
**Location**: `wpm_backend/models/portfolio.py`

Response model for the `/portfolio/trades/<ticker>` endpoint. Contains paginated trades for a specific asset ticker.

**Fields**:
- `trades` (Page[Trade], required)
  - Description: Paginated list of trades using fastapi-pagination Page structure
  - Contains: items, total, page, size, pages (see Page[Trade] structure below)
  - Validation: Valid Page[Trade] object
  - Example: Page[Trade] with items=[Trade(...), ...], total=50, page=1, size=20, pages=3

**Note**: The trades are filtered by the provided date range (if specified) and paginated according to the page and size parameters.

### Page[Trade]
**Location**: `fastapi_pagination.Page`

Paginated response structure used within PortfolioAssetTradesResponse. Uses fastapi-pagination library for standardized pagination.

**Fields**:
- `items` (List[Trade], required)
  - Description: List of trades in the current page
  - Validation: List of valid Trade objects
  - Example: [Trade(date="2024-01-15", ticker="AAPL", ...), ...]
  
- `total` (int, required)
  - Description: Total number of items across all pages
  - Validation: Non-negative integer
  - Example: 50
  
- `page` (int, required)
  - Description: Current page number (1-indexed)
  - Validation: Positive integer, >= 1
  - Example: 1
  
- `size` (int, required)
  - Description: Number of items per page
  - Validation: Positive integer, >= 1, <= 100
  - Example: 20
  
- `pages` (int, required)
  - Description: Total number of pages
  - Calculation: `ceil(total / size)`
  - Validation: Non-negative integer
  - Example: 3

### Page[Position]
**Location**: `fastapi_pagination.Page`

Paginated response structure used within PortfolioAllResponse. Uses fastapi-pagination library for standardized pagination.

**Fields**:
- `items` (List[Position], required)
  - Description: List of positions in the current page
  - Validation: List of valid Position objects
  - Example: [Position(ticker="AAPL", quantity=100.0, ...), ...]
  
- `total` (int, required)
  - Description: Total number of items across all pages
  - Validation: Non-negative integer
  - Example: 100
  
- `page` (int, required)
  - Description: Current page number (1-indexed)
  - Validation: Positive integer, >= 1
  - Example: 1
  
- `size` (int, required)
  - Description: Number of items per page
  - Validation: Positive integer, >= 1, <= 100
  - Example: 20
  
- `pages` (int, required)
  - Description: Total number of pages
  - Calculation: `ceil(total / size)`
  - Validation: Non-negative integer
  - Example: 5

### PortfolioResponse (Deprecated)
**Location**: `wpm_backend/models/portfolio.py`

**Note**: This model is deprecated. The `/portfolio/all` endpoint now returns `Page[Position]` instead.

**Fields**:
- `positions` (List[Position], required)
  - Description: List of all positions in the composite portfolio
  - Validation: List of valid Position objects
  - Example: [Position(ticker="AAPL", quantity=100.0, ...), ...]
  
- `total_count` (int, calculated)
  - Description: Total number of positions
  - Calculation: `len(positions)`
  - Validation: Non-negative integer
  - Example: 15

## External Dependencies

### Core Dependencies
- **fastapi** (>=0.104.0): Modern web framework for building APIs with automatic OpenAPI documentation
- **uvicorn[standard]** (>=0.24.0): ASGI server for running FastAPI application in production
- **pydantic** (>=2.0.0): Data validation and settings management using Python type annotations
- **python-dotenv** (>=1.0.0): Load environment variables from .env file
- **python-jose[cryptography]** (>=3.3.0): JWT token encoding and decoding with cryptographic support
- **passlib[bcrypt]** (>=1.7.4): Password hashing utilities (for future password storage enhancements)
- **fastapi-pagination** (>=0.12.0): Standardized pagination support for FastAPI endpoints

### WPM Library
- **wpm** (git+https://github.com/waigore/wpmv2.git@dev): Wealth Portfolio Manager library installed from GitHub dev branch. Key components:
  - `wpm.importer.import_csv_files(import_dir: Path) -> CompositePortfolio`: Function to import all available trade CSV files from a directory and return a CompositePortfolio
  - `wpm.portfolio.CompositePortfolio`: Composite portfolio class that aggregates positions from sub-portfolios
  - `CompositePortfolio.get_positions() -> Dict[Asset, Position]`: Returns dictionary mapping Asset objects to Position objects
  - `CompositePortfolio.get_asset_trades(ticker: str) -> List[Trade]`: Returns list of Trade objects for a specific asset ticker
  - `wpm.portfolio.fetch_price_map(portfolio: Portfolio, price_service: PriceService) -> Dict[Asset, Optional[float]]`: Fetches current prices for all assets in portfolio
  - `wpm.pricing.PriceService`: Service for retrieving current asset prices from various sources
  - `wpm.models.Position`: Position model with asset (Asset), quantity (Decimal), cost_basis (float), cost_basis_method (str)
  - `wpm.models.Trade`: Trade model with date, asset (Asset), order_instruction (str), quantity (Decimal), price (float)
  - `wpm.models.Asset`: Asset model with ticker (str) and asset_type (str)

### Development Dependencies
- **pytest** (>=7.4.0): Testing framework for writing and running tests
- **pytest-cov** (>=4.1.0): Pytest plugin for code coverage reporting
- **pytest-asyncio** (>=0.21.0): Pytest plugin for testing async code
- **httpx** (>=0.25.0): HTTP client for testing FastAPI endpoints (used by TestClient)

### Build and Packaging
- **setuptools** (>=68.0.0): Package building and distribution
- **wheel** (>=0.41.0): Built-package format for Python

## Testing

### Coverage Requirement
- **Target**: Minimum 80% code coverage across all modules
- **Tool**: pytest-cov for coverage measurement
- **Command**: `pytest --cov=wpm_backend --cov-report=html --cov-report=term`

### Test Structure
- **Location**: `tests/` directory
- **Framework**: pytest
- **Test Files**:
  - `test_auth.py`: Tests for authentication module
    - Test `authenticate_user()` with valid/invalid credentials
    - Test login endpoint with various scenarios
    - Test JWT token generation with correct payload structure
    - Test JWT token verification and expiry validation
    - Test token expiry after 1 hour
    - Test protected endpoint access with valid/invalid/expired tokens
  - `test_portfolio.py`: Tests for portfolio endpoints
    - Test `/portfolio/all` endpoint
    - Test portfolio service functions
    - Test data transformation from wpm library to API models
  - `conftest.py`: Shared fixtures
    - FastAPI test client fixture
    - Settings fixture with test credentials
    - Mock wpm library fixtures

### Test Types
- **Unit Tests**: Test individual functions and classes in isolation
- **Integration Tests**: Test API endpoints with test client
- **Mocking**: Mock wpm library calls to avoid dependencies on actual CSV files during testing

### Running Tests
- **Command**: `pytest` (from project root)
- **With Coverage**: `pytest --cov=wpm_backend --cov-report=term-missing`
- **Verbose**: `pytest -v`
- **Specific Test**: `pytest tests/test_auth.py::test_login_success`

## Logging and Observability

### Logging Framework
- **Module**: Python's built-in `logging` module
- **Configuration**: Centralized in `wpm_backend/utils/logging_config.py`
- **Log Directory**: `logs/` (gitignored, created automatically if missing)

### Log Levels
- **INFO**: 
  - Inputs and outputs of all externally callable functions (API endpoints, service functions)
  - Authentication attempts (success and failure)
  - API request/response summaries
  - WPM library function calls and results
- **DEBUG**: 
  - Internal/private function execution details
  - Intermediate calculation steps
  - Detailed error stack traces
  - WPM library internal operations (if available)

### Log Format
- **Format String**: `"%(asctime)s - %(name)s - %(levelname)s - %(message)s"`
- **Date Format**: ISO 8601 format with milliseconds
- **Example**: `2024-01-15 10:30:45,123 - wpm_backend.api.routes - INFO - Login request received for user: admin`

### Log Files
- **Primary Log**: `logs/app.log`
- **Rotation**: Use `RotatingFileHandler` with maxBytes=10MB, backupCount=5
- **WPM Library Logs**: Configure wpm library logger to also write to `logs/app.log` if wpm uses standard logging

### Logging Examples
- **API Endpoint**: Log request parameters at entry, response status at exit
- **Authentication**: Log username (not password) and success/failure
- **Portfolio Service**: Log function entry, wpm library calls, number of positions returned
- **Errors**: Log full exception traceback at ERROR level

### Observability Considerations
- All external API calls should be logged
- JWT token creation and verification should be logged at INFO level
- Token expiry events should be logged at DEBUG level
- Performance metrics can be added in the future (request duration, etc.)
- Structured logging (JSON format) can be considered for future enhancements

## Security Considerations

### JWT Token Security
- **Secret Key**: Must be stored in .env file and never committed to version control. Should be a strong, randomly generated string (minimum 32 characters recommended).
- **Token Expiry**: Default 1-hour expiry provides balance between security and user convenience. Tokens cannot be revoked before expiry (stateless design).
- **Algorithm**: HS256 (HMAC with SHA-256) is used by default. The secret key must be kept secure as it's used to sign and verify tokens.
- **Token Storage**: Frontend should store tokens securely (e.g., httpOnly cookies or secure localStorage) and include them in Authorization header as `Bearer <token>`.
- **Protected Endpoints**: All endpoints except `/login` should require valid JWT token in Authorization header.

### Credential Management
- Username and password are stored in .env file as plain text for now (static authentication).
- Future enhancements may include password hashing and database-backed user management.

