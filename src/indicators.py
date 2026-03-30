"""
Technical Indicators Module

Implements all indicators used in DMA-DMA+CAR strategy:
- DMA (50, 100, 200) – Done
- RSI (14) – Done
- CAR signal (cumulative average check) – Done
- Volume Ratio – Done
- Beta (vs Nifty) – Done
- Relative Strength (vs Nifty, 1-month) – Done
- 52-week high proximity & range position – Done
- ADX (optional enhancement) – Done
- ATR (for reference) – Done
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import logging
from .utils import safe_round

logger = logging.getLogger(__name__)


def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return prices.rolling(window=period).mean()


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return prices.ewm(span=period, adjust=False).mean()


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI (Relative Strength Index)."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range.
    df must have columns: high, low, close
    """
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(window=period).mean()
    return atr


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate ADX (Average Directional Index).
    Requires high, low, close.
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # +DM and -DM
    plus_dm = high.diff()
    minus_dm = low.diff()
    plus_dm = plus_dm.where(plus_dm > 0, 0)
    minus_dm = minus_dm.where(minus_dm < 0, 0).abs()

    # TR
    tr = calculate_atr(df, period)

    # Smoothed +DM and -DM
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr.replace(0, np.nan))

    # DX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(window=period).mean()
    return adx


def calculate_car_signal(df: pd.DataFrame, lookback: int = 10) -> pd.Series:
    """
    Calculate CAR (Cumulative Average Ratio) signal.

    Logic (from Google Sheets formula):
    For each day, compute cumulative average of close prices up to that day.
    Check if the last 'lookback' cumulative averages are strictly increasing.
    If yes → "Buy/Average Out"
    If not → "Avoid/Hold"

    Implementation:
    1. Compute cumulative average series: cum_avg[i] = mean(close[0:i+1])
    2. For today: check if cum_avg[-lookback:] are strictly increasing
    3. Return 2 points for Buy/Average Out, 0 for Avoid

    Returns: Series with values: "Buy/Average Out" or "Avoid/Hold"
    Or numeric: 2 or 0 for point calculation.
    """
    if len(df) < lookback:
        return pd.Series("Avoid/Hold", index=df.index)

    close = df['close']
    # Cumulative average: for each row i, average of all closes up to i
    cum_avg = close.expanding().mean()

    # Check if last 'lookback' cumulative averages are strictly increasing
    last_n = cum_avg.tail(lookback).values
    is_strictly_increasing = all(last_n[i] > last_n[i-1] for i in range(1, len(last_n)))

    signal = "Buy/Average Out" if is_strictly_increasing else "Avoid/Hold"

    # Return a series with same value for all rows? Actually we only need latest
    # But for batch processing we compute for each day. For now, return just latest.
    logger.debug(f"CAR signal: lookback={lookback}, increasing={is_strictly_increasing}")
    return signal


def calculate_beta(
    stock_returns: pd.Series,
    index_returns: pd.Series,
    window: int = 100
) -> pd.Series:
    """
    Calculate rolling beta: Cov(stock, index) / Var(index).
    Align both series by date, then compute rolling beta.
    """
    # Ensure same index
    aligned = pd.concat([stock_returns, index_returns], axis=1, join='inner')
    aligned.columns = ['stock_ret', 'index_ret']

    if len(aligned) < window:
        return pd.Series(np.nan, index=aligned.index)

    # Rolling covariance and variance
    rolling_cov = aligned['stock_ret'].rolling(window).cov(aligned['index_ret'])
    rolling_var = aligned['index_ret'].rolling(window).var()

    beta = rolling_cov / rolling_var
    return beta


def calculate_volume_ratio(df: pd.DataFrame, volume_period: int = 20) -> pd.Series:
    """
    Volume Ratio = Today's Volume / Average Volume (over volume_period days)
    """
    avg_volume = df['volume'].rolling(window=volume_period).mean()
    volume_ratio = df['volume'] / avg_volume
    return volume_ratio


def calculate_relative_strength(
    stock_prices: pd.Series,
    index_prices: pd.Series,
    period_days: int = 22  # ~1 month
) -> pd.Series:
    """
    Relative Strength vs Nifty over 1-month.
    RS = (P_today / P_past) - 1
    """
    if len(stock_prices) < period_days + 1:
        return pd.Series(np.nan, index=stock_prices.index)

    stock_ret = (stock_prices / stock_prices.shift(period_days)) - 1
    index_ret = (index_prices / index_prices.shift(period_days)) - 1
    rs = stock_ret - index_ret  # relative strength difference
    return rs


