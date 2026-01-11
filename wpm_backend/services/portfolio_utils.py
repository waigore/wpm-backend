"""Utility functions for portfolio service operations."""

import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from wpm.models import Trade as WPMTrade

logger = logging.getLogger(__name__)


def parse_date_to_date_object(date_value) -> date:
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


def parse_date_to_iso_string(date_value) -> str:
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


def determine_trade_action(wpm_trade, order_instruction: str) -> str:
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


def extract_ticker_and_asset_type_from_trade(wpm_trade, default_ticker: str) -> tuple[str, str]:
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


def get_lot_date(wpm_lot) -> Optional[date]:
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
            return parse_date_to_date_object(purchase_date)
        except Exception:
            pass
    
    return None


def extract_ticker_and_asset_type_from_lot(wpm_lot, default_ticker: str) -> tuple[str, str]:
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


def _get_next_monday(start_date: date) -> date:
    """
    Find the next Monday from a given date.
    
    If start_date is already a Monday, returns start_date.
    Otherwise, returns the date of the next Monday.
    
    Args:
        start_date: Starting date
        
    Returns:
        Date of the next Monday (or start_date if it's already a Monday)
    """
    # date.weekday() returns 0 for Monday, 1 for Tuesday, ..., 6 for Sunday
    days_until_monday = (7 - start_date.weekday()) % 7
    
    # If days_until_monday is 0, start_date is already a Monday
    if days_until_monday == 0:
        return start_date
    
    # Add days to get to the next Monday
    return start_date + timedelta(days=days_until_monday)


def _get_weekly_dates(start_date: date, end_date: date) -> List[date]:
    """
    Generate list of weekly dates (Mondays) from start_date to end_date.
    
    If start_date is not a Monday, finds the next Monday first.
    Then generates Monday dates at weekly intervals until end_date.
    
    Args:
        start_date: Start date of the range
        end_date: End date of the range (inclusive)
        
    Returns:
        List of Monday dates in the range
    """
    # Find the first Monday from start_date
    first_monday = _get_next_monday(start_date)
    
    # Generate weekly dates (Mondays)
    weekly_dates = []
    current_date = first_monday
    
    while current_date <= end_date:
        weekly_dates.append(current_date)
        current_date += timedelta(weeks=1)
    
    return weekly_dates


def _get_month_start_dates(start_date: date, end_date: date) -> List[date]:
    """
    Generate list of month start dates (first day of each month) from start_date to end_date.
    
    For each month in the range, includes the first day of the month if it falls
    within the range [start_date, end_date].
    
    Args:
        start_date: Start date of the range
        end_date: End date of the range (inclusive)
        
    Returns:
        List of first-of-month dates in the range
    """
    month_start_dates = []
    
    # Start from the first day of the month containing start_date
    current_month_start = date(start_date.year, start_date.month, 1)
    
    # If start_date is after the first of its month, move to the next month
    if current_month_start < start_date:
        # Move to next month
        if current_month_start.month == 12:
            current_month_start = date(current_month_start.year + 1, 1, 1)
        else:
            current_month_start = date(current_month_start.year, current_month_start.month + 1, 1)
    
    # Generate month start dates until we exceed end_date
    while current_month_start <= end_date:
        month_start_dates.append(current_month_start)
        
        # Move to next month
        if current_month_start.month == 12:
            current_month_start = date(current_month_start.year + 1, 1, 1)
        else:
            current_month_start = date(current_month_start.year, current_month_start.month + 1, 1)
    
    return month_start_dates
