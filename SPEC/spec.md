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
- `startup_event()`: Async event handler invoked on application startup; calls `wpm_backend.utils.startup.run_startup_logic(app, settings)` to execute startup logic including CSV import, historical portfolio cloning, and OpenAPI specification generation.

**Key Variables**:
- `app.state.composite_portfolio`: Stores the CompositePortfolio instance created during startup for access by portfolio endpoints
- `app.state.historical_portfolio`: Stores the cloned historical CompositePortfolio instance created during startup for use by performance endpoint

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
- `get_asset_lots_endpoint(ticker: str, ...) -> PortfolioAssetLotsResponse`: GET endpoint at `/portfolio/lots/{ticker}` that requires JWT authentication. Supports pagination, date filtering, and sorting via query parameters: `page` (default: 1), `size` (default: 20, max: 100), `start_date` (optional, ISO format YYYY-MM-DD), `end_date` (optional, ISO format YYYY-MM-DD), `sort_by` (default: "date"), and `sort_order` (default: "asc"). Verifies token via auth module, retrieves CompositePortfolio and PriceService from application state, calls portfolio_service.get_asset_lots() with ticker, price_service, date filtering, and sorting parameters to fetch and transform lots, applies pagination using fastapi-pagination, then returns PortfolioAssetLotsResponse containing paginated lots. Validates date formats and date range (start_date <= end_date), validates sort_by against allowed Lot fields (date, original_quantity, remaining_quantity, cost_basis, broker, realized_pnl, unrealized_pnl, total_pnl), returns 400 Bad Request for invalid dates or sort_by field, 404 Not Found if ticker doesn't exist. Logs request/response at INFO level.
- `get_portfolio_performance_endpoint(...) -> PortfolioPerformanceResponse`: GET endpoint at `/portfolio/all/performance` that requires JWT authentication. Supports optional date filtering via query parameter: `end_date` (optional, ISO format YYYY-MM-DD). Verifies token via auth module, retrieves historical CompositePortfolio from application state (created via cloning at startup), retrieves PriceService from application state, uses portfolio's start_date property to determine start_date, parses end_date if provided (defaults to today if not provided), validates date range, calls portfolio_service.get_portfolio_performance() with historical portfolio, price_service, start_date, and end_date to fetch and transform history points, then returns PortfolioPerformanceResponse containing list of PortfolioHistoryPoint objects. Returns 400 Bad Request for invalid date format, 500 Internal Server Error if historical portfolio is not available. Logs request/response at INFO level.
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
- `get_asset_lots(composite: CompositePortfolio, ticker: str, price_service: PriceService, start_date: Optional[date] = None, end_date: Optional[date] = None, sort_by: Optional[str] = None, sort_order: Optional[str] = "asc") -> List[Lot]`: Retrieves all lots for a specific asset ticker from the wpm composite portfolio using `composite.get_asset_lots(ticker)` which returns a list of Lot objects. Filters lots by date range if `start_date` and/or `end_date` are provided (inclusive boundaries). Fetches current prices using `fetch_price_map(composite, price_service)` for unrealized_pnl and total_pnl calculations. Transforms wpm Lot objects into API Lot models, including transforming matched sells (which contain Trade objects and consumed_quantity) into MatchedSell API models. Extracts broker field from `wpm_lot.broker`. Calls `lot.get_realized_pnl()` to get realized P&L (no parameters). For each lot, gets current_price from price_map using lot's asset. Calls `lot.get_unrealized_pnl(current_price)` with current_price (None if price unavailable). Calls `lot.get_total_pnl(current_price)` with current_price (None if price unavailable). Applies sorting based on `sort_by` and `sort_order` parameters. Validates `sort_by` against Lot model fields (date, original_quantity, remaining_quantity, cost_basis, broker, realized_pnl, unrealized_pnl, total_pnl). Defaults to date ascending if no sort parameters provided. Logs function entry/exit, date filtering, and sorting at INFO level. Returns sorted list of API Lot objects filtered by date range.
- `get_portfolio_performance(portfolio: CompositePortfolio, price_service: PriceService, start_date: date, end_date: date) -> List[PortfolioHistoryPoint]`: Retrieves historical performance data from the wpm historical portfolio using `wpm.portfolio.get_historical_performance(portfolio, price_service, start_date, end_date)` which returns a list of PortfolioHistoryPoint objects. Transforms wpm PortfolioHistoryPoint objects (containing date, total_market_value, asset_positions) into API PortfolioHistoryPoint models. Extracts date and converts to ISO format string (YYYY-MM-DD), extracts total_market_value as float, extracts asset_positions as Dict[str, float] mapping ticker to position value. Logs function entry/exit and wpm library calls at INFO level. Returns list of API PortfolioHistoryPoint objects.

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
- `MatchedSell`: Model representing a matched sell with consumed quantity from a lot
  - `trade`: Trade (required)
  - `consumed_quantity`: float (required, ge=0)
