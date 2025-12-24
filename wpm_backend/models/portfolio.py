"""Pydantic models for portfolio-related data structures."""

from typing import Optional
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


class PortfolioResponse(BaseModel):
    """Response model for portfolio endpoints."""

    positions: list[Position] = Field(..., description="List of all positions in the composite portfolio")

    @computed_field
    @property
    def total_count(self) -> int:
        """Total number of positions."""
        return len(self.positions)

