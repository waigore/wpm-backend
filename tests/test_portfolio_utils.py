"""Unit tests for portfolio utility functions."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from wpm_backend.models.portfolio import PortfolioHistoryPoint, Position
from wpm_backend.services.portfolio_service import apply_granularity_filter, get_all_positions, get_portfolio_performance


def test_portfolio_response_total_count():
    """Test PortfolioResponse.total_count computed field (deprecated model)."""
    from wpm_backend.models.portfolio import PortfolioResponse, Position
    
    # Create a PortfolioResponse with positions
    positions = [
        Position(
            ticker="AAPL",
            asset_type="Stock",
            quantity=100.0,
            average_price=150.0,
            cost_basis=15000.0,
            cost_basis_method="fifo",
        ),
        Position(
            ticker="GOOGL",
            asset_type="Stock",
            quantity=50.0,
            average_price=100.0,
            cost_basis=5000.0,
            cost_basis_method="average",
        ),
    ]
    
    portfolio_response = PortfolioResponse(positions=positions)
    assert portfolio_response.total_count == 2
    
    # Test with empty positions
    empty_response = PortfolioResponse(positions=[])
    assert empty_response.total_count == 0


def test_parse_date_to_iso_string_custom_objects():
    """Test parse_date_to_iso_string helper function with custom date-like objects."""
    from datetime import date
    from wpm_backend.services.portfolio_utils import parse_date_to_iso_string
    
    # Test with ISO string (validates and returns - covers line 95-96)
    assert parse_date_to_iso_string("2024-01-15") == "2024-01-15"
    
    # Test with custom date-like object with isoformat method (covers hasattr path)
    class CustomDateWithIsoformat:
        def isoformat(self):
            return "2024-01-15"
    
    custom_date = CustomDateWithIsoformat()
    assert parse_date_to_iso_string(custom_date) == "2024-01-15"
    
    # Test with custom date-like object with date method (covers hasattr date path)
    class CustomDateWithDate:
        def date(self):
            return date(2024, 1, 15)
    
    custom_date2 = CustomDateWithDate()
    assert parse_date_to_iso_string(custom_date2) == "2024-01-15"
    
    # Test with custom object (last resort - converts to string, covers line 111)
    class CustomDateStr:
        def __str__(self):
            return "2024-01-15"
    
    custom_date3 = CustomDateStr()
    assert parse_date_to_iso_string(custom_date3) == "2024-01-15"


def test_apply_granularity_filter_daily():
    """Test apply_granularity_filter with daily granularity (returns all points)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for a week
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    # Apply daily granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        start_date + timedelta(days=6),
        "daily",
    )
    
    # Should return all points
    assert len(filtered) == 7
    assert filtered == history_points


def test_apply_granularity_filter_weekly_monday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is Monday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for 3 weeks (21 days)
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Sunday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (Mondays of weeks 1, 2, 3)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-15"  # Monday, week 1
    assert filtered[1].date == "2024-01-22"  # Monday, week 2
    assert filtered[2].date == "2024-01-29"  # Monday, week 3


def test_apply_granularity_filter_weekly_non_monday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is not Monday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on Wednesday
    start_date = date(2024, 1, 17)  # Wednesday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Tuesday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (next Monday after start, then subsequent Mondays)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-22"  # Monday after start (Wed)
    assert filtered[1].date == "2024-01-29"  # Monday, week 2
    assert filtered[2].date == "2024-02-05"  # Monday, week 3