- `Lot`: Model representing a single lot
  - Fields defined in Data Models section below
- `PortfolioAllResponse`: Response model for `/portfolio/all` endpoint
  - `positions`: Page[Position] (required)
  - `total_market_value`: Optional[float]
  - `total_cost_basis`: float (required)
  - `total_unrealized_gain_loss`: Optional[float]
- `PortfolioAssetTradesResponse`: Response model for `/portfolio/trades/<ticker>` endpoint
  - `trades`: Page[Trade] (required)
- `PortfolioAssetLotsResponse`: Response model for `/portfolio/lots/<ticker>` endpoint
  - `lots`: Page[Lot] (required)
- `PortfolioHistoryPoint`: Model representing a single portfolio history point
  - Fields defined in Data Models section below
- `PortfolioPerformanceResponse`: Response model for `/portfolio/all/performance` endpoint
  - `history_points`: List[PortfolioHistoryPoint] (required)
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

### wpm_backend/utils/startup.py
**Location**: `wpm_backend/utils/startup.py`

**Responsibilities**:
- Execute application startup logic
- Import CSV files and create composite portfolio
- Create and store cloned historical portfolio for performance endpoint
- Generate OpenAPI specification

**Key Functions**:
- `run_startup_logic(app: FastAPI, settings: Settings) -> None`: Executes application startup logic. Creates PriceService instance and stores it in `app.state.price_service`. Imports CSV files using `wpm.importer.import_csv_files(import_dir)` and stores the returned CompositePortfolio in `app.state.composite_portfolio`. Creates a cloned historical portfolio using `composite_portfolio.clone()` (with no date filters to preserve full history) and stores it in `app.state.historical_portfolio` for use by the performance endpoint. The cloned portfolio is reused for all subsequent performance API calls. Generates OpenAPI specification using `generate_openapi_spec(app)`. Logs all operations at INFO level.

**Artifacts**: None

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
- `InteractiveCLI.lots_command(ticker: str) -> None`: Calls GET `/portfolio/lots/{ticker}` endpoint via TestClient with stored JWT token in Authorization header. Displays the response (paginated lots) in formatted JSON using `json.dumps()` with `indent=2`. Handles authentication errors (401), not found errors (404), validation errors (400), and server errors (500) with user-friendly error messages.
- `InteractiveCLI.performance_command(end_date: str) -> None`: Calls GET `/portfolio/all/performance?end_date={end_date}` endpoint via TestClient with stored JWT token in Authorization header. Extracts history_points from response, displays only the last 10 history points in formatted JSON using `json.dumps()` with `indent=2`. Handles authentication errors (401), validation errors (400), and server errors (500) with user-friendly error messages.
- `InteractiveCLI.run() -> None`: Main interactive loop that prompts for commands, parses input, routes to appropriate command handlers, and continues until user enters `exit` or `quit`.
- `InteractiveCLI.show_help() -> None`: Displays list of available commands and their descriptions, including the `trades <ticker>`, `lots <ticker>`, and `performance YYYY-MM-DD` commands.

**Key Variables**:
- `InteractiveCLI.client`: TestClient instance for making API requests
- `InteractiveCLI.token`: JWT access token stored in memory during the session (None if not logged in)

