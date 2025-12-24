"""Business logic for portfolio operations, wraps wpm library calls."""

import logging
from typing import List

from wpm.models import Asset, Position as WPMPosition
from wpm.portfolio import CompositePortfolio, fetch_price_map
from wpm.pricing import PriceService

from wpm_backend.models.portfolio import Position

logger = logging.getLogger(__name__)


def get_all_positions(
    composite: CompositePortfolio, price_service: PriceService
) -> List[Position]:
    """
    Retrieve all positions from the wpm composite portfolio and transform to API models.

    Args:
        composite: CompositePortfolio instance from wpm library
        price_service: PriceService instance for fetching current prices

    Returns:
        List of Position API models
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
    return api_positions