def calculate_52week_stats(df: pd.DataFrame) -> Tuple[float, float, str]:
    """
    Calculate 52-week high proximity and range position.

    Returns:
        pct_from_high: % below 52-week high (negative number if below)
        range_position: % of 52-week range from bottom (0-100)
        zone: "AT HIGH", "UPPER", "MID", "DEEP RECOVERY"
    """
    if len(df) < 252:  # not enough data
        return np.nan, np.nan, "UNKNOWN"

    one_year = min(252, len(df))
    df_52w = df.tail(one_year)
    high_52 = df_52w['high'].max()
    low_52 = df_52w['low'].min()

    current_close = df['close'].iloc[-1]

    pct_from_high = (current_close - high_52) / high_52 * 100  # negative means below

    # Range position percentage (0% = at low, 100% = at high)
    if high_52 == low_52:
        range_pos = 50.0
    else:
        range_pos = (current_close - low_52) / (high_52 - low_52) * 100

    # Zone classification
    if current_close >= high_52 * 0.95:  # within -5% of high
        zone = "AT HIGH"
    elif current_close >= high_52 * 0.80:
        zone = "UPPER"
    elif current_close >= high_52 * 0.60:
        zone = "MID"
    else:
        zone = "DEEP RECOVERY"

    return pct_from_high, range_pos, zone


def calculate_ema_features(df: pd.DataFrame) -> dict:
    """
    Evaluate EMA order and slope for market regime classification.
    Returns:
        golden: bool (50>100>200)
        inverted: bool (50<100<200)
        dma_status: "Bull Run", "Bear Run", "Unconfirmed"
    """
    if len(df) < 200:
        return {"golden": False, "inverted": False, "status": "UNKNOWN"}

    latest = df.iloc[-1]
    ma50 = latest.get('ma50', np.nan)
    ma100 = latest.get('ma100', np.nan)
    ma200 = latest.get('ma200', np.nan)
    cmp = latest.get('close', np.nan)

    if pd.isna(ma50) or pd.isna(ma100) or pd.isna(ma200):
        return {"golden": False, "inverted": False, "status": "UNKNOWN"}

    golden = (ma50 > ma100) and (ma100 > ma200)
    inverted = (ma50 < ma100) and (ma100 < ma200)

    # DMA Status based on price vs DMAs
    if cmp > ma50 and cmp > ma100 and cmp > ma200:
        status = "In Bull Run"
    elif cmp < ma50 and cmp < ma100 and cmp < ma200:
        status = "In Bear Run"
    else:
        status = "Unconfirmed"

    return {
        "golden": golden,
        "inverted": inverted,
        "status": status
    }