**Command Structure**:
- `login`: Prompts for username and password, authenticates via `/login` endpoint, stores token
- `portfolio all`: Retrieves all portfolio positions via `/portfolio/all` endpoint, displays formatted JSON
- `trades <ticker>`: Retrieves all trades for the specified asset ticker via `/portfolio/trades/{ticker}` endpoint, displays formatted JSON
- `lots <ticker>`: Retrieves all lots for the specified asset ticker via `/portfolio/lots/{ticker}` endpoint, displays formatted JSON
- `performance YYYY-MM-DD`: Retrieves historical performance data via `/portfolio/all/performance?end_date=YYYY-MM-DD` endpoint, displays last 10 history points in formatted JSON
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

### MatchedSell
**Location**: `wpm_backend/models/portfolio.py`

Model representing a matched sell with consumed quantity from a lot.

**Fields**:
- `trade` (Trade, required)
  - Description: Sell trade that consumed from the lot
  - Source: `matched_sell.trade` from wpm matched sell object
  - Validation: Valid Trade object
  - Example: Trade(date="2024-02-15", ticker="AAPL", action="Sell", ...)
  
- `consumed_quantity` (float, required)
  - Description: Quantity consumed from the lot by this sell trade
  - Source: `matched_sell.consumed_quantity` from wpm matched sell object
  - Validation: Non-negative float, ge=0
  - Example: 25.0

### Lot
**Location**: `wpm_backend/models/portfolio.py`

Model representing a single lot for an asset. This model is based on the wpm library's Lot class.

**Fields**:
- `date` (str, required)
  - Description: Lot date in ISO format (YYYY-MM-DD)
  - Source: `lot.date` from wpm Lot object
  - Validation: ISO date string format
  - Example: "2024-01-15"
  
- `ticker` (str, required)
  - Description: Asset ticker symbol
  - Source: `lot.asset.ticker` or `lot.ticker` from wpm Lot object
  - Validation: Non-empty string
  - Example: "AAPL"
  
- `asset_type` (str, required)
  - Description: Type of asset (e.g., "Stock", "Crypto", "Bond")
  - Source: `lot.asset.asset_type` or `lot.asset_type` from wpm Lot object
  - Validation: Non-empty string
  - Example: "Stock"
  
- `original_quantity` (float, required)
  - Description: Original quantity in the lot
  - Source: `float(lot.original_quantity)` from wpm Lot object
  - Validation: Non-negative float, ge=0
  - Example: 100.0
  
- `remaining_quantity` (float, required)
  - Description: Remaining quantity in the lot
  - Source: `float(lot.remaining_quantity)` from wpm Lot object
  - Validation: Non-negative float, ge=0
  - Example: 75.0
  
- `cost_basis` (float, required)
  - Description: Cost basis of the lot in USD
  - Source: `float(lot.cost_basis)` from wpm Lot object
  - Validation: Non-negative float, ge=0
  - Example: 15000.0
  
- `matched_sells` (List[MatchedSell], optional, default=[])
  - Description: List of matched sells that consumed from this lot
  - Source: `lot.matched_sells` from wpm Lot object, transformed to MatchedSell API models
  - Validation: List of valid MatchedSell objects
  - Example: [MatchedSell(trade=Trade(...), consumed_quantity=25.0), ...]
  
- `broker` (str, required)
  - Description: Broker name from which the lot originated
  - Source: `lot.broker` from wpm Lot object
  - Validation: Non-empty string
  - Example: "IBKR"
  
- `realized_pnl` (float, optional)
  - Description: Realized profit or loss from matched sells in USD
  - Source: `lot.get_realized_pnl()` from wpm Lot object
  - Validation: Can be negative (loss) or positive (gain)
  - Example: 250.0 or -150.0
  
- `unrealized_pnl` (float, optional)
  - Description: Unrealized profit or loss on remaining quantity in USD
  - Source: `lot.get_unrealized_pnl(current_price)` from wpm Lot object (requires current_price)
  - Calculation: Called with current_price from price_map for the lot's asset
  - Validation: Can be negative (loss) or positive (gain), None if current_price unavailable
  - Example: 500.0 or None
  
- `total_pnl` (float, optional)
  - Description: Total profit or loss (realized + unrealized) in USD
  - Source: `lot.get_total_pnl(current_price)` from wpm Lot object (current_price may be None)
  - Calculation: Called with current_price from price_map for the lot's asset (None if unavailable)
  - Validation: Can be negative (loss) or positive (gain), None if current_price unavailable
  - Example: 750.0 or None

