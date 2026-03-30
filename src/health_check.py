"""
Health checks and monitoring for the trading platform.
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from .utils import get_db_engine, load_config, logger

def check_data_freshness(config, hours_threshold=24):
    """
    Check if market data is fresh.
    Returns: dict with status, last_update, missing_symbols
    """
    engine = get_db_engine(config)
    now = datetime.now()
    cutoff = now - timedelta(hours=hours_threshold)

    try:
        with engine.connect() as conn:
            # Get latest date and timestamp for each symbol
            result = conn.execute(text("""
                SELECT symbol, MAX(date) as latest_date
                FROM market_data
                GROUP BY symbol
            """))

            issues = []
            latest_overall = None

            for row in result:
                symbol, latest_date = row
                if latest_date is None:
                    issues.append(f"{symbol}: no date")
                    continue

                # Convert to datetime at start of day
                latest_dt = datetime.combine(latest_date, datetime.min.time())

                if latest_overall is None or latest_date > latest_overall:
                    latest_overall = latest_date

                # Check if data is stale (assuming we update only on trading days)
                # For simplicity: if latest date is more than X days old, flag
                days_old = (now.date() - latest_date).days
                if days_old > 2:  # allow weekends/holidays
                    issues.append(f"{symbol}: {days_old} days old")

            return {
                'status': 'OK' if not issues else 'STALE',
                'last_update': latest_overall.isoformat() if latest_overall else None,
                'issues': issues,
                'checked_at': now.isoformat()
            }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {'status': 'ERROR', 'error': str(e)}


if __name__ == "__main__":
    config = load_config()
    result = check_data_freshness(config)
    print(f"Data Health: {result}")
    if result['issues']:
        print("Issues found:")
        for issue in result['issues']:
            print(f"  - {issue}")
