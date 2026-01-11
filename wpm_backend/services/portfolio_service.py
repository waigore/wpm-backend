"""Business logic for portfolio operations, wraps wpm library calls."""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from wpm.models import Asset, Position as WPMPosition, Trade as WPMTrade
from wpm.portfolio import CompositePortfolio, fetch_price_map, get_historical_performance
from wpm.pricing import PriceService

from wpm_backend.models.portfolio import Lot, MatchedSell, PortfolioHistoryPoint, Position, Trade

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

# Valid sortable fields for Lot model
VALID_LOT_SORT_FIELDS = {
    "date",
    "original_quantity",
    "remaining_quantity",
    "cost_basis",
    "broker",
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
}


def _parse_date_to_date_object(date_value) -> date:
    """
    Parse a date value to a date object.
    
    Handles date objects, datetime objects, and ISO format strings.
    This is a helper function to work with external library types that may
    return dates in various formats.
    
    Args:
        date_value: Date value that may be a date, datetime, or ISO string
        
    Returns:
        date object
        
    Raises:
        ValueError: If date_value cannot be parsed to a date
    """
    if isinstance(date_value, date):
        return date_value
    if isinstance(date_value, datetime):
        return date_value.date()
    if isinstance(date_value, str):
        return date.fromisoformat(date_value)
    # Try to convert to string and parse as last resort
    # This handles cases where external library returns custom date-like objects
    return date.fromisoformat(str(date_value))


def _parse_date_to_iso_string(date_value) -> str:
    """
    Parse a date value to an ISO format string (YYYY-MM-DD).
    
    Handles date objects, datetime objects, and ISO format strings.
    This is a helper function to work with external library types that may
    return dates in various formats.
    
    Args:
        date_value: Date value that may be a date, datetime, or ISO string
        
    Returns:
        ISO format date string (YYYY-MM-DD)
    """
    if isinstance(date_value, str):
        # Validate it's a valid ISO format by parsing it
        date.fromisoformat(date_value)
        return date_value
    if isinstance(date_value, date):
        return date_value.isoformat()
    if isinstance(date_value, datetime):
        return date_value.date().isoformat()
    # For other types, try to get isoformat method if available
    # This handles cases where external library returns custom date-like objects
    # NOTE: hasattr is necessary here because we're working with external library types
    # that may return custom date-like objects without a known base class or protocol.
    # This is a legitimate use case as the external library types are not under our control.
    if hasattr(date_value, 'isoformat'):
        return date_value.isoformat()
    if hasattr(date_value, 'date'):
        return date_value.date().isoformat()
    # Last resort: convert to string
    return str(date_value)


def _determine_trade_action(wpm_trade, order_instruction: str) -> str:
    """
    Determine the trade action (Buy or Sell) from a wpm trade object.
    
    The CSV has separate "Action" (Buy/Sell) and "Order Instruction" (Limit/Market) columns.
    This function checks for an 'action' field first, then falls back to order_instruction.
    
    Args:
        wpm_trade: WPM trade object with an 'action' attribute
        order_instruction: Order instruction string (e.g., "buy", "sell", "Limit", "Market")
        
    Returns:
        Normalized action string: "Buy" or "Sell"
    """
    # Use action field (from CSV "Action" column: "Buy" or "Sell")
    action = wpm_trade.action
    if action is not None:
        # Use action field if available (from CSV "Action" column: "Buy" or "Sell")
        is_buy = action.lower() == "buy"
        # Normalize action to "Buy" or "Sell" (capitalized)
        return "Buy" if is_buy else "Sell"
    else:
        # Fall back to order_instruction for backward compatibility
        # order_instruction can be "buy", "sell", "Limit", "Market", etc.
        # If it's explicitly "sell", it's a sell; otherwise assume it's a buy
        is_buy = order_instruction.lower() != "sell"
        # Derive action from is_buy when action field is not available
        return "Buy" if is_buy else "Sell"