### PortfolioAssetLotsResponse
**Location**: `wpm_backend/models/portfolio.py`

Response model for the `/portfolio/lots/<ticker>` endpoint. Contains paginated lots for a specific asset ticker.

**Fields**:
- `lots` (Page[Lot], required)
  - Description: Paginated list of lots using fastapi-pagination Page structure
  - Contains: items, total, page, size, pages (see Page[Lot] structure below)
  - Validation: Valid Page[Lot] object
  - Example: Page[Lot] with items=[Lot(...), ...], total=10, page=1, size=20, pages=1

**Note**: The lots are filtered by the provided date range (if specified) and paginated according to the page and size parameters.

### PortfolioHistoryPoint
**Location**: `wpm_backend/models/portfolio.py`

Model representing a single portfolio history point (snapshot of portfolio state at a specific date). This model is based on the wpm library's `PortfolioHistoryPoint` class.

**Fields**:
- `date` (str, required)
  - Description: Date of the history point in ISO format (YYYY-MM-DD)
  - Source: `history_point.date` from wpm PortfolioHistoryPoint object
  - Validation: ISO date string format
  - Example: "2024-01-15"
  
- `total_market_value` (float, required)
  - Description: Total market value of the portfolio on this date in USD
  - Source: `history_point.total_market_value` from wpm PortfolioHistoryPoint object
  - Validation: Non-negative float, ge=0
  - Example: 25000.0
  
- `asset_positions` (Dict[str, float], required)
  - Description: Dictionary mapping ticker symbols to position values (quantity * price) on this date
  - Source: `history_point.asset_positions` from wpm PortfolioHistoryPoint object
  - Validation: Dictionary with string keys (ticker) and float values (position value)
  - Example: {"AAPL": 17550.0, "GOOGL": 7500.0}

### PortfolioPerformanceResponse
**Location**: `wpm_backend/models/portfolio.py`

Response model for the `/portfolio/all/performance` endpoint. Contains a list of portfolio history points representing day-to-day historical performance.

**Fields**:
- `history_points` (List[PortfolioHistoryPoint], required)
  - Description: List of portfolio history points, one for each day from start_date to end_date (inclusive)
  - Contains: PortfolioHistoryPoint objects ordered chronologically by date
  - Validation: List of valid PortfolioHistoryPoint objects
  - Example: [PortfolioHistoryPoint(date="2024-01-15", total_market_value=25000.0, asset_positions={...}), ...]

**Note**: The history points are not paginated or sorted - all points are returned as the frontend is expected to utilize all points. Points are ordered chronologically from start_date to end_date.

### Page[Lot]
**Location**: `fastapi_pagination.Page`

Paginated response structure used within PortfolioAssetLotsResponse. Uses fastapi-pagination library for standardized pagination.

**Fields**:
- `items` (List[Lot], required)
  - Description: List of lots in the current page
  - Validation: List of valid Lot objects
  - Example: [Lot(date="2024-01-15", ticker="AAPL", ...), ...]
  
- `total` (int, required)
  - Description: Total number of items across all pages
  - Validation: Non-negative integer
  - Example: 10
  
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
  - Example: 1

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
  - `wpm.portfolio.get_historical_performance(portfolio: Portfolio, price_service: PriceService, start_date: date, end_date: date) -> List[PortfolioHistoryPoint]`: Function to retrieve historical performance data from a portfolio
  - `wpm.models.PortfolioHistoryPoint`: Portfolio history point model with date (date), total_market_value (float), asset_positions (Dict[str, float])
  - `Portfolio.clone() -> Portfolio`: Method to create a deep copy (clone) of a portfolio
  - `Portfolio.start_date`: Property returning the earliest start_date (Optional[date])

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

## Development Workflow

This section defines the mandatory workflow for introducing changes, enhancements, or refactorings to the wpm-backend library. All development work must follow this process to ensure consistency, quality, and maintainability. This workflow can be referenced as "Development Workflow" or "See Development Workflow section in spec.md" for future work.

### Overview

The development workflow consists of four distinct phases that must be completed in order:

1. **Spec Definition**: Review and update the specification document
2. **Review WPM Library Changes** (if applicable): Review wpm library documentation for API compatibility
3. **Implement & Code Review**: Implement changes and conduct code review
4. **Test**: Ensure comprehensive test coverage

Each phase has specific requirements and deliverables that must be completed before proceeding to the next phase.

### Phase 1: Spec Definition

**When Required:**
- **Mandatory** for:
  - New APIs (new endpoints, new request/response models)
  - Modifications to existing APIs (endpoint changes, model updates, parameter additions)
- **Recommended** for:
  - Major refactorings that affect module structure or interfaces
  - Significant architectural changes

**Requirements:**

1. **Review Current Spec**: 
   - Read through relevant sections of `SPEC/spec.md` to understand current conventions and patterns
   - Review existing module requirements, data models, and API endpoint specifications
   - Understand the package structure and module organization

2. **Update Specification**:
   - Add or modify sections following existing spec conventions:
     - **Module Requirements**: Document new or modified modules in the "Module Requirements" section, following the format used for existing modules (Location, Responsibilities, Key Functions, Key Variables, Artifacts)
     - **Data Models**: Add or update Pydantic models in the "Data Models" section, documenting all fields with descriptions, validation rules, sources, and examples
     - **API Endpoints**: Document new or modified endpoints in the relevant module's "Key Functions" section, including HTTP method, path, parameters, response models, and behavior
   - Maintain consistency with existing documentation style and format

3. **Break Down Implementation**:
   - Document required data structures (Pydantic models, internal data types)
   - Identify dependencies (external libraries, internal modules, wpm library components)
   - Outline the logic flow and business rules
   - Specify how the feature integrates with the existing package structure
   - Reference existing patterns and conventions from the spec

4. **Document Integration Points**:
   - Specify how new code interacts with existing modules
   - Document any changes to existing interfaces or contracts
   - Identify affected modules and their update requirements

**Deliverable**: Updated `SPEC/spec.md` with complete documentation of the proposed changes, following existing conventions and format.

### Phase 2: Review WPM Library Changes (if applicable)

**When Required:**
- When changes involve integration with the wpm library
- When the wpm library has been updated or upgraded
- When implementing features that depend on wpm library APIs

**Requirements:**

1. **Review WPM Library Documentation**:
   - Review the wpm library documentation located at `wpm/docs/api.md` (markdown format, in the installed wheel package at `.venv/lib/python3.14/site-packages/wpm/docs/api.md`)
   - Understand the API contracts, data structures, and behavior of relevant wpm library components
   - Identify any breaking changes or deprecated APIs
   - Note version requirements or compatibility constraints
   - Note that wpm library models are dataclasses with well-defined attributes:
     - `Asset`: `ticker`, `asset_type` (frozen dataclass)
     - `Trade`: `date`, `asset`, `action`, `order_instruction`, `quantity`, `price`, `broker` (dataclass)
     - `Position`: `asset`, `quantity`, `cost_basis`, `cost_basis_method` (dataclass)
     - `Lot`: `purchase_date`, `asset`, `original_quantity`, `remaining_quantity`, `cost_basis`, `matched_sells` (dataclass)

2. **Verify API Compatibility**:
   - Ensure backend implementation aligns with wpm library API contracts
   - Verify data type compatibility (e.g., Decimal vs float, date formats)
   - Check that method signatures and return types match expectations
   - Understand error handling and exception behavior

3. **Document Dependencies**:
   - Update the spec to document wpm library dependencies
   - Note any assumptions about wpm library behavior
   - Document version requirements or compatibility notes
   - Update the "External Dependencies" section if new wpm library components are used

4. **Identify Integration Points**:
   - Map wpm library calls to backend service functions
   - Document data transformation requirements (wpm types to API models)
   - Identify any abstraction layers needed

**Deliverable**: Documentation of wpm library dependencies and integration approach, with any necessary spec updates.

### Phase 3: Implement & Code Review

**Requirements:**

1. **Implementation**:
   - Follow the spec breakdown from Phase 1
   - Create or update required classes, methods, and modules as specified
   - Implement data structures, business logic, and API endpoints according to the spec
   - Follow existing code patterns and conventions
   - Ensure proper error handling and logging