def test_apply_granularity_filter_weekly_sunday_start():
    """Test apply_granularity_filter with weekly granularity when start_date is Sunday."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on Sunday (next Monday is 1 day away)
    start_date = date(2024, 1, 14)  # Sunday
    history_points = []
    for i in range(21):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=20)  # Saturday, 3rd week
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should return 3 points (next Monday after Sunday, then subsequent Mondays)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-15"  # Monday (1 day after Sunday)
    assert filtered[1].date == "2024-01-22"  # Monday, week 2
    assert filtered[2].date == "2024-01-29"  # Monday, week 3


def test_apply_granularity_filter_monthly_first_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is first of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on first of month
    start_date = date(2024, 1, 1)
    history_points = []
    # Create points for 3 months (90 days)
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 3, 31)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Jan 1, Feb 1, Mar 1)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-01-01"
    assert filtered[1].date == "2024-02-01"
    assert filtered[2].date == "2024-03-01"


def test_apply_granularity_filter_monthly_non_first_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is not first of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start in middle of month
    start_date = date(2024, 1, 15)
    history_points = []
    # Create points for 3 months (90 days)
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 4, 15)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Feb 1, Mar 1, Apr 1 - skipping Jan since we start on 15th)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-02-01"  # First of month after start
    assert filtered[1].date == "2024-03-01"
    assert filtered[2].date == "2024-04-01"


def test_apply_granularity_filter_monthly_last_day_of_month():
    """Test apply_granularity_filter with monthly granularity when start_date is last day of month."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Start on last day of month
    start_date = date(2024, 1, 31)
    history_points = []
    # Create points for 3 months
    for i in range(90):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 4, 30)
    
    # Apply monthly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "monthly",
    )
    
    # Should return 3 points (Feb 1, Mar 1, Apr 1)
    assert len(filtered) == 3
    assert filtered[0].date == "2024-02-01"  # First of next month
    assert filtered[1].date == "2024-03-01"
    assert filtered[2].date == "2024-04-01"


def test_apply_granularity_filter_invalid_granularity():
    """Test apply_granularity_filter with invalid granularity value."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    history_points = [
        PortfolioHistoryPoint(
            date="2024-01-15",
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    ]
    
    # Test with invalid granularity
    with pytest.raises(ValueError, match="Invalid granularity"):
        apply_granularity_filter(
            history_points,
            date(2024, 1, 15),
            date(2024, 1, 15),
            "invalid",
        )


def test_portfolio_performance_endpoint_with_granularity_daily(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with daily granularity (default)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 7 days
    cache_end_date = date(2024, 1, 21)
    performance_cache = {}
    for i in range(7):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with daily granularity (default)
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-21&granularity=daily",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return all 7 points
    assert len(data["history_points"]) == 7


def test_portfolio_performance_endpoint_with_granularity_weekly(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with weekly granularity."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)  # Monday
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 21 days (3 weeks)
    cache_end_date = date(2024, 2, 4)  # Sunday, 3rd week
    performance_cache = {}
    for i in range(21):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with weekly granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-02-04&granularity=weekly",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return 3 points (Mondays)
    assert len(data["history_points"]) == 3
    assert data["history_points"][0]["date"] == "2024-01-15"  # Monday, week 1
    assert data["history_points"][1]["date"] == "2024-01-22"  # Monday, week 2
    assert data["history_points"][2]["date"] == "2024-01-29"  # Monday, week 3


def test_portfolio_performance_endpoint_with_granularity_monthly(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with monthly granularity."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 1)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 90 days (3 months)
    cache_end_date = date(2024, 3, 31)
    performance_cache = {}
    for i in range(90):
        current_date = date(2024, 1, 1) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with monthly granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-03-31&granularity=monthly",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return 3 points (first of each month)
    assert len(data["history_points"]) == 3
    assert data["history_points"][0]["date"] == "2024-01-01"
    assert data["history_points"][1]["date"] == "2024-02-01"
    assert data["history_points"][2]["date"] == "2024-03-01"


def test_portfolio_performance_endpoint_invalid_granularity(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with invalid granularity value."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache
    cache_end_date = date(2024, 1, 16)
    performance_cache = {
        "2024-01-15": PortfolioHistoryPoint(
            date="2024-01-15",
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    }
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint with invalid granularity
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-16&granularity=invalid",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    # Should return 422 (FastAPI validation error)
    assert response.status_code == 422


def test_apply_granularity_filter_maintains_chronological_order():
    """Test that apply_granularity_filter maintains chronological order."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points for a week
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0 + (i * 100),
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = start_date + timedelta(days=6)
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Verify chronological order
    assert len(filtered) >= 1
    for i in range(len(filtered) - 1):
        assert filtered[i].date < filtered[i + 1].date