def _extract_ticker_and_asset_type_from_trade(wpm_trade, default_ticker: str) -> tuple[str, str]:
    """
    Extract ticker and asset_type from a wpm trade object.
    
    Args:
        wpm_trade: WPM trade object with an asset attribute
        default_ticker: Default ticker value to use if not found (unused, kept for compatibility)
        
    Returns:
        Tuple of (ticker, asset_type) as strings
    """
    # Trade objects have an asset attribute (Asset dataclass)
    wpm_asset = wpm_trade.asset
    ticker_value = wpm_asset.ticker
    asset_type_value = wpm_asset.asset_type
    
    return ticker_value, asset_type_value


def _get_lot_date(wpm_lot) -> Optional[date]:
    """
    Extract date from a wpm lot object.
    
    Args:
        wpm_lot: WPM lot object with purchase_date attribute
        
    Returns:
        date object if found, None otherwise
    """
    purchase_date = wpm_lot.purchase_date
    if purchase_date is not None:
        try:
            return _parse_date_to_date_object(purchase_date)
        except Exception:
            pass
    
    return None


def _extract_ticker_and_asset_type_from_lot(wpm_lot, default_ticker: str) -> tuple[str, str]:
    """
    Extract ticker and asset_type from a wpm lot object.
    
    Args:
        wpm_lot: WPM lot object with an asset attribute
        default_ticker: Default ticker value to use if not found (unused, kept for compatibility)
        
    Returns:
        Tuple of (ticker, asset_type) as strings
    """
    # Lot objects have an asset attribute (Asset dataclass)
    wpm_asset = wpm_lot.asset
    ticker_value = wpm_asset.ticker
    asset_type_value = wpm_asset.asset_type
    
    return ticker_value, asset_type_value


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
        # Direct attribute access for sort_by field
        if sort_by == "ticker":
            value = position.ticker
        elif sort_by == "asset_type":
            value = position.asset_type
        elif sort_by == "quantity":
            value = position.quantity
        elif sort_by == "average_price":
            value = position.average_price
        elif sort_by == "cost_basis":
            value = position.cost_basis
        elif sort_by == "cost_basis_method":
            value = position.cost_basis_method
        elif sort_by == "current_price":
            value = position.current_price
        elif sort_by == "market_value":
            value = position.market_value
        elif sort_by == "unrealized_gain_loss":
            value = position.unrealized_gain_loss
        else:
            value = None
        
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
            # Parse trade date using helper function
            trade_date = _parse_date_to_date_object(wpm_trade.date)

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

    # Transform wpm Trade objects to API Trade models
    api_trades = []
    for wpm_trade in filtered_trades:
        try:
            # Extract trade date using helper function
            trade_date_str = _parse_date_to_iso_string(wpm_trade.date)

            # Extract ticker and asset_type using helper function
            ticker_value, asset_type_value = _extract_ticker_and_asset_type_from_trade(wpm_trade, ticker)

            order_instruction = wpm_trade.order_instruction
            quantity = float(wpm_trade.quantity)
            price = float(wpm_trade.price)
            broker = wpm_trade.broker

            # Determine trade action using helper function
            action = _determine_trade_action(wpm_trade, order_instruction)

            # Create API Trade model
            api_trade = Trade(
                date=trade_date_str,
                ticker=ticker_value,
                asset_type=asset_type_value,
                action=action,
                order_instruction=order_instruction,
                quantity=quantity,
                price=price,
                broker=broker,
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
        # Direct attribute access for sort_by field
        if sort_by == "date":
            value = trade.date
        else:
            # Only "date" is a valid sort field for Trade
            value = None
        
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


def get_asset_lots(
    composite: CompositePortfolio,
    ticker: str,
    price_service: PriceService,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
) -> List[Lot]:
    """
    Retrieve all lots for a specific asset ticker and transform to API models.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol to retrieve lots for
        price_service: PriceService instance for fetching current prices
        start_date: Optional start date for filtering lots (inclusive)
        end_date: Optional end date for filtering lots (inclusive)
        sort_by: Field name to sort by (default: None, which defaults to "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        Sorted list of Lot API models, filtered by date range if provided

    Raises:
        ValueError: If ticker is not found or invalid, or if sort_by is not a valid Lot field
    """
    logger.info(f"Retrieving lots for ticker: {ticker}, start_date={start_date}, end_date={end_date}, sort_by={sort_by}, sort_order={sort_order}")

    # Get lots from composite portfolio
    try:
        wpm_lots = composite.get_asset_lots(ticker)
        logger.info(f"Retrieved {len(wpm_lots)} lots for ticker {ticker}")
    except Exception as e:
        logger.error(f"Error retrieving lots for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve lots for ticker {ticker}: {e}")

    # Fetch current prices for P&L calculations
    logger.info("Fetching current prices for P&L calculations")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Filter by date range if provided
    filtered_lots = []
    for wpm_lot in wpm_lots:
        try:
            # Get lot date using helper function
            lot_date = _get_lot_date(wpm_lot)
            if lot_date is None:
                # If no date found, skip date filtering but still include the lot
                filtered_lots.append(wpm_lot)
                continue

            # Apply date filtering
            if start_date is not None and lot_date < start_date:
                continue
            if end_date is not None and lot_date > end_date:
                continue

            filtered_lots.append(wpm_lot)
        except Exception as e:
            logger.warning(f"Error processing lot date for ticker {ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Filtered to {len(filtered_lots)} lots after date filtering")

    # Transform wpm Lot objects to API Lot models
    api_lots = []
    for wpm_lot in filtered_lots:
        try:
            # Extract lot date using helper function
            lot_date_obj = _get_lot_date(wpm_lot)
            if lot_date_obj is None:
                # If no date found, skip this lot (date is required by Lot model)
                logger.warning(f"Lot for ticker {ticker} has no date, skipping")
                continue
            lot_date_str = lot_date_obj.isoformat()

            # Extract ticker and asset_type using helper function
            ticker_value, asset_type_value = _extract_ticker_and_asset_type_from_lot(wpm_lot, ticker)

            # Extract lot quantities and cost basis
            original_quantity = float(wpm_lot.original_quantity)
            remaining_quantity = float(wpm_lot.remaining_quantity)
            cost_basis = float(wpm_lot.cost_basis)

            # Extract broker
            broker = wpm_lot.broker

            # Calculate P&L using wpm library methods
            realized_pnl = wpm_lot.get_realized_pnl()

            # Get current price for this lot's asset
            current_price = price_map.get(wpm_lot.asset)

            # Calculate unrealized P&L (only if price available)
            if current_price is not None:
                unrealized_pnl = wpm_lot.get_unrealized_pnl(current_price)
            else:
                unrealized_pnl = None

            # Calculate total P&L (handles None current_price)
            total_pnl = wpm_lot.get_total_pnl(current_price)

            # Transform matched sells
            matched_sells = []
            wpm_matched_sells = wpm_lot.matched_sells
            for wpm_matched_sell in wpm_matched_sells:
                try:
                    # Handle matched_sell as tuple: (trade, consumed_quantity) or (consumed_quantity, trade)
                    if isinstance(wpm_matched_sell, tuple):
                        # Try both orderings: (trade, consumed_quantity) or (consumed_quantity, trade)
                        if len(wpm_matched_sell) >= 2:
                            # Check if first element is a Trade object (it has a date attribute)
                            # Use isinstance to check if it's a WPMTrade object
                            if isinstance(wpm_matched_sell[0], WPMTrade):
                                wpm_trade = wpm_matched_sell[0]
                                consumed_quantity = float(wpm_matched_sell[1])
                            else:
                                # Reverse order: (consumed_quantity, trade)
                                consumed_quantity = float(wpm_matched_sell[0])
                                wpm_trade = wpm_matched_sell[1]
                        else:
                            logger.warning(f"Unexpected tuple length for matched_sell: {len(wpm_matched_sell)}")
                            continue
                    else:
                        # Extract consumed quantity and trade from matched sell object
                        consumed_quantity = float(wpm_matched_sell.consumed_quantity)
                        wpm_trade = wpm_matched_sell.trade

                    # Transform trade to API Trade model using helper function
                    trade_date_str = _parse_date_to_iso_string(wpm_trade.date)

                    # Extract ticker and asset_type using helper function
                    trade_ticker, trade_asset_type = _extract_ticker_and_asset_type_from_trade(wpm_trade, ticker_value)

                    order_instruction = wpm_trade.order_instruction
                    trade_quantity = float(wpm_trade.quantity)
                    trade_price = float(wpm_trade.price)
                    broker = wpm_trade.broker

                    # Determine action using helper function (should be Sell for matched sells)
                    action = _determine_trade_action(wpm_trade, order_instruction)

                    # Create API Trade model
                    api_trade = Trade(
                        date=trade_date_str,
                        ticker=trade_ticker,
                        asset_type=trade_asset_type,
                        action=action,
                        order_instruction=order_instruction,
                        quantity=trade_quantity,
                        price=trade_price,
                        broker=broker,
                    )

                    # Create MatchedSell model
                    matched_sell = MatchedSell(
                        trade=api_trade,
                        consumed_quantity=consumed_quantity,
                    )
                    matched_sells.append(matched_sell)
                except Exception as e:
                    logger.warning(f"Error processing matched sell for ticker {ticker}: {e}", exc_info=True)
                    continue

            # Create API Lot model
            api_lot = Lot(
                date=lot_date_str,
                ticker=ticker_value,
                asset_type=asset_type_value,
                original_quantity=original_quantity,
                remaining_quantity=remaining_quantity,
                cost_basis=cost_basis,
                matched_sells=matched_sells,
                broker=broker,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                total_pnl=total_pnl,
            )
            api_lots.append(api_lot)
        except Exception as e:
            logger.error(f"Error transforming lot for ticker {ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Transformed {len(api_lots)} lots to API models")

    # Apply sorting if requested
    if sort_by is None:
        sort_by = "date"
    
    # Validate sort_by field
    if sort_by not in VALID_LOT_SORT_FIELDS:
        raise ValueError(f"Invalid sort_by field: {sort_by}. Valid fields: {sorted(VALID_LOT_SORT_FIELDS)}")
    
    # Normalize sort_order
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"
    
    # Sort the lots
    reverse = sort_order == "desc"
    
    def get_sort_key(lot: Lot):
        """Get sort key for a lot, handling date string parsing and None values."""
        # Direct attribute access for sort_by field
        if sort_by == "date":
            value = lot.date
        elif sort_by == "original_quantity":
            value = lot.original_quantity
        elif sort_by == "remaining_quantity":
            value = lot.remaining_quantity
        elif sort_by == "cost_basis":
            value = lot.cost_basis
        elif sort_by == "broker":
            value = lot.broker
        elif sort_by == "realized_pnl":
            value = lot.realized_pnl
        elif sort_by == "unrealized_pnl":
            value = lot.unrealized_pnl
        elif sort_by == "total_pnl":
            value = lot.total_pnl
        else:
            value = None
        
        # For date field, parse ISO format string to date object for proper sorting
        if sort_by == "date" and value is not None:
            try:
                return date.fromisoformat(value)
            except (ValueError, AttributeError):
                # If parsing fails, use string comparison as fallback
                return value
        
        # Handle None values for numeric and string fields
        if value is None:
            sentinel = float('-inf') if not reverse else float('inf')
            return (1 if reverse else 0, sentinel)
        
        # For non-None values
        return (0 if reverse else 1, value)
    
    sorted_lots = sorted(api_lots, key=get_sort_key, reverse=reverse)
    
    logger.info(f"Sorted {len(sorted_lots)} lots by {sort_by} ({sort_order})")
    return sorted_lots


def get_cached_portfolio_performance(
    cache: dict[str, PortfolioHistoryPoint],
    cache_end_date: Optional[date],
    start_date: date,
    end_date: date,
) -> List[PortfolioHistoryPoint]:
    """
    Retrieve and filter cached portfolio performance history points by date range.

    Args:
        cache: Dictionary keyed by ISO date string (YYYY-MM-DD), mapping to PortfolioHistoryPoint API models
        cache_end_date: Maximum date in the cache (None if cache is empty)
        start_date: Start date for performance tracking (inclusive)
        end_date: End date for performance tracking (inclusive)

    Returns:
        List of PortfolioHistoryPoint API models, filtered by date range, in chronological order

    Raises:
        ValueError: If date range is invalid, cache_end_date is None, or end_date > cache_end_date
    """
    logger.info(f"Retrieving cached portfolio performance from {start_date} to {end_date}")
    
    # Validate cache_end_date
    if cache_end_date is None:
        raise ValueError("Performance cache is not available (cache_end_date is None)")
    
    # Validate date range
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) must be less than or equal to end_date ({end_date})")
    
    # Validate end_date is not beyond cache
    if end_date > cache_end_date:
        raise ValueError(
            f"end_date ({end_date}) exceeds maximum available date in cache ({cache_end_date})"
        )
    
    # Iterate through dates from start_date to end_date (inclusive) and retrieve from cache
    history_points = []
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.isoformat()
        if date_str in cache:
            cached_point = cache[date_str]
            history_points.append(cached_point)
        else:
            # Log warning if date is missing from cache (shouldn't happen in normal operation)
            logger.warning(f"Date {date_str} not found in performance cache")
        # Increment date by one day
        current_date += timedelta(days=1)
    
    logger.info(
        f"Retrieved {len(history_points)} history points from cache "
        f"(from {start_date} to {end_date})"
    )
    return history_points


