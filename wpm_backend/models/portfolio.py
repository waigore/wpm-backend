"""Pydantic models for portfolio-related data structures."""

from typing import Any, Dict, Optional
from fastapi_pagination import Page
from pydantic import BaseModel, Field, computed_field


class Position(BaseModel):
    """Model representing a single portfolio position."""

    ticker: str = Field(..., description="Stock ticker symbol or asset identifier")
    asset_type: str = Field(..., description="Type of asset (e.g., 'Stock', 'Crypto', 'Bond')")
    quantity: float = Field(..., ge=0, description="Number of shares/units held")
    average_price: float = Field(..., ge=0, description="Average purchase price per share/unit")
    cost_basis: float = Field(..., ge=0, description="Total cost basis of the position in USD")
    cost_basis_method: str = Field(..., description="Method used to calculate cost basis ('fifo' or 'average')")
    current_price: Optional[float] = Field(
        None, ge=0, description="Current market price per share/unit in USD"
    )
    market_value: Optional[float] = Field(
        None, description="Current total market value of the position in USD"
    )
    unrealized_gain_loss: Optional[float] = Field(
        None, description="Unrealized gain or loss on the position in USD"
    )
    allocation_percentage: Optional[float] = Field(
        None, ge=0, le=100, description="Percentage allocation of this asset in the portfolio (0.00-100.00)"
    )


class PortfolioAllResponse(BaseModel):
    """Response model for /portfolio/all endpoint with paginated positions and portfolio totals."""

    positions: Page[Position] = Field(..., description="Paginated list of positions")
    total_market_value: Optional[float] = Field(
        None, description="Total market value across all positions in USD"
    )
    total_cost_basis: float = Field(..., ge=0, description="Total cost basis across all positions in USD")
    total_unrealized_gain_loss: Optional[float] = Field(
        None, description="Total unrealized gain or loss across all positions in USD"
    )


class Trade(BaseModel):
    """Model representing a single trade."""

    date: str = Field(..., description="Trade date (ISO format YYYY-MM-DD)")
    ticker: str = Field(..., description="Asset ticker symbol")
    asset_type: str = Field(..., description="Type of asset (e.g., 'Stock', 'Crypto', 'Bond')")
    action: str = Field(..., description="Trade action from CSV 'Action' column: 'Buy' or 'Sell'")
    order_instruction: str = Field(..., description="Trade instruction: 'buy' or 'sell'")
    quantity: float = Field(..., description="Number of shares/units")
    price: float = Field(..., ge=0, description="Price per share/unit")
    broker: str = Field(..., description="Broker name from which the trade originated")


class PortfolioAssetTradesResponse(BaseModel):
    """Response model for /portfolio/trades/<ticker> endpoint with paginated trades."""

    trades: Page[Trade] = Field(..., description="Paginated list of trades")


class PortfolioResponse(BaseModel):
    """Response model for portfolio endpoints."""

    positions: list[Position] = Field(..., description="List of all positions in the composite portfolio")

    @computed_field
    @property
    def total_count(self) -> int:
        """Total number of positions."""
        return len(self.positions)


class MatchedSell(BaseModel):
    """Model representing a matched sell with consumed quantity from a lot."""

    trade: Trade = Field(..., description="Sell trade that consumed from the lot")
    consumed_quantity: float = Field(..., ge=0, description="Quantity consumed from the lot by this sell trade")


class Lot(BaseModel):
    """Model representing a single lot."""

    date: str = Field(..., description="Lot date (ISO format YYYY-MM-DD)")
    ticker: str = Field(..., description="Asset ticker symbol")
    asset_type: str = Field(..., description="Type of asset (e.g., 'Stock', 'Crypto', 'Bond')")
    original_quantity: float = Field(..., ge=0, description="Original quantity in the lot")
    remaining_quantity: float = Field(..., ge=0, description="Remaining quantity in the lot")
    cost_basis: float = Field(..., ge=0, description="Cost basis of the lot in USD")
    matched_sells: list[MatchedSell] = Field(
        default_factory=list, description="List of matched sells that consumed from this lot"
    )
    broker: str = Field(..., description="Broker name from which the lot originated")
    realized_pnl: Optional[float] = Field(None, description="Realized profit or loss from matched sells in USD")
    unrealized_pnl: Optional[float] = Field(
        None, description="Unrealized profit or loss on remaining quantity in USD"
    )
    total_pnl: Optional[float] = Field(None, description="Total profit or loss (realized + unrealized) in USD")


class PortfolioAssetLotsResponse(BaseModel):
    """Response model for /portfolio/lots/<ticker> endpoint with paginated lots."""

    lots: Page[Lot] = Field(..., description="Paginated list of lots")


class PortfolioHistoryPoint(BaseModel):
    """Model representing a single portfolio history point."""

    date: str = Field(..., description="Date of the history point (ISO format YYYY-MM-DD)")
    total_market_value: float = Field(..., ge=0, description="Total market value of the portfolio on this date in USD")
    asset_positions: Dict[str, float] = Field(..., description="Dictionary mapping ticker symbols to position values (quantity * price) on this date")
    prices: Dict[str, float] = Field(..., description="Dictionary mapping ticker symbols to asset prices on this date in USD")


class PortfolioPerformanceResponse(BaseModel):
    """Response model for /portfolio/all/performance endpoint with historical performance data."""

    history_points: list[PortfolioHistoryPoint] = Field(..., description="List of portfolio history points, one for each day from start_date to end_date (inclusive)")


class AssetMetadataResponse(BaseModel):
    """Response model for /asset/metadata/{ticker} endpoint with asset metadata."""

    ticker: str = Field(..., description="Asset ticker symbol")
    metadata: Optional[Dict[str, Any]] = Field(..., description="Metadata dictionary from wpm library, or None if retrieval fails")


class AssetMetadataAllResponse(BaseModel):
    """Response model for /asset/metadata/all endpoint with metadata for all tickers."""

    metadata: Dict[str, Optional[Dict[str, Any]]] = Field(..., description="Dictionary mapping ticker to metadata dict (None if retrieval fails for that ticker)")

