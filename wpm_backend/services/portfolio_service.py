"""Business logic for portfolio operations, wraps wpm library calls."""

import logging
from datetime import date
from typing import List, Optional

from wpm.models import Asset, Position as WPMPosition, Trade as WPMTrade
from wpm.portfolio import CompositePortfolio, fetch_price_map
from wpm.pricing import PriceService

from wpm_backend.models.portfolio import Position, Trade

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

# Valid sortable fields for Trade model
VALID_TRADE_SORT_FIELDS = {
    "date",
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


def get_asset_trades(
    composite: CompositePortfolio,
    ticker: str,
    price_service: PriceService,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
) -> List[Trade]:
    """
    Retrieve all trades for a specific asset ticker and transform to API models.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol to retrieve trades for
        price_service: PriceService instance for fetching current prices
        start_date: Optional start date for filtering trades (inclusive)
        end_date: Optional end date for filtering trades (inclusive)
        sort_by: Field name to sort by (default: None, which defaults to "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        Sorted list of Trade API models, filtered by date range if provided

    Raises:
        ValueError: If ticker is not found or invalid, or if sort_by is not a valid Trade field
    """
    logger.info(f"Retrieving trades for ticker: {ticker}, start_date={start_date}, end_date={end_date}, sort_by={sort_by}, sort_order={sort_order}")

    # Get trades from composite portfolio
    try:
        wpm_trades = composite.get_asset_trades(ticker)
        logger.info(f"Retrieved {len(wpm_trades)} trades for ticker {ticker}")
    except Exception as e:
        logger.error(f"Error retrieving trades for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve trades for ticker {ticker}: {e}")

    # Filter by date range if provided
    filtered_trades = []
    for wpm_trade in wpm_trades:
        try:
            # Parse trade date (assuming it's a date object, datetime object, or string in YYYY-MM-DD format)
            trade_date = wpm_trade.date
            if isinstance(trade_date, str):
                trade_date = date.fromisoformat(trade_date)
            elif isinstance(trade_date, date):
                # Already a date object, use as-is
                pass
            elif hasattr(trade_date, 'date'):
                # datetime object, extract date
                trade_date = trade_date.date()
            else:
                # Try to convert to string and parse
                trade_date = date.fromisoformat(str(trade_date))

            # Apply date filtering
            if start_date is not None and trade_date < start_date:
                continue
            if end_date is not None and trade_date > end_date:
                continue

            filtered_trades.append(wpm_trade)
        except Exception as e:
            logger.warning(f"Error processing trade date for ticker {ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Filtered to {len(filtered_trades)} trades after date filtering")

    # Fetch current prices for the asset (needed for buy trades)
    market_price = None
    try:
        logger.info(f"Fetching current price for asset {ticker}")
        full_price_map = fetch_price_map(composite, price_service)
        # Find the matching asset in the price map by ticker
        for price_asset, price_value in full_price_map.items():
            if price_asset.ticker == ticker:
                market_price = price_value
                break
        logger.info(f"Fetched price for {ticker}: {market_price}")
    except Exception as e:
        logger.warning(f"Error fetching price for asset {ticker}: {e}", exc_info=True)

    # Transform wpm Trade objects to API Trade models
    api_trades = []
    for wpm_trade in filtered_trades:
        try:
            # Extract trade fields
            trade_date = wpm_trade.date
            if isinstance(trade_date, str):
                trade_date_str = trade_date
            elif hasattr(trade_date, 'isoformat'):
                trade_date_str = trade_date.isoformat()
            elif hasattr(trade_date, 'date'):
                trade_date_str = trade_date.date().isoformat()
            else:
                trade_date_str = str(trade_date)

            ticker_value = getattr(wpm_trade, 'ticker', ticker)
            asset_type_value = getattr(wpm_trade, 'asset_type', 'Stock')
            if hasattr(wpm_trade, 'asset'):
                asset_type_value = wpm_trade.asset.asset_type
                ticker_value = wpm_trade.asset.ticker

            order_instruction = getattr(wpm_trade, 'order_instruction', 'buy')
            quantity = float(getattr(wpm_trade, 'quantity', 0))
            price = float(getattr(wpm_trade, 'price', 0))

            # Determine if this is a buy trade
            # The CSV has separate "Action" (Buy/Sell) and "Order Instruction" (Limit/Market) columns
            # Check for an 'action' field first (from CSV "Action" column), fall back to order_instruction
            action = getattr(wpm_trade, 'action', None)
            is_buy = False
            if action is not None:
                # Use action field if available (from CSV "Action" column: "Buy" or "Sell")
                is_buy = action.lower() == "buy"
                # Normalize action to "Buy" or "Sell" (capitalized)
                action = "Buy" if is_buy else "Sell"
            else:
                # Fall back to order_instruction for backward compatibility
                # order_instruction can be "buy", "sell", "Limit", "Market", etc.
                # If it's explicitly "sell", it's a sell; otherwise assume it's a buy
                is_buy = order_instruction.lower() != "sell"
                # Derive action from is_buy when action field is not available
                action = "Buy" if is_buy else "Sell"

            # Initialize optional fields
            cost_basis = None
            unrealized_profit_loss = None

            # For buy trades, calculate cost_basis, market_price, and unrealized_profit_loss
            trade_market_price = None
            if is_buy:
                # Calculate cost basis
                cost_basis = quantity * price

                # Use the fetched market price (already retrieved above, from outer scope)
                trade_market_price = market_price

                # Calculate unrealized profit/loss if market price is available
                if trade_market_price is not None:
                    unrealized_profit_loss = (trade_market_price - price) * quantity

            # Create API Trade model
            api_trade = Trade(
                date=trade_date_str,
                ticker=ticker_value,
                asset_type=asset_type_value,
                action=action,
                order_instruction=order_instruction,
                quantity=quantity,
                price=price,
                cost_basis=cost_basis,
                market_price=trade_market_price if is_buy else None,
                unrealized_profit_loss=unrealized_profit_loss,
            )
            api_trades.append(api_trade)
        except Exception as e:
            logger.error(f"Error transforming trade for ticker {ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Transformed {len(api_trades)} trades to API models")

    # Apply sorting if requested
    if sort_by is None:
        sort_by = "date"
    
    # Validate sort_by field
    if sort_by not in VALID_TRADE_SORT_FIELDS:
        raise ValueError(f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_TRADE_SORT_FIELDS)}")
    
    # Normalize sort_order
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"
    
    # Sort the trades
    reverse = sort_order == "desc"
    
    def get_sort_key(trade: Trade):
        """Get sort key for a trade, handling date string parsing."""
        value = getattr(trade, sort_by, None)
        
        # For date field, parse ISO format string to date object for proper sorting
        if sort_by == "date" and value is not None:
            try:
                return date.fromisoformat(value)
            except (ValueError, AttributeError):
                # If parsing fails, use string comparison as fallback
                return value
        
        return value
    
    sorted_trades = sorted(api_trades, key=get_sort_key, reverse=reverse)
    
    logger.info(f"Sorted {len(sorted_trades)} trades by {sort_by} ({sort_order})")
    return sorted_trades