def test_apply_granularity_filter_with_missing_dates():
    """Test apply_granularity_filter when some expected dates are missing from history points."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Create history points but skip some Mondays (simulating missing cache entries)
    start_date = date(2024, 1, 15)  # Monday
    history_points = []
    # Only include some dates, not all Mondays
    dates_to_include = [
        date(2024, 1, 15),  # Monday, week 1
        date(2024, 1, 16),  # Tuesday (not Monday)
        date(2024, 1, 17),  # Wednesday (not Monday)
        # Skip Monday week 2
        date(2024, 1, 29),  # Monday, week 3
    ]
    
    for current_date in dates_to_include:
        history_points.append(
            PortfolioHistoryPoint(
                date=current_date.isoformat(),
                total_market_value=25000.0,
                asset_positions={"AAPL": 17550.0},
                prices={"AAPL": 175.50},
            )
        )
    
    end_date = date(2024, 1, 29)
    
    # Apply weekly granularity
    filtered = apply_granularity_filter(
        history_points,
        start_date,
        end_date,
        "weekly",
    )
    
    # Should only return the Mondays that exist in history_points
    assert len(filtered) == 2
    assert filtered[0].date == "2024-01-15"
    assert filtered[1].date == "2024-01-29"


def test_apply_granularity_filter_single_day_range():
    """Test apply_granularity_filter with single day range."""
    from datetime import date
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    from wpm_backend.services.portfolio_service import apply_granularity_filter
    
    # Single day
    start_date = date(2024, 1, 15)  # Monday
    history_points = [
        PortfolioHistoryPoint(
            date=start_date.isoformat(),
            total_market_value=25000.0,
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        ),
    ]
    
    # Daily granularity should return the single point
    filtered_daily = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "daily",
    )
    assert len(filtered_daily) == 1
    
    # Weekly granularity should return the point if it's a Monday
    filtered_weekly = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "weekly",
    )
    assert len(filtered_weekly) == 1  # Monday is included
    
    # Monthly granularity - Jan 15 is not first of month, so should be empty
    filtered_monthly = apply_granularity_filter(
        history_points,
        start_date,
        start_date,
        "monthly",
    )
    assert len(filtered_monthly) == 0  # Jan 15 is not first of month


def test_portfolio_performance_endpoint_default_granularity(client_with_portfolio, test_settings):
    """Test /portfolio/all/performance endpoint with default granularity (daily)."""
    from datetime import date, timedelta
    from wpm_backend.models.portfolio import PortfolioHistoryPoint
    
    # First, get a token
    login_response = client_with_portfolio.post(
        "/login",
        json={"username": "testuser", "password": "testpass"},
    )
    token = login_response.json()["access_token"]
    
    # Create mock historical portfolio
    mock_historical_portfolio = MagicMock()
    mock_historical_portfolio.start_date = date(2024, 1, 15)
    client_with_portfolio.app.state.historical_portfolio = mock_historical_portfolio
    
    # Set up performance cache with 7 days
    cache_end_date = date(2024, 1, 21)
    performance_cache = {}
    for i in range(7):
        current_date = date(2024, 1, 15) + timedelta(days=i)
        performance_cache[current_date.isoformat()] = PortfolioHistoryPoint(
            date=current_date.isoformat(),
            total_market_value=25000.0 + (i * 100),
            asset_positions={"AAPL": 17550.0},
            prices={"AAPL": 175.50},
        )
    
    client_with_portfolio.app.state.performance_cache = performance_cache
    client_with_portfolio.app.state.performance_cache_end_date = cache_end_date
    
    # Call endpoint without granularity parameter (should default to daily)
    response = client_with_portfolio.get(
        "/portfolio/all/performance?end_date=2024-01-21",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should return all 7 points (daily is default)
    assert len(data["history_points"]) == 7


# Asset Metadata Service Function Tests

