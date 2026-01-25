"""Business logic for portfolio operations, wraps wpm library calls."""

import logging
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from wpm.asset import AssetService
from wpm.models import Asset, Position as WPMPosition, Trade as WPMTrade
from wpm.portfolio import CompositePortfolio, fetch_price_map, get_historical_performance, get_positions_with_allocations
from wpm.pricing import PriceService

from wpm_backend.models.portfolio import AllocationPosition, AssetPriceHistoryResponse, BrokerPosition, Lot, MatchedSell, OverallPosition, PortfolioHistoryPoint, Position, PricePoint, Trade
from wpm_backend.services.portfolio_utils import (
    _get_month_start_dates,
    _get_weekly_dates,
    determine_trade_action,
    extract_ticker_and_asset_type_from_lot,
    extract_ticker_and_asset_type_from_trade,
    get_lot_date,
    parse_date_to_date_object,
    parse_date_to_iso_string,
)

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
    "allocation_percentage",
    "realized_gain_loss",
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

    # Fetch current prices first (needed for get_positions_with_allocations)
    logger.info("Fetching current prices for all assets")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Get positions with allocations from composite portfolio
    positions_with_allocations = get_positions_with_allocations(composite, price_map)
    logger.info(f"Retrieved {len(positions_with_allocations)} positions with allocations from composite portfolio")

    # Transform wpm Position objects to API Position models
    api_positions = []
    for asset, (wpm_position, allocation_decimal) in positions_with_allocations.items():
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

            # Convert allocation from Decimal to float
            allocation_percentage = float(allocation_decimal) if allocation_decimal is not None else None

            # Get realized P/L for this asset
            realized_gain_loss = composite.get_asset_realized_pnl(asset.ticker)

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
                allocation_percentage=allocation_percentage,
                realized_gain_loss=realized_gain_loss,
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
        elif sort_by == "allocation_percentage":
            value = position.allocation_percentage
        elif sort_by == "realized_gain_loss":
            value = position.realized_gain_loss
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
            trade_date = parse_date_to_date_object(wpm_trade.date)

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
            trade_date_str = parse_date_to_iso_string(wpm_trade.date)

            # Extract ticker and asset_type using helper function
            ticker_value, asset_type_value = extract_ticker_and_asset_type_from_trade(wpm_trade, ticker)

            order_instruction = wpm_trade.order_instruction
            quantity = float(wpm_trade.quantity)
            price = float(wpm_trade.price)
            broker = wpm_trade.broker

            # Determine trade action using helper function
            action = determine_trade_action(wpm_trade, order_instruction)

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
    brokers: Optional[List[str]] = None,
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
        brokers: Optional list of broker names to filter by
        sort_by: Field name to sort by (default: None, which defaults to "date")
        sort_order: Sort order - "asc" or "desc" (default: "asc")

    Returns:
        Sorted list of Lot API models, filtered by date range and brokers if provided

    Raises:
        ValueError: If ticker is not found or invalid, or if sort_by is not a valid Lot field
    """
    logger.info(f"Retrieving lots for ticker: {ticker}, start_date={start_date}, end_date={end_date}, brokers={brokers}, sort_by={sort_by}, sort_order={sort_order}")

    # Fetch current prices for P&L calculations (needed for get_asset_lots with prices parameter)
    logger.info("Fetching current prices for P&L calculations")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Get lots from composite portfolio (with broker and date filtering if provided)
    try:
        wpm_lots = composite.get_asset_lots(
            ticker,
            start_date=start_date,
            end_date=end_date,
            brokers=brokers,
            prices=price_map,
        )
        logger.info(f"Retrieved {len(wpm_lots)} lots for ticker {ticker}")
    except Exception as e:
        logger.error(f"Error retrieving lots for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve lots for ticker {ticker}: {e}")

    # Transform wpm Lot objects to API Lot models
    api_lots = []
    for wpm_lot in wpm_lots:
        try:
            # Extract lot date using helper function
            lot_date_obj = get_lot_date(wpm_lot)
            if lot_date_obj is None:
                # If no date found, skip this lot (date is required by Lot model)
                logger.warning(f"Lot for ticker {ticker} has no date, skipping")
                continue
            lot_date_str = lot_date_obj.isoformat()

            # Extract ticker and asset_type using helper function
            ticker_value, asset_type_value = extract_ticker_and_asset_type_from_lot(wpm_lot, ticker)

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
                    trade_date_str = parse_date_to_iso_string(wpm_trade.date)

                    # Extract ticker and asset_type using helper function
                    trade_ticker, trade_asset_type = extract_ticker_and_asset_type_from_trade(wpm_trade, ticker_value)

                    order_instruction = wpm_trade.order_instruction
                    trade_quantity = float(wpm_trade.quantity)
                    trade_price = float(wpm_trade.price)
                    broker = wpm_trade.broker

                    # Determine action using helper function (should be Sell for matched sells)
                    action = determine_trade_action(wpm_trade, order_instruction)

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


def get_asset_positions_by_broker(
    composite: CompositePortfolio,
    ticker: str,
    price_service: PriceService,
    brokers: Optional[List[str]] = None,
) -> tuple[OverallPosition, List[BrokerPosition]]:
    """
    Retrieve positions by broker for a specific asset ticker and calculate overall position.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol to retrieve positions for
        price_service: PriceService instance for fetching current prices
        brokers: Optional list of broker names to filter by

    Returns:
        Tuple of (overall_position: OverallPosition, per_broker_positions: List[BrokerPosition])

    Raises:
        ValueError: If ticker is not found
    """
    logger.info(f"Retrieving positions by broker for ticker: {ticker}, brokers={brokers}")

    # Get positions by broker from composite portfolio
    try:
        broker_positions_dict = composite.get_asset_positions_by_broker(ticker)
        logger.info(f"Retrieved positions for {len(broker_positions_dict)} brokers for ticker {ticker}")
    except Exception as e:
        logger.error(f"Error retrieving positions by broker for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve positions by broker for ticker {ticker}: {e}")

    # Filter by brokers if provided
    if brokers is not None:
        filtered_positions_dict = {
            broker: position
            for broker, position in broker_positions_dict.items()
            if broker in brokers
        }
        broker_positions_dict = filtered_positions_dict
        logger.info(f"Filtered to {len(broker_positions_dict)} brokers after filtering")

    # Fetch current prices for market value calculations
    logger.info("Fetching current prices for market value calculations")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Transform wpm Position objects to BrokerPosition API models
    per_broker_positions = []
    # Use Decimal for precise quantity calculations, convert to float only at the end
    total_quantity_decimal = Decimal("0")
    total_cost_basis_decimal = Decimal("0")
    total_market_value: Optional[float] = None

    for broker_name, wpm_position in broker_positions_dict.items():
        try:
            # Keep quantity as Decimal for precise calculations
            quantity_decimal = wpm_position.quantity if isinstance(wpm_position.quantity, Decimal) else Decimal(str(wpm_position.quantity))
            cost_basis_decimal = Decimal(str(wpm_position.cost_basis))

            # Convert to float only for BrokerPosition model (individual broker quantities)
            quantity = float(quantity_decimal)
            cost_basis = float(cost_basis_decimal)

            # Get current price for this position's asset
            current_price = price_map.get(wpm_position.asset)

            # Calculate market_value (quantity * current_price) if price available
            market_value = None
            if current_price is not None:
                market_value = quantity * current_price

            # Create BrokerPosition model
            broker_position = BrokerPosition(
                broker=broker_name,
                quantity=quantity,
                cost_basis=cost_basis,
                market_value=market_value,
            )
            per_broker_positions.append(broker_position)

            # Aggregate overall position using Decimal for precision
            total_quantity_decimal += quantity_decimal
            total_cost_basis_decimal += cost_basis_decimal
            if market_value is not None:
                if total_market_value is None:
                    total_market_value = 0.0
                total_market_value += market_value

        except Exception as e:
            logger.warning(f"Error processing position for broker {broker_name}, ticker {ticker}: {e}", exc_info=True)
            continue

    # Convert Decimal to float only at the end for OverallPosition model
    total_quantity = float(total_quantity_decimal)
    total_cost_basis = float(total_cost_basis_decimal)

    # Create OverallPosition model
    overall_position = OverallPosition(
        quantity=total_quantity,
        cost_basis=total_cost_basis,
        market_value=total_market_value,
    )

    logger.info(
        f"Calculated positions for ticker {ticker}: "
        f"overall qty={total_quantity}, cost_basis={total_cost_basis}, "
        f"market_value={total_market_value}, brokers={len(per_broker_positions)}"
    )

    return overall_position, per_broker_positions


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


def apply_granularity_filter(
    history_points: List[PortfolioHistoryPoint],
    start_date: date,
    end_date: date,
    granularity: str = "daily",
) -> List[PortfolioHistoryPoint]:
    """
    Filter history points based on granularity parameter.
    
    Takes a list of all daily history points (must be sorted chronologically)
    and filters them according to the specified granularity.
    
    Args:
        history_points: List of all daily history points (must be sorted chronologically)
        start_date: Start date of the range
        end_date: End date of the range
        granularity: Granularity level - "daily", "weekly", or "monthly"
        
    Returns:
        Filtered list of history points based on granularity, in chronological order
        
    Raises:
        ValueError: If granularity is not one of the supported values
    """
    logger.info(
        f"Applying granularity filter: granularity={granularity}, "
        f"start_date={start_date}, end_date={end_date}, "
        f"input_points={len(history_points)}"
    )
    
    # Daily granularity: return all points as-is
    if granularity == "daily":
        logger.info(f"Daily granularity: returning all {len(history_points)} points")
        return history_points
    
    # Weekly granularity: filter to Monday dates
    if granularity == "weekly":
        # Get list of Monday dates in the range
        weekly_dates = _get_weekly_dates(start_date, end_date)
        weekly_dates_set = {d.isoformat() for d in weekly_dates}
        
        # Filter history points to only include Mondays
        filtered_points = [
            point for point in history_points
            if point.date in weekly_dates_set
        ]
        
        logger.info(
            f"Weekly granularity: filtered from {len(history_points)} to {len(filtered_points)} points"
        )
        return filtered_points
    
    # Monthly granularity: filter to first-of-month dates
    if granularity == "monthly":
        # Get list of month start dates in the range
        month_start_dates = _get_month_start_dates(start_date, end_date)
        month_start_dates_set = {d.isoformat() for d in month_start_dates}
        
        # Filter history points to only include month starts
        filtered_points = [
            point for point in history_points
            if point.date in month_start_dates_set
        ]
        
        logger.info(
            f"Monthly granularity: filtered from {len(history_points)} to {len(filtered_points)} points"
        )
        return filtered_points
    
    # Invalid granularity value
    raise ValueError(
        f"Invalid granularity: {granularity}. "
        f"Supported values: 'daily', 'weekly', 'monthly'"
    )


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
            history_date_str = parse_date_to_iso_string(wpm_history_point.date)
            
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


def get_asset_metadata(
    composite: CompositePortfolio,
    ticker: str,
    asset_service: AssetService,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve metadata for a single asset ticker from the wpm library using AssetService.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol
        asset_service: AssetService instance for retrieving metadata

    Returns:
        Metadata dictionary or None if retrieval fails

    Raises:
        ValueError: If ticker is not found in portfolio
    """
    logger.info(f"Retrieving metadata for ticker: {ticker}")

    # Get asset_type from portfolio
    assets = composite.get_assets()
    if ticker not in assets:
        logger.warning(f"Ticker {ticker} not found in portfolio")
        raise ValueError(f"Ticker {ticker} not found in portfolio")

    asset = assets[ticker]
    asset_type = asset.asset_type
    logger.info(f"Found asset {ticker} with asset_type: {asset_type}")

    # Get metadata from AssetService
    try:
        metadata = asset_service.get_metadata(ticker, asset_type)
        if metadata is None:
            logger.warning(f"Metadata retrieval failed for ticker: {ticker}")
        else:
            logger.info(f"Successfully retrieved metadata for ticker: {ticker}")
        return metadata
    except Exception as e:
        logger.error(f"Error retrieving metadata for ticker {ticker}: {e}", exc_info=True)
        return None


