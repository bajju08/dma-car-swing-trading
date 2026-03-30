"""
Data Fetcher Module

Fetches historical and daily market data for NSE stocks.
Primary source: Dhan API (if configured)
Fallback: yfinance (no credentials needed)
Stores data in SQLite database.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Tuple
import logging
import time
import requests
from sqlalchemy import create_engine, text, MetaData, Table, Column, Date, Float, String, Integer, inspect

from .utils import (
    load_config, get_db_engine, ist_now, clean_nse_code, logger,
    format_percent, format_currency, safe_divide, safe_round
)

logger = logging.getLogger(__name__)


class DataFetcher:
    """Fetch market data from Dhan API or yfinance."""

    def __init__(self, config: dict = None):
        self.config = config or load_config()
        self.db_engine = get_db_engine(config=self.config)
        self._create_tables()
        self.session = requests.Session()
        self.dhan_token = None
        self.dhan_token_expiry = None

    def _create_tables(self):
        """Create database tables if not exist."""
        metadata = MetaData()

        # Market data table: daily OHLCV for each stock
        Table('market_data', metadata,
              Column('date', Date, primary_key=True),
              Column('symbol', String, primary_key=True),
              Column('open', Float),
              Column('high', Float),
              Column('low', Float),
              Column('close', Float),
              Column('volume', Integer),
              )

        # Index data table: Nifty and other indices
        Table('index_data', metadata,
              Column('date', Date, primary_key=True),
              Column('index_name', String, primary_key=True),
              Column('close', Float),
              Column('volume', Integer, nullable=True),
              )

        metadata.create_all(self.db_engine)
        logger.info("Database tables ensured")

    # ========== Dhan API Methods ==========

    def _get_dhan_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """Get or refresh Dhan access token."""
        if self.dhan_token and not force_refresh:
            # Check expiry (tokens usually valid 24h)
            return self.dhan_token

        client_id = self.config.get('dhan', {}).get('client_id')
        api_key = self.config.get('dhan', {}).get('api_key')
        secret = self.config.get('dhan', {}).get('secret')

        if not client_id or not api_key or not secret:
            logger.warning("Dhan credentials not configured")
            return None

        try:
            url = "https://api.dhan.co/v2/rest/oauth/access_token"
            payload = {
                "client_id": client_id,
                "client_secret": secret,
                "grant_type": "client_credentials"
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            resp = self.session.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.dhan_token = data.get('access_token')
                expires_in = data.get('expires_in', 86400)  # seconds
                self.dhan_token_expiry = datetime.now() + timedelta(seconds=expires_in - 3600)  # buffer
                logger.info("✅ Dhan access token obtained")
                return self.dhan_token
            else:
                logger.error(f"Dhan auth failed: {resp.status_code} - {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting Dhan token: {e}")
            return None

    def _dhan_headers(self) -> dict:
        """Get authenticated headers for Dhan API."""
        token = self._get_dhan_access_token()
        if not token:
            return {}
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }

    def fetch_dhan_historical(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "daily"  # "daily", "15min", "5min", "1min"
    ) -> pd.DataFrame:
        """
        Fetch historical data from Dhan API.

        symbol: Format "NSE:RELIANCE"
        interval: "daily" for EOD, "15min" for intraday
        Returns DataFrame with columns: date, open, high, low, close, volume
        """
        if not self.dhan_token:
            self._get_dhan_access_token()

        if not self.dhan_token:
            raise RuntimeError("Dhan not authenticated")

        # Map interval to Dhan format
        interval_map = {
            "daily": "EOD",
            "15min": "15",
            "5min": "5",
            "1min": "1"
        }
        dhan_interval = interval_map.get(interval, "EOD")

        url = "https://api.dhan.co/v2/charts/historical"
        payload = {
            "securityId": symbol,
            "exchangeSegment": "NSE_EQ",  # for NSE stocks
            "instrument": "EQUITY",
            "fromDate": start_date.strftime("%Y-%m-%d"),
            "toDate": end_date.strftime("%Y-%m-%d"),
            "interval": dhan_interval
        }

        try:
            resp = self.session.post(url, json=payload, headers=self._dhan_headers(), timeout=15)
            if resp.status_code != 200:
                logger.error(f"Dhan historical error {resp.status_code}: {resp.text[:200]}")
                return pd.DataFrame()

            data = resp.json()

            # Dhan returns: timestamp, open, high, low, close, volume
            if not data.get('data'):
                logger.warning(f"No data from Dhan for {symbol}")
                return pd.DataFrame()

            df = pd.DataFrame(data['data'])
            df['date'] = pd.to_datetime(df['timestamp'], unit='ms').dt.date
            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
            df['volume'] = df['volume'].astype(int)
            # Drop rows where close is NaN
            df = df.dropna(subset=['close'])
            df = df.sort_values('date')
            logger.debug(f"Fetched {len(df)} days for {symbol} from Dhan")
            return df

        except Exception as e:
            logger.error(f"Error fetching {symbol} from Dhan: {e}")
            return pd.DataFrame()

    # ========== Yahoo Finance Fallback ==========

    def fetch_yfinance_historical(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """Fetch data using yfinance library."""
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed. pip install yfinance")
            return pd.DataFrame()

        ticker = symbol.replace("NSE:", "") + ".NS"
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")  # inclusive

        try:
            df = yf.download(ticker, start=start_str, end=end_str, progress=False, timeout=10)
            if df.empty:
                logger.warning(f"No data from yfinance for {ticker}")
                return pd.DataFrame()

            # yfinance returns columns: Open, High, Low, Close, Adj Close, Volume
            df = df.reset_index()
            df['date'] = pd.to_datetime(df['Date']).dt.date
            df = df[['date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df['volume'] = df['volume'].fillna(0).astype(int)
            # Drop rows where close is NaN (e.g., non-trading days)
            df = df.dropna(subset=['close'])
            df = df.sort_values('date')
            logger.info(f"Fetched {len(df)} days for {symbol} via yfinance")
            return df
        except Exception as e:
            logger.error(f"yfinance error for {ticker}: {e}")
            return pd.DataFrame()

    # ========== Main Fetch Method ==========

    def fetch_historical(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "daily"
    ) -> pd.DataFrame:
        """
        Fetch historical data with fallback logic.
        Tries Dhan first, falls back to yfinance.
        """
        # Try Dhan if configured
        dhan_enabled = self.config.get('dhan', {}).get('client_id') and self.config.get('dhan', {}).get('access_token')
        if dhan_enabled:
            df = self.fetch_dhan_historical(symbol, start_date, end_date, interval)
            if not df.empty:
                return df
            logger.warning(f"Dhan failed for {symbol}, falling back to yfinance")

        # Fallback to yfinance
        df = self.fetch_yfinance_historical(symbol, start_date, end_date)
        return df

    def update_daily_data(self, symbols: List[str], date: date = None):
        """
        Fetch latest daily data for a list of symbols and update database.
        For daily scanner, we need the most recent day's OHLC.
        Uses UPSERT logic to avoid duplicates and only fetch missing dates.
        """
        if date is None:
            date = ist_now().date()

        logger.info(f"Updating daily data for {len(symbols)} symbols for {date}")

        # Get the latest date already in DB for each symbol (to fetch only new data)
        latest_dates = {}
        try:
            with self.db_engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT symbol, MAX(date) as latest_date
                    FROM market_data
                    GROUP BY symbol
                """))
                latest_dates = {row[0]: row[1] for row in result}
        except Exception as e:
            logger.warning(f"Could not fetch latest dates: {e}")

        success_count = 0
        for symbol in symbols:
            try:
                # Determine start date: fetch 10 days from latest date (or from 10 days ago if symbol not in DB)
                latest_date = latest_dates.get(symbol, date - timedelta(days=10))
                start_date = min(latest_date + timedelta(days=1), date - timedelta(days=10))
                # Ensure we don't fetch future dates
                end_date = min(date, ist_now().date())

                if start_date >= end_date:
                    logger.debug(f"{symbol}: already up to date (latest: {latest_date})")
                    continue

                df = self.fetch_historical(symbol, start_date, end_date)

                if df.empty:
                    logger.debug(f"No new data for {symbol} (market holiday?)")
                    continue

                # Drop any rows with NaN close (non-trading days)
                df = df.dropna(subset=['close'])

                if df.empty:
                    continue

                # Insert new data
                df['symbol'] = symbol
                with self.db_engine.connect() as conn:
                    df.to_sql('market_data', conn, if_exists='append', index=False)

                success_count += 1
                logger.info(f"Updated {symbol}: +{len(df)} rows (latest: {df['date'].max()})")

                time.sleep(0.5)  # rate limiting

            except Exception as e:
                logger.error(f"Failed to update {symbol}: {e}")

        logger.info(f"Daily update complete: {success_count}/{len(symbols)} symbols updated")
        return success_count

    def fetch_index_data(self, index_name: str = "NIFTY_50", years: int = 5) -> pd.DataFrame:
        """Fetch index data for beta calculation."""
        end_date = ist_now().date()
        start_date = date(end_date.year - years, end_date.month, end_date.day)

        # Try yfinance (NIFTY_50 = ^NSEI)
        try:
            import yfinance as yf
            ticker = "^NSEI" if index_name == "NIFTY_50" else index_name
            df = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), progress=False)
            if df.empty:
                return pd.DataFrame()
            df = df.reset_index()
            df['date'] = pd.to_datetime(df['Date']).dt.date
            df = df[['date', 'Close']].copy()
            df.columns = ['date', 'close']
            df['index_name'] = index_name
            df = df[['date', 'index_name', 'close']]

            # Delete existing data for this index to avoid duplicates
            with self.db_engine.connect() as conn:
                conn.execute(text("DELETE FROM index_data WHERE index_name = :idx"), {'idx': index_name})
                df.to_sql('index_data', conn, if_exists='append', index=False)

            logger.info(f"Fetched {len(df)} days of {index_name}")
            return df
        except Exception as e:
            logger.error(f"Error fetching index {index_name}: {e}")
            return pd.DataFrame()

    # ========== Data Reading ==========

    def get_data_for_symbol(self, symbol: str, start_date: date = None, end_date: date = None, days: int = None) -> pd.DataFrame:
        """Retrieve OHLC data for a symbol from database."""
        query = "SELECT * FROM market_data WHERE symbol = :symbol"
        params = {"symbol": symbol}

        if start_date:
            query += " AND date >= :start_date"
            params["start_date"] = start_date
        if end_date:
            query += " AND date <= :end_date"
            params["end_date"] = end_date

        query += " ORDER BY date"

        df = pd.read_sql(text(query), self.db_engine, params=params)
        if df.empty:
            return df

        if days:
            df = df.tail(days)

        return df

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the most recent closing price for a symbol."""
        query = text("SELECT close FROM market_data WHERE symbol = :symbol ORDER BY date DESC LIMIT 1")
        with self.db_engine.connect() as conn:
            result = conn.execute(query, {"symbol": symbol}).fetchone()
            return result[0] if result else None

    def get_index_data(self, index_name: str = "NIFTY_50", days: int = 252) -> pd.DataFrame:
        """Get index data from DB."""
        query = text("SELECT * FROM index_data WHERE index_name = :idx ORDER BY date DESC LIMIT :days")
        df = pd.read_sql(query, self.db_engine, params={"idx": index_name, "days": days})
        return df.sort_values('date')


def test_fetcher():
    """Test data fetcher functionality."""
    logger.info("Testing DataFetcher...")
    fetcher = DataFetcher()

    # Test fetch for 1 stock
    symbol = "NSE:RELIANCE"
    end = ist_now().date()
    start = end - timedelta(days=30)
    df = fetcher.fetch_historical(symbol, start, end)
    if not df.empty:
        print(f"\nSample data for {symbol}:")
        print(df.tail())
    else:
        print(f"No data fetched for {symbol}")

    return fetcher


if __name__ == "__main__":
    test_fetcher()