def calculate_all_indicators(
    df: pd.DataFrame,
    index_df: pd.DataFrame = None
) -> dict:
    """
    Calculate all required indicators for a stock's OHLC data.

    Args:
        df: DataFrame with columns: date, open, high, low, close, volume
        index_df: Nifty index DataFrame for beta & RS (optional)

    Returns:
        Dict with all indicator values for the latest date.
    """
    if len(df) < 200:
        return {}  # Not enough data

    # Sort by date
    df = df.sort_values('date').copy()

    # Calculate DMAs
    df['ma50'] = calculate_sma(df['close'], 50)
    df['ma100'] = calculate_sma(df['close'], 100)
    df['ma200'] = calculate_sma(df['close'], 200)

    # Get latest values
    latest = df.iloc[-1]

    # DMA Status
    cmp = latest['close']
    ma50 = latest['ma50']
    ma100 = latest['ma100']
    ma200 = latest['ma200']

    if pd.isna(ma200):
        return {}  # Not ready

    pct_from_200 = (cmp - ma200) / ma200 * 100

    # Golden DMA flag
    golden = (ma50 > ma100) and (ma100 > ma200)

    # DMA Status
    if cmp > ma50 and cmp > ma100 and cmp > ma200:
        dma_status = "In Bull Run"
    elif cmp < ma50 and cmp < ma100 and cmp < ma200:
        dma_status = "In Bear Run"
    else:
        dma_status = "Unconfirmed"

    # Conviction Score components
    pts_golden = 3 if golden else 0
    # Distance from 200 DMA: 3-12% = 4 pts; 0-3% = 2 pts
    if 3 <= pct_from_200 <= 12:
        pts_distance = 4
    elif 0 <= pct_from_200 < 3:
        pts_distance = 2
    else:
        pts_distance = 0

    # Data Integrity: all 3 DMAs distinct and non-zero
    data_ok = 1 if (ma50 > 0 and ma100 > 0 and ma200 > 0 and ma50 != ma100 != ma200) else 0

    # CAR Signal
    car_signal = calculate_car_signal(df)

    pts_car = 2 if car_signal == "Buy/Average Out" else 0

    # Original Conviction Score (0-10)
    conviction_score = pts_golden + pts_distance + pts_car + data_ok

    # Enhanced Filters (0-5)
    # Volume Ratio (1 pt) – only if 'volume' column exists
    vol_ratio = np.nan
    volume_score = 0
    if 'volume' in df.columns and len(df) >= 20:
        vol_ratio = calculate_volume_ratio(df).iloc[-1]
        volume_score = 1 if vol_ratio >= 1.2 else 0

    # Beta (1 pt) – will compute from index data if available
    beta = np.nan
    beta_score = 0
    beta_signal = "N/A"
    if index_df is not None and len(index_df) >= 100:
        try:
            # Align dates
            merged = pd.merge(df[['date', 'close']], index_df[['date', 'close']], on='date', how='inner', suffixes=('_stock', '_index'))
            if len(merged) >= 100:
                stock_ret = merged['close_stock'].pct_change().tail(100)
                index_ret = merged['close_index'].pct_change().tail(100)
                beta = calculate_beta(stock_ret, index_ret, window=60).iloc[-1]
                if not pd.isna(beta):
                    if beta >= 1.2:
                        beta_score = 3
                        beta_signal = "FAST"
                    elif beta >= 0.9:
                        beta_score = 2
                        beta_signal = "MEDIUM"
                    elif beta >= 0.6:
                        beta_score = 1
                        beta_signal = "SLOW"
                    else:
                        beta_score = 0
                        beta_signal = "SLOW"
        except Exception as e:
            logger.debug(f"Beta calculation error: {e}")

    # Relative Strength (1 month vs Nifty)
    rs_pct = np.nan
    rs_score = 0
    rs_signal = "N/A"
    if index_df is not None and len(df) >= 22:
        try:
            merged = pd.merge(df[['date', 'close']], index_df[['date', 'close']], on='date', how='inner', suffixes=('_stock', '_index'))
            if len(merged) >= 22:
                stock_prices = merged['close_stock']
                index_prices = merged['close_index']
                rs_series = calculate_relative_strength(stock_prices, index_prices, period_days=22)
                rs_pct = rs_series.iloc[-1] * 100 if not pd.isna(rs_series.iloc[-1]) else np.nan
                if rs_pct > 5:
                    rs_score = 2
                    rs_signal = "STRONG RS"
                elif rs_pct > 0:
                    rs_score = 1
                    rs_signal = "MILD RS"
                else:
                    rs_score = 0
                    rs_signal = "WEAK RS"
        except Exception as e:
            logger.debug(f"RS calculation error: {e}")

    # 52-week stats
    pct_from_52wk_high = np.nan
    range_pos = np.nan
    zone_52wk = "UNKNOWN"
    zone_score = 0
    if len(df) >= 252:
        pct_from_52wk_high, range_pos, zone_52wk = calculate_52week_stats(df)
        if zone_52wk == "AT HIGH" or zone_52wk == "UPPER":
            zone_score = 1
        else:
            zone_score = 0

    # EPS Check – placeholder (would need fundamental data source)
    eps_ok = 1  # assume positive; later integrate with Screener.in API or similar

    # Enhanced Score (0-15)
    enhanced_score = conviction_score + volume_score + beta_score + rs_score + zone_score + eps_ok

    # Speed Score (0-10) – derived from enhanced components
    # Formula: (Beta Score 0-3) + (Volume Score 0-3) + (RS Score 0-2) + (Zone Score 0-2) mapped to 0-10
    speed_score = int((beta_score / 3 + volume_score / 3 + rs_score / 2 + zone_score / 2) * 10)

    # Master Signal
    master_signal = get_master_signal(
        enhanced_score=enhanced_score,
        speed_score=speed_score,
        dma_status=dma_status
    )

    # Additional indicators
    rsi_14 = calculate_rsi(df['close'], 14).iloc[-1] if len(df) >= 14 else np.nan
    atr = calculate_atr(df, 14).iloc[-1] if len(df) >= 14 else np.nan
    atr_pct = (atr / cmp * 100) if not pd.isna(atr) and cmp else np.nan

    return {
        # Current values
        'cmp': cmp,
        'ma50': ma50,
        'ma100': ma100,
        'ma200': ma200,
        'pct_from_200': safe_round(pct_from_200, 2),

        # DMA Status
        'dma_status': dma_status,
        'golden_dma': golden,
        'golden_dma_str': "✓ True" if golden else "✗ False",

        # Conviction Score (0-10)
        'pts_golden': pts_golden,
        'pts_distance': pts_distance,
        'pts_car': pts_car,
        'data_ok': data_ok,
        'conviction_score': conviction_score,

        # CAR
        'car_signal': car_signal,

        # Enhanced Filters
        'volume_ratio': safe_round(vol_ratio, 2) if not pd.isna(vol_ratio) else None,
        'volume_signal': "HIGH VOL" if vol_ratio >= 1.5 else ("OK VOL" if vol_ratio >= 1.2 else "LOW VOL"),
        'beta': safe_round(beta, 2) if not pd.isna(beta) else None,
        'beta_signal': beta_signal,
        'beta_score': beta_score,
        'rs_pct': safe_round(rs_pct, 2) if not pd.isna(rs_pct) else None,
        'rs_signal': rs_signal,
        'rs_score': rs_score,
        'pct_from_52wk_high': safe_round(pct_from_52wk_high, 2) if not pd.isna(pct_from_52wk_high) else None,
        'range_pos': safe_round(range_pos, 1) if not pd.isna(range_pos) else None,
        'zone_52wk': zone_52wk,
        'zone_score': zone_score,
        'eps_ok': eps_ok,

        # Totals
        'enhanced_score': enhanced_score,
        'speed_score': speed_score,
        'master_signal': master_signal,

        # Technicals
        'rsi_14': safe_round(rsi_14, 1) if not pd.isna(rsi_14) else None,
        'atr': safe_round(atr, 2) if not pd.isna(atr) else None,
        'atr_pct': safe_round(atr_pct, 2) if not pd.isna(atr_pct) else None,
    }


