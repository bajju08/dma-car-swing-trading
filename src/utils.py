"""
Utility functions for DMA-DMA+CAR trading platform.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
import pytz
import yaml
import os
from pathlib import Path
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Constants
IST = pytz.timezone('Asia/Kolkata')
NSE_HOLIDAYS = []  # Could load from calendar


def load_config(config_path: str = "config_local.yaml") -> dict:
    """Load configuration from YAML file, with environment variable overrides."""
    if not os.path.exists(config_path):
        # Fall back to template
        template = "config.yaml"
        if os.path.exists(template):
            logger.warning(f"{config_path} not found, using {template} as template")
            config_path = template
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Override with environment variables (for Docker/deployment)
    # Format: SECTION__KEY (e.g., DHAN__CLIENT_ID)
    for section in config:
        if isinstance(config[section], dict):
            for key in config[section]:
                env_var = f"{section.upper()}__{key.upper()}"
                if env_var in os.environ:
                    config[section][key] = os.environ[env_var]

    return config


def get_db_engine(db_path: str = None, config: dict = None):
    """Create SQLAlchemy engine for database."""
    if db_path is None:
        if config is None:
            config = load_config()
        db_path = config['data']['db_path']

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    return engine


def ist_now() -> datetime:
    """Current time in IST timezone."""
    return datetime.now(IST)


def market_close_time() -> datetime:
    """Return today's market close time (3:30 PM IST) as datetime."""
    today = date.today()
    return datetime.combine(today, datetime.min.time()).replace(hour=15, minute=30, tzinfo=IST)


def is_market_day(dt: datetime) -> bool:
    """Check if a date is a trading day (Mon-Fri, not holiday)."""
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    # TODO: add holiday check
    return True


def next_market_day(dt: datetime) -> datetime:
    """Return next trading day."""
    next_day = dt + timedelta(days=1)
    while not is_market_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def calculate_cagr(initial: float, final: float, years: float) -> float:
    """Calculate Compound Annual Growth Rate."""
    if initial <= 0 or final <= 0:
        return 0.0
    return (final / initial) ** (1 / years) - 1


def format_currency(value: float, currency: str = "₹") -> str:
    """Format number as currency string."""
    if abs(value) >= 10000000:
        return f"{currency}{value/10000000:.2f} Cr"
    elif abs(value) >= 100000:
        return f"{currency}{value/100000:.2f} L"
    elif abs(value) >= 1000:
        return f"{currency}{value:,.0f}"
    else:
        return f"{currency}{value:.2f}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format number as percentage."""
    return f"{value*100:.{decimals}f}%"


def read_csv_auto(filepath: str, **kwargs) -> pd.DataFrame:
    """Read CSV with proper encoding detection."""
    encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
    for enc in encodings:
        try:
            df = pd.read_csv(filepath, encoding=enc, **kwargs)
            logger.info(f"Read {filepath} with {enc} encoding")
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {filepath} with any encoding")


def clean_nse_code(ticker: str) -> str:
    """Ensure NSE code format: NSE:SYMBOL"""
    if ticker.startswith('NSE:'):
        return ticker
    return f"NSE:{ticker}"


def parse_nse_codes_from_file(filepath: str, column: str = "Ticker") -> list:
    """Read NSE codes from CSV file."""
    df = read_csv_auto(filepath)
    if column not in df.columns:
        # Try first column
        column = df.columns[0]
    codes = df[column].dropna().astype(str).tolist()
    # Clean and format
    codes = [clean_nse_code(c.strip()) for c in codes if c.strip()]
    return codes


def rolling_window(arr: np.ndarray, window: int) -> np.ndarray:
    """Create rolling windows for time series."""
    shape = (arr.shape[0] - window + 1, window)
    strides = (arr.strides[0], arr.strides[0])
    return np.lib.stride_tricks.as_strided(arr, shape=shape, strides=strides)


def calculate_max_drawdown(returns: pd.Series) -> float:
    """Calculate maximum drawdown from returns series."""
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()


def calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.06) -> float:
    """Annualized Sharpe ratio (assuming daily returns)."""
    excess_returns = returns - (risk_free_rate / 252)
    if excess_returns.std() == 0:
        return 0.0
    return excess_returns.mean() / excess_returns.std() * np.sqrt(252)


def calculate_sortino(returns: pd.Series, risk_free_rate: float = 0.06, target_return: float = 0.0) -> float:
    """Annualized Sortino ratio."""
    excess_returns = returns - (risk_free_rate / 252)
    downside_returns = excess_returns[excess_returns < target_return]
    if len(downside_returns) == 0:
        return np.inf
    downside_deviation = np.sqrt((downside_returns ** 2).mean())
    if downside_deviation == 0:
        return 0.0
    return excess_returns.mean() / downside_deviation * np.sqrt(252)


def format_timedelta(days: int) -> str:
    """Format days into human readable string."""
    if days < 30:
        return f"{days} days"
    months = days // 30
    remaining_days = days % 30
    if remaining_days == 0:
        return f"{months} month{'s' if months > 1 else ''}"
    return f"{months}mo {remaining_days}d"


def validate_stock_universe(tickers: list) -> list:
    """Validate and clean stock ticker list."""
    cleaned = []
    for t in tickers:
        t = str(t).strip()
        if not t or t.lower() in ['nan', 'none', 'null']:
            continue
        # Remove any whitespace
        t = t.replace(' ', '')
        # Ensure NSE: prefix
        if not t.startswith('NSE:'):
            t = f"NSE:{t}"
        cleaned.append(t)
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for t in cleaned:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safe division handling division by zero."""
    if b == 0:
        return default
    return a / b


def safe_round(value: float, decimals: int = 2) -> float:
    """Safely round a number, handling NaN/None."""
    if pd.isna(value) or value is None:
        return np.nan
    return round(value, decimals)


if __name__ == "__main__":
    # Test utilities
    print("Testing utilities...")
    cfg = load_config()
    print(f"Config loaded: {cfg['strategy']['target_pct']}")
    print(f"Format 15000: {format_currency(15000)}")
    print(f"Format 1234567: {format_currency(1234567)}")
    print(f"Format 0.0628: {format_percent(0.0628)}")