2. **Code Review (Distinct Pass)**:
   - Conduct a separate code review pass after implementation is complete
   - Review must verify adherence to clean coding principles defined in `SPEC/clean_coding_principles.md`
   - Use the code review checklist below

**Code Review Checklist:**

Verify compliance with clean coding principles:

- [ ] **Abstraction and Delegation**:
  - [ ] Route handlers delegate to service layer functions (no business logic in routes)
  - [ ] Service layer abstracts away external library (wpm) implementation details
  - [ ] Dependencies are injected via FastAPI `Depends()` rather than accessed as globals
  - [ ] Internal implementation details are not exposed beyond module boundaries

- [ ] **Control Flow**:
  - [ ] No more than 2 levels of nested conditionals
  - [ ] Guard clauses are used to flatten control flow (early returns/continues)
  - [ ] Complex conditional logic is abstracted into well-named helper methods or classes

- [ ] **Imports**:
  - [ ] All imports are at module level (no inline imports)
  - [ ] Any inline imports are documented with justification for circular import avoidance

- [ ] **Type Safety**:
  - [ ] `hasattr()` is avoided unless absolutely necessary (with documented justification)
  - [ ] Interfaces are defined using abstract base classes, protocols, or explicit type checking
  - [ ] Pydantic models are used for request/response validation

- [ ] **FastAPI-Specific Patterns**:
  - [ ] Dependencies use `Depends()` for injection rather than global state
  - [ ] Route handlers are thin and delegate business logic to service layer
  - [ ] HTTPException is raised for error cases rather than returning error dicts
  - [ ] Response models are specified using `response_model` parameter

- [ ] **Code Quality**:
  - [ ] Functions and classes have clear, descriptive names
  - [ ] Code is well-documented with docstrings where appropriate
  - [ ] Logging is implemented at appropriate levels (INFO for external calls, DEBUG for internal details)

**Deliverable**: Implemented code that passes code review and adheres to all clean coding principles.

### Phase 4: Test

**Requirements:**

1. **Test Coverage**:
   - Ensure all new code is covered by tests
   - Ensure all modified code has updated tests
   - Maintain minimum 80% code coverage requirement (as specified in the Testing section)
   - Write tests for:
     - New functions and methods
     - Modified functions and methods
     - Edge cases and error conditions
     - Integration points with wpm library
     - API endpoints (request/response validation, error handling)

2. **Test Structure**:
   - Follow existing test patterns in the `tests/` directory
   - Use pytest fixtures from `conftest.py` where applicable
   - Write both unit tests (isolated function testing) and integration tests (API endpoint testing)
   - Mock wpm library calls appropriately to avoid dependencies on actual CSV files

3. **Test Execution**:
   - Run the full test suite: `pytest --cov=wpm_backend --cov-report=html --cov-report=term`
   - Verify all tests pass (no failures or errors)
   - Verify code coverage meets or exceeds 80% threshold
   - Review coverage report to identify any untested code paths

4. **Test Quality**:
   - Tests should be clear, readable, and maintainable
   - Test names should clearly describe what is being tested
   - Tests should be independent and not rely on execution order
   - Use appropriate assertions and error messages

**Deliverable**: Complete test suite with all tests passing and minimum 80% code coverage achieved.

### Workflow Summary

For quick reference, the workflow phases are:

1. **Spec Definition** → Update `SPEC/spec.md` with complete feature documentation
2. **Review WPM Library Changes** (if applicable) → Review `docs/api.md` and document dependencies
3. **Implement & Code Review** → Implement following spec, then review against clean coding principles
4. **Test** → Write tests, achieve 80%+ coverage, verify all tests pass

**Important Notes:**
- Spec updates are **mandatory** for API changes (new or modified endpoints)
- Spec updates are **recommended** for major refactorings
- Code review is a **distinct phase** - do not skip or combine with implementation
- Testing must be comprehensive - aim for 100% coverage of new/changed code, with overall project coverage at 80%+
- All phases must be completed before considering a change ready for merge or deployment

**References:**
- See `SPEC/clean_coding_principles.md` for detailed coding standards
- See "Testing" section in this spec for test structure and coverage requirements
- See "Module Requirements" section for documentation format conventions