def get_portfolio_performance(
    portfolio: CompositePortfolio,
    price_service: PriceService,
    start_date: date,
    end_date: date,
) -> List[PortfolioHistoryPoint]:
    """
    Retrieve historical performance data from the wpm historical portfolio and transform to API models.

    Args:
        portfolio: Historical CompositePortfolio instance from wpm library
        price_service: PriceService instance for fetching historical prices
        start_date: Start date for performance tracking (inclusive)
        end_date: End date for performance tracking (inclusive)

    Returns:
        List of PortfolioHistoryPoint API models, one for each day from start_date to end_date

    Raises:
        ValueError: If date range is invalid or historical prices cannot be retrieved
    """
    logger.info(f"Retrieving portfolio performance from {start_date} to {end_date}")
    
    try:
        # Call wpm library function to get historical performance
        wpm_history_points = get_historical_performance(portfolio, price_service, start_date, end_date)
        logger.info(f"Retrieved {len(wpm_history_points)} history points from wpm library")
    except Exception as e:
        logger.error(f"Error retrieving historical performance: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve historical performance: {e}")
    
    # Transform wpm PortfolioHistoryPoint objects to API models
    api_history_points = []
    for wpm_history_point in wpm_history_points:
        try:
            # Extract date and convert to ISO format string
            history_date_str = _parse_date_to_iso_string(wpm_history_point.date)
            
            # Extract total_market_value
            total_market_value = float(wpm_history_point.total_market_value)
            
            # Extract asset_positions (already Dict[str, float])
            asset_positions = wpm_history_point.asset_positions
            
            # Extract prices (already Dict[str, float])
            prices = wpm_history_point.prices
            
            # Create API PortfolioHistoryPoint model
            api_history_point = PortfolioHistoryPoint(
                date=history_date_str,
                total_market_value=total_market_value,
                asset_positions=asset_positions,
                prices=prices,
            )
            api_history_points.append(api_history_point)
        except Exception as e:
            logger.error(f"Error transforming history point: {e}", exc_info=True)
            continue
    
    logger.info(f"Transformed {len(api_history_points)} history points to API models")
    return api_history_points