def get_master_signal(enhanced_score: int, speed_score: int, dma_status: str, config: dict = None) -> str:
    """
    Determine final Master Signal based on enhanced score, speed, and market regime.

    Logic:
    - If Bear Run → "REVERSE TRADE"
    - If Unconfirmed → "WAIT"
    - If Bull Run:
        - Enhanced ≥13 AND Speed ≥7 → "PRIME FAST"
        - Enhanced ≥10 AND Speed ≥4 → "PRIME BUY"
        - Enhanced ≥8 → "BUY"
        - Enhanced 6-7 → "WATCH"
        - Enhanced <6 → "SKIP"
    """
    if dma_status == "In Bear Run":
        return "REVERSE TRADE"
    elif dma_status == "Unconfirmed":
        return "WAIT"

    # Bull Run
    if enhanced_score >= 13 and speed_score >= 7:
        return "PRIME FAST"
    elif enhanced_score >= 10 and speed_score >= 4:
        return "PRIME BUY"
    elif enhanced_score >= 8:
        return "BUY"
    elif enhanced_score >= 6:
        return "WATCH"
    else:
        return "SKIP"


def calculate_conviction_score(row: dict) -> int:
    """
    Given a row (from DB or scan), compute Conviction Score (0-10).
    Convenience wrapper using calculate_all_indicators output.
    """
    return row.get('conviction_score', 0)


if __name__ == "__main__":
    # Quick test with sample data
    print("Testing indicators module...")

    # Create dummy data
    dates = pd.date_range(end=datetime.now(), periods=300, freq='D')
    np.random.seed(42)
    close = 100 + np.random.randn(300).cumsum() * 0.5
    df = pd.DataFrame({
        'date': [d.date() for d in dates],
        'open': close * (1 + np.random.randn(300) * 0.01),
        'high': close * (1 + abs(np.random.randn(300) * 0.02)),
        'low': close * (1 - abs(np.random.randn(300) * 0.02)),
        'close': close,
        'volume': np.random.randint(100000, 1000000, 300)
    })

    result = calculate_all_indicators(df)
    print("\nIndicator outputs:")
    for k, v in result.items():
        if v not in [None, np.nan]:
            print(f"  {k}: {v}")
