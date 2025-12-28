"""Business logic for portfolio operations, wraps wpm library calls."""

import logging
from typing import List, Optional

from wpm.models import Asset, Position as WPMPosition
from wpm.portfolio import CompositePortfolio, fetch_price_map
from wpm.pricing import PriceService

from wpm_backend.models.portfolio import Position

logger = logging.getLogger(__name__)

# Valid sortable fields for Position model
VALID_SORT_FIELDS = {
    "ticker",
    "asset_type",
    "quantity",
    "average_price",
    "cost_basis",
    "cost_basis_method",
    "current_price",
    "market_value",
    "unrealized_gain_loss",
}


def get_all_positions(
    composite: CompositePortfolio,
    price_service: PriceService,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
) -> List[Position]:
    """
    Retrieve all positions from the wpm composite portfolio and transform to API models.

    Args:
        composite: CompositePortfolio instance from wpm library
        price_service: PriceService instance for fetching current prices
        sort_by: Field name to sort by (default: None, which defaults to "ticker")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        Sorted list of Position API models

    Raises:
        ValueError: If sort_by is not a valid Position field
    """
    logger.info("Retrieving all positions from composite portfolio")

    # Get positions from composite portfolio
    positions_dict = composite.get_positions()
    logger.info(f"Retrieved {len(positions_dict)} positions from composite portfolio")

    # Fetch current prices
    logger.info("Fetching current prices for all assets")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Transform wpm Position objects to API Position models
    api_positions = []
    for asset, wpm_position in positions_dict.items():
        try:
            # Get current price (may be None)
            current_price = price_map.get(asset)

            # Calculate average price from cost_basis and quantity
            quantity_float = float(wpm_position.quantity)
            average_price = (
                float(wpm_position.cost_basis) / quantity_float if quantity_float > 0 else 0.0
            )

            # Calculate market_value if price is available
            market_value = None
            if current_price is not None:
                market_value = quantity_float * current_price

            # Calculate unrealized_gain_loss if market_value is available
            unrealized_gain_loss = None
            if market_value is not None:
                unrealized_gain_loss = market_value - float(wpm_position.cost_basis)

            # Create API Position model
            api_position = Position(
                ticker=asset.ticker,
                asset_type=asset.asset_type,
                quantity=quantity_float,
                average_price=average_price,
                cost_basis=float(wpm_position.cost_basis),
                cost_basis_method=wpm_position.cost_basis_method,
                current_price=current_price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss,
            )
            api_positions.append(api_position)
        except Exception as e:
            logger.error(f"Error transforming position for asset {asset.ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Transformed {len(api_positions)} positions to API models")

    # Apply sorting if requested
    if sort_by is None:
        sort_by = "ticker"
    
    # Validate sort_by field
    if sort_by not in VALID_SORT_FIELDS:
        raise ValueError(f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_SORT_FIELDS)}")
    
    # Normalize sort_order
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"
    
    # Sort the positions
    reverse = sort_order == "desc"
    
    def get_sort_key(position: Position):
        """Get sort key for a position, handling None values."""
        value = getattr(position, sort_by, None)
        
        # Handle None values: None sorts to beginning for asc, end for desc
        # Use tuple (is_none_flag, value) where:
        # - For ascending: (0, sentinel) for None, (1, value) for non-None
        #   This makes None come first since (0, ...) < (1, ...)
        # - For descending: (1, sentinel) for None, (0, value) for non-None
        #   With reverse=True, (1, ...) > (0, ...), so None comes last
        if value is None:
            # Use a sentinel value that won't interfere with actual values
            sentinel = float('-inf') if not reverse else float('inf')
            return (1 if reverse else 0, sentinel)
        
        # For non-None values
        return (0 if reverse else 1, value)
    
    sorted_positions = sorted(api_positions, key=get_sort_key, reverse=reverse)
    
    logger.info(f"Sorted {len(sorted_positions)} positions by {sort_by} ({sort_order})")
    return sorted_positions