def get_all_asset_metadata(
    composite: CompositePortfolio,
    asset_service: AssetService,
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Retrieve metadata for all tickers in the portfolio from the wpm library using AssetService.

    Args:
        composite: CompositePortfolio instance from wpm library
        asset_service: AssetService instance for retrieving metadata

    Returns:
        Dictionary mapping ticker to metadata (None if retrieval fails for that ticker)
    """
    logger.info("Retrieving metadata for all tickers in portfolio")

    # Get all tickers from portfolio
    assets = composite.get_assets()
    logger.info(f"Found {len(assets)} tickers in portfolio")

    if not assets:
        logger.info("Portfolio is empty, returning empty metadata dictionary")
        return {}

    # Group tickers by asset_type (get_metadata_batch requires all tickers to have same asset_type)
    tickers_by_asset_type: Dict[str, List[str]] = {}
    for ticker, asset in assets.items():
        asset_type = asset.asset_type
        if asset_type not in tickers_by_asset_type:
            tickers_by_asset_type[asset_type] = []
        tickers_by_asset_type[asset_type].append(ticker)

    logger.info(f"Grouped tickers into {len(tickers_by_asset_type)} asset types: {list(tickers_by_asset_type.keys())}")

    # Retrieve metadata for each asset_type group
    all_metadata: Dict[str, Optional[Dict[str, Any]]] = {}
    for asset_type, tickers in tickers_by_asset_type.items():
        logger.info(f"Retrieving metadata for {len(tickers)} tickers of asset_type: {asset_type}")
        try:
            metadata_batch = asset_service.get_metadata_batch(tickers, asset_type)
            all_metadata.update(metadata_batch)
            logger.info(f"Successfully retrieved metadata for {len([m for m in metadata_batch.values() if m is not None])} out of {len(tickers)} tickers")
        except Exception as e:
            logger.error(f"Error retrieving metadata batch for asset_type {asset_type}: {e}", exc_info=True)
            # Set None for all tickers in this group if batch retrieval fails
            for ticker in tickers:
                all_metadata[ticker] = None

    logger.info(f"Retrieved metadata for {len(all_metadata)} tickers total")
    return all_metadata


def get_asset_brokers(
    composite: CompositePortfolio,
    ticker: str,
) -> List[str]:
    """
    Retrieve list of broker names that have positions for a specific asset ticker.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol to retrieve brokers for

    Returns:
        List of broker names (strings). Returns empty list if ticker exists but has no positions.

    Raises:
        ValueError: If ticker is not found
    """
    logger.info(f"Retrieving brokers for ticker: {ticker}")

    # Get positions by broker from composite portfolio
    try:
        broker_positions_dict = composite.get_asset_positions_by_broker(ticker)
        logger.info(f"Retrieved positions for {len(broker_positions_dict)} brokers for ticker {ticker}")
    except Exception as e:
        logger.error(f"Error retrieving brokers for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve brokers for ticker {ticker}: {e}")

    # Extract broker names from dictionary keys
    broker_names = list(broker_positions_dict.keys())
    
    logger.info(f"Found {len(broker_names)} brokers for ticker {ticker}: {broker_names}")
    return broker_names


def get_asset_price_history(
    composite: CompositePortfolio,
    ticker: str,
    price_service: PriceService,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> AssetPriceHistoryResponse:
    """
    Retrieve historical price data for a specific asset ticker.

    Args:
        composite: CompositePortfolio instance from wpm library
        ticker: Asset ticker symbol to retrieve price history for
        price_service: PriceService instance for retrieving prices
        start_date: Optional start date for price history (defaults to max of 2 years ago or portfolio start_date)
        end_date: Optional end date for price history (defaults to today)

    Returns:
        AssetPriceHistoryResponse with historical prices and current price

    Raises:
        ValueError: If ticker is not found in portfolio or price data cannot be retrieved
    """
    logger.info(f"Retrieving price history for ticker: {ticker}, start_date={start_date}, end_date={end_date}")

    # Validate ticker exists in portfolio and get asset type
    assets = composite.get_assets()
    if ticker not in assets:
        logger.warning(f"Ticker {ticker} not found in portfolio")
        raise ValueError(f"Ticker {ticker} not found in portfolio")

    asset = assets[ticker]
    asset_type = asset.asset_type
    logger.info(f"Found asset {ticker} with asset_type: {asset_type}")

    # Calculate default start_date if not provided
    # Default: max of 2 years ago or portfolio start_date
    today = date.today()
    if start_date is None:
        portfolio_start_date = composite.start_date
        two_years_ago = today - timedelta(days=730)
        
        if portfolio_start_date is not None:
            start_date = max(two_years_ago, portfolio_start_date)
        else:
            start_date = two_years_ago
        
        logger.info(f"Calculated default start_date: {start_date} (max of 2 years ago or portfolio start)")

    # Default end_date to today if not provided
    if end_date is None:
        end_date = today
        logger.info(f"Using default end_date: {end_date}")

    # Validate date range
    if end_date < start_date:
        logger.warning(f"Invalid date range: end_date={end_date} < start_date={start_date}")
        raise ValueError(f"end_date ({end_date}) must be greater than or equal to start_date ({start_date})")

    # Get historical prices
    try:
        historical_prices = price_service.get_historical_prices(
            [ticker], asset_type, start_date, end_date
        )
        logger.info(f"Retrieved historical prices for {ticker} from {start_date} to {end_date}")
    except Exception as e:
        logger.error(f"Error retrieving historical prices for ticker {ticker}: {e}", exc_info=True)
        raise ValueError(f"Failed to retrieve historical prices for ticker {ticker}: {e}")

    # Transform historical prices to PricePoint list
    price_points: List[PricePoint] = []
    if ticker in historical_prices:
        ticker_prices = historical_prices[ticker]
        # Sort by date to ensure chronological order
        sorted_dates = sorted(ticker_prices.keys())
        for price_date in sorted_dates:
            price_points.append(
                PricePoint(
                    date=price_date.isoformat(),
                    price=ticker_prices[price_date]
                )
            )
        logger.info(f"Transformed {len(price_points)} price points for {ticker}")
    else:
        logger.warning(f"No historical price data found for ticker {ticker} in date range")

    # Get current price
    current_price: Optional[float] = None
    try:
        current_price = price_service.get_price(ticker, asset_type)
        logger.info(f"Retrieved current price for {ticker}: {current_price}")
    except Exception as e:
        logger.warning(f"Could not retrieve current price for ticker {ticker}: {e}", exc_info=True)
        # Current price is optional, so we continue without it

    return AssetPriceHistoryResponse(
        ticker=ticker,
        asset_type=asset_type,
        prices=price_points,
        current_price=current_price
    )


def get_portfolio_allocation(
    composite: CompositePortfolio,
    price_service: PriceService,
    asset_service: AssetService,
    asset_types: Optional[List[str]] = None,
    tickers: Optional[List[str]] = None,
) -> List[AllocationPosition]:
    """
    Retrieve filtered portfolio positions with metadata for the allocation endpoint.

    Args:
        composite: CompositePortfolio instance from wpm library
        price_service: PriceService instance for fetching current prices
        asset_service: AssetService instance for retrieving metadata
        asset_types: Optional list of asset types to filter by (e.g., ["Stock", "ETF", "Crypto"])
        tickers: Optional list of ticker symbols to filter by (e.g., ["AAPL", "GOOG"])

    Returns:
        List of AllocationPosition API models with metadata included

    Note:
        Filtering uses OR logic: assets are included if they match any specified asset_type OR any specified ticker.
        Allocations are automatically recalculated against the filtered asset list only by the wpm library.
    """
    logger.info(
        f"Retrieving portfolio allocation with filters: asset_types={asset_types}, tickers={tickers}"
    )

    # Fetch current prices first (needed for get_positions_with_allocations)
    logger.info("Fetching current prices for all assets")
    price_map = fetch_price_map(composite, price_service)
    logger.info(f"Fetched prices for {len(price_map)} assets")

    # Get positions with allocations from composite portfolio (with filtering if provided)
    positions_with_allocations = get_positions_with_allocations(
        composite, price_map, asset_types=asset_types, asset_tickers=tickers
    )
    logger.info(
        f"Retrieved {len(positions_with_allocations)} positions with allocations from composite portfolio"
    )

    # Transform wpm Position objects to API AllocationPosition models
    api_positions = []
    for asset, (wpm_position, allocation_decimal) in positions_with_allocations.items():
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

            # Convert allocation from Decimal to float
            allocation_percentage = float(allocation_decimal) if allocation_decimal is not None else None

            # Get realized P/L for this asset
            realized_gain_loss = composite.get_asset_realized_pnl(asset.ticker)

            # Create API AllocationPosition model (metadata will be added later)
            api_position = AllocationPosition(
                ticker=asset.ticker,
                asset_type=asset.asset_type,
                quantity=quantity_float,
                average_price=average_price,
                cost_basis=float(wpm_position.cost_basis),
                cost_basis_method=wpm_position.cost_basis_method,
                current_price=current_price,
                market_value=market_value,
                unrealized_gain_loss=unrealized_gain_loss,
                allocation_percentage=allocation_percentage,
                realized_gain_loss=realized_gain_loss,
                metadata=None,  # Will be populated from batch metadata retrieval
            )
            api_positions.append(api_position)
        except Exception as e:
            logger.error(f"Error transforming position for asset {asset.ticker}: {e}", exc_info=True)
            continue

    logger.info(f"Transformed {len(api_positions)} positions to API models")

    # Extract filtered tickers and group by asset_type for batch metadata retrieval
    if api_positions:
        tickers_by_asset_type: Dict[str, List[str]] = {}
        for position in api_positions:
            asset_type = position.asset_type
            if asset_type not in tickers_by_asset_type:
                tickers_by_asset_type[asset_type] = []
            tickers_by_asset_type[asset_type].append(position.ticker)

        logger.info(
            f"Grouped {len([t for tickers in tickers_by_asset_type.values() for t in tickers])} tickers into {len(tickers_by_asset_type)} asset types: {list(tickers_by_asset_type.keys())}"
        )

        # Retrieve metadata for each asset_type group
        all_metadata: Dict[str, Optional[Dict[str, Any]]] = {}
        for asset_type, ticker_list in tickers_by_asset_type.items():
            logger.info(f"Retrieving metadata for {len(ticker_list)} tickers of asset_type: {asset_type}")
            try:
                metadata_batch = asset_service.get_metadata_batch(ticker_list, asset_type)
                all_metadata.update(metadata_batch)
                logger.info(
                    f"Successfully retrieved metadata for {len([m for m in metadata_batch.values() if m is not None])} out of {len(ticker_list)} tickers"
                )
            except Exception as e:
                logger.error(
                    f"Error retrieving metadata batch for asset_type {asset_type}: {e}", exc_info=True
                )
                # Set None for all tickers in this group if batch retrieval fails
                for ticker in ticker_list:
                    all_metadata[ticker] = None

        # Merge metadata into AllocationPosition objects
        for position in api_positions:
            position.metadata = all_metadata.get(position.ticker)

        logger.info(f"Merged metadata for {len(api_positions)} positions")

    logger.info(f"Returning {len(api_positions)} allocation positions with metadata")
    return api_positions
