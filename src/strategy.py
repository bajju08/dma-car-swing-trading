"""
Strategy Module – Core scoring and decision logic for DMA-DMA+CAR.

This module contains the rules for:
- Computing all scores
- Determining market regime
- Generating final signals (BUY/SELL/WAIT/REVERSE)
- Position sizing based on regime
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
import logging
from .utils import (
    load_config, get_db_engine, logger, format_currency, format_percent, safe_round
)
from .indicators import calculate_all_indicators, get_master_signal

logger = logging.getLogger(__name__)


class MarketRegime:
    """Classify market regime based on Nifty and stocks in Bull Run."""

    def __init__(self, nifty_status: str, bull_percentage: float, config: dict):
        self.nifty_status = nifty_status  # "In Bull Run", "In Bear Run", "Unconfirmed"
        self.bull_percentage = bull_percentage  # 0 to 1
        self.config = config

    def classify(self) -> str:
        """
        Classify overall regime:
        - FULL_BULL: Nifty Bull + >=15% stocks Bull
        - CAUTIOUS: Nifty Bull + 7-15% stocks Bull
        - REDUCED: Nifty Unconfirmed OR (Nifty Bull and <7% stocks Bull) OR (7-15% stocks Bull alone)
        - PAUSE: Nifty Bear OR <7% stocks Bull
        """
        thresholds = {
            'full': self.config['strategy']['bull_percentage_full'],
            'cautious': self.config['strategy']['bull_percentage_cautious']
        }

        if self.nifty_status == "In Bull Run":
            if self.bull_percentage >= thresholds['full']:
                return "FULL_BULL"
            elif self.bull_percentage >= thresholds['cautious']:
                return "CAUTIOUS"
            else:
                return "REDUCED"
        else:
            # Nifty Bear or Unconfirmed
            if self.bull_percentage >= thresholds['cautious']:
                return "REDUCED"  # stocks bullish but Nifty not confirming
            else:
                return "PAUSE"

    def get_position_size_multiplier(self) -> float:
        """Get position sizing multiplier (0 to 1)."""
        regime = self.classify()
        if regime == "FULL_BULL":
            return self.config['strategy']['position_size_full']
        elif regime == "CAUTIOUS":
            return self.config['strategy']['position_size_cautious']
        elif regime == "REDUCED":
            return self.config['strategy']['position_size_reduced']
        else:
            return 0.0  # PAUSE

    def can_trade(self, min_enhanced_score: int = None) -> bool:
        """
        Check if new trades are allowed based on regime and score thresholds.
        Even in PAUSE, you might still have scores high enough? No, PAUSE = no trades.
        """
        regime = self.classify()
        if regime == "PAUSE":
            return False
        return True


class TradeJournal:
    """Manage trade entries, averages, and P&L tracking."""

    def __init__(self, db_engine, config: dict):
        self.db_engine = db_engine
        self.config = config
        self._ensure_table()

    def _ensure_table(self):
        """Create trades table if not exists."""
        from sqlalchemy import MetaData, Table, Column, Date, Float, Integer, String, Boolean, Text
        metadata = MetaData()
        Table('trades', metadata,
              Column('id', Integer, primary_key=True, autoincrement=True),
              Column('chain', Integer),
              Column('slot', Integer),  # Row number in compounding chain
              Column('stock', String),
              Column('entry_date', Date),
              Column('entry_price', Float),
              Column('investment', Float),  # Total invested so far
              Column('target_price', Float),  # Based on current average
              Column('avg_reserve', Float),  # 50% of initial slot for future averages
              Column('avg_count', Integer, default=0),  # How many averages done
              Column('status', String),  # OPEN, CLOSED, REVIEW
              Column('profit_booked', Float, nullable=True),
              Column('close_date', Date, nullable=True),
              Column('days_held', Integer, nullable=True),
              Column('current_price', Float, nullable=True),
              Column('unrealized_pnl', Float, nullable=True),
              Column('avg_price', Float, nullable=True),  # Weighted average
              Column('notes', Text),
              Column('created_at', Date),
              Column('updated_at', Date),
              )
        metadata.create_all(self.db_engine)

    def add_trade(self, trade_data: dict) -> int:
        """
        Add a new trade.
        trade_data keys: chain, slot, stock, entry_date, entry_price, investment, target_price, avg_reserve, notes, etc.
        Returns: trade ID
        """
        # Set defaults
        trade_data.setdefault('avg_count', 0)
        trade_data.setdefault('avg_price', trade_data['entry_price'])
        trade_data.setdefault('status', 'OPEN')
        trade_data.setdefault('created_at', date.today())
        trade_data.setdefault('updated_at', date.today())

        # If target_price not provided, calculate from target_pct
        if 'target_price' not in trade_data:
            target_multiplier = 1 + self.config['strategy']['target_pct']
            trade_data['target_price'] = trade_data['entry_price'] * target_multiplier

        # Calculate avg_reserve if not provided: 50% of initial slot investment
        if 'avg_reserve' not in trade_data:
            initial_investment = trade_data['investment']
            trade_data['avg_reserve'] = initial_investment * 0.5

        # Insert into DB
        with self.db_engine.connect() as conn:
            df = pd.DataFrame([trade_data])
            df.to_sql('trades', conn, if_exists='append', index=False)
            trade_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            logger.info(f"Added trade #{trade_id}: {trade_data['stock']} on {trade_data['entry_date']}")
            return trade_id

    def get_open_trades(self) -> pd.DataFrame:
        """Fetch all open trades."""
        query = "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id"
        df = pd.read_sql(query, self.db_engine)
        return df

    def get_all_trades(self) -> pd.DataFrame:
        """Fetch all trades."""
        query = "SELECT * FROM trades ORDER BY id"
        df = pd.read_sql(query, self.db_engine)
        return df

    def update_prices(self, price_fetcher: callable):
        """
        Update current prices and P&L for all open trades.
        price_fetcher: function that takes symbol (NSE:SYMBOL) and returns latest close price.
        """
        open_trades = self.get_open_trades()
        if open_trades.empty:
            return

        for _, trade in open_trades.iterrows():
            symbol = trade['stock']
            try:
                current_price = price_fetcher(symbol)
                if current_price is None:
                    continue

                avg_price = trade['avg_price']
                unrealized_pnl = (current_price - avg_price) * (trade['investment'] / avg_price)  # approx shares
                days_held = (date.today() - trade['entry_date']).days

                # Update
                with self.db_engine.connect() as conn:
                    conn.execute(text("""
                        UPDATE trades
                        SET current_price = :cp,
                            unrealized_pnl = :upnl,
                            days_held = :days,
                            updated_at = :upd
                        WHERE id = :id
                    """), {
                        'cp': current_price,
                        'upnl': unrealized_pnl,
                        'days': days_held,
                        'upd': date.today(),
                        'id': trade['id']
                    })

            except Exception as e:
                logger.error(f"Error updating trade {trade['id']} ({symbol}): {e}")

    def add_average(self, trade_id: int, avg_date: date, avg_price: float, avg_amount: float):
        """
        Add an average to an existing trade.
        Recalculates avg_price and investment, and updates target.
        """
        with self.db_engine.connect() as conn:
            # Get current trade
            trade = conn.execute(text("SELECT * FROM trades WHERE id = :id"), {'id': trade_id}).fetchone()
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return

            # Compute new totals
            old_investment = trade['investment']
            old_avg_price = trade['avg_price']
            old_shares = old_investment / old_avg_price if old_avg_price else 0

            new_investment = old_investment + avg_amount
            new_shares = old_shares + (avg_amount / avg_price)
            new_avg_price = new_investment / new_shares if new_shares > 0 else avg_price

            # New target
            target_multiplier = 1 + self.config['strategy']['target_pct']
            new_target = new_avg_price * target_multiplier

            # Update
            conn.execute(text("""
                UPDATE trades
                SET investment = :inv,
                    avg_price = :avg,
                    target_price = :tgt,
                    avg_count = :cnt,
                    updated_at = :upd,
                    notes = :notes
                WHERE id = :id
            """), {
                'inv': new_investment,
                'avg': new_avg_price,
                'tgt': new_target,
                'cnt': trade['avg_count'] + 1,
                'upd': date.today(),
                'notes': f"Averaged on {avg_date}: ₹{avg_price:.2f} +₹{avg_amount:.0f}",
                'id': trade_id
            })

            logger.info(f"Trade {trade_id} averaged: new avg ₹{new_avg_price:.2f}, investment ₹{new_investment:.0f}")

    def close_trade(self, trade_id: int, close_date: date, profit: float, status_note: str = ""):
        """Mark trade as closed with profit."""
        with self.db_engine.connect() as conn:
            conn.execute(text("""
                UPDATE trades
                SET status = 'CLOSED',
                    profit_booked = :profit,
                    close_date = :cdate,
                    days_held = :days,
                    updated_at = :upd,
                    notes = :notes
                WHERE id = :id
            """), {
                'profit': profit,
                'cdate': close_date,
                'days': (close_date - date.today()).days * -1 if close_date > date.today() else (date.today() - close_date).days * -1,
                'upd': date.today(),
                'notes': f"CLOSED: {status_note}",
                'id': trade_id
            })
            logger.info(f"Closed trade #{trade_id}: profit ₹{profit}")

    def should_average(self, trade: pd.Series, current_price: float, car_signal: str, dma_status: str) -> Tuple[bool, str]:
        """
        Check if a trade qualifies for averaging.

        Rules:
        - Must be in Bull Run
        - Last average >= 7 days ago
        - Price >= 10% below entry price OR >= 2% below last average price
        - CAR = "Buy/Average Out"
        - Avg count < max (14)
        """
        if dma_status != "In Bull Run":
            return False, "Not in Bull Run"

        if car_signal != "Buy/Average Out":
            return False, "CAR not 'Buy/Average Out'"

        if trade['avg_count'] >= self.config['strategy']['avg_max_count']:
            return False, "Max averages reached"

        # Check weekly frequency (7 days since last average)
        # We need to store last_avg_date in trades table. Assuming we have it:
        last_avg_date = trade.get('last_avg_date', trade['entry_date'])
        days_since_avg = (date.today() - last_avg_date).days
        if days_since_avg < 7:
            return False, f"Only {days_since_avg} days since last average"

        # Price drop condition: either 10% from entry OR 2% from last avg
        entry_price = trade['entry_price']
        last_avg_price = trade['avg_price']

        drop_from_entry = (entry_price - current_price) / entry_price
        drop_from_last = (last_avg_price - current_price) / last_avg_price

        if drop_from_entry >= 0.10 or drop_from_last >= 0.02:
            return True, "Qualified"
        else:
            return False, f"Price drop insufficient (entry drop: {drop_from_entry:.1%}, last avg drop: {drop_from_last:.1%})"

    def check_exit_conditions(self, trade: pd.Series, dma_status: str, car_signal: str, days_in_bear: int) -> Optional[str]:
        """
        Check if exit conditions are met.
        Returns: "PROFIT_TARGET" or "HOPELESS" or None
        """
        current_price = trade['current_price']
        if pd.isna(current_price):
            return None

        # Profit target
        if current_price >= trade['target_price']:
            return "PROFIT_TARGET"

        # Hopeless conditions
        holding_days = trade['days_held']
        if holding_days and holding_days > self.config['strategy']['max_holding_days']:
            return "MAX_HOLD_TIME"

        if dma_status == "In Bear Run" and days_in_bear >= self.config['strategy']['exit_hopeless_days'] and car_signal == "Avoid/Hold":
            return "HOPELESS"

        return None


class StrategyEngine:
    """Main strategy engine that ties everything together."""

    def __init__(self, config: dict = None):
        self.config = config or load_config()
        self.db_engine = get_db_engine(config=self.config)
        self.trade_journal = TradeJournal(self.db_engine, self.config)

    def scan_universe(self, symbols: List[str], index_df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Scan all symbols and compute their indicator suite.
        Returns DataFrame with one row per symbol (latest date).
        """
        from .data_fetcher import DataFetcher
        fetcher = DataFetcher(self.config)

        results = []
        skipped = 0
        for symbol in symbols:
            try:
                # Get last 300 days of data (enough for 200 DMA)
                df = fetcher.get_data_for_symbol(symbol, days=300)
                if df.empty:
                    logger.info(f"{symbol}: SKIP - No data in DB")
                    skipped += 1
                    continue
                # Drop rows with NaN close (e.g., non-trading days)
                df = df.dropna(subset=['close'])
                if len(df) < 200:
                    logger.info(f"{symbol}: SKIP - Only {len(df)} days (<200 required)")
                    skipped += 1
                    continue

                # Calculate indicators
                indicators = calculate_all_indicators(df, index_df)
                if not indicators:
                    logger.info(f"{symbol}: SKIP - Indicators returned empty (len={len(df)}, latest close={df['close'].iloc[-1] if not df.empty else 'N/A'})")
                    skipped += 1
                    continue

                indicators['symbol'] = symbol
                results.append(indicators)

            except Exception as e:
                logger.info(f"{symbol}: SKIP - Exception: {e}")
                skipped += 1
                continue

        logger.info(f"Scan complete: {len(results)} succeeded, {skipped} skipped")
        scan_df = pd.DataFrame(results)
        return scan_df

    def compute_market_regime(self, scan_df: pd.DataFrame, index_df: pd.DataFrame = None) -> MarketRegime:
        """
        Determine overall market regime from scan results.

        Args:
            scan_df: DataFrame with stock signals
            index_df: Optional pre-fetched index data (for backtesting). Should have at least 'date' and 'close'.
                      If None, will query the latest from DB (for live scanner).
        """
        total_stocks = len(scan_df)
        if total_stocks == 0:
            bull_pct = 0.0
            nifty_status = "UNKNOWN"
        else:
            # Count stocks in Bull Run
            bull_count = (scan_df['dma_status'] == "In Bull Run").sum()
            bull_pct = bull_count / total_stocks

            # Determine Nifty status from index_data
            nifty_status = "Unconfirmed"
            try:
                if index_df is None:
                    # Query latest from DB (live mode)
                    nifty_df = pd.read_sql("""
                        SELECT * FROM index_data
                        WHERE index_name='NIFTY_50'
                        ORDER BY date DESC LIMIT 200
                    """, self.db_engine)
                else:
                    nifty_df = index_df.copy()

                if not nifty_df.empty:
                    nifty_series = nifty_df.sort_values('date')['close']
                    # Build a DataFrame with synthetic OHLC for calculate_all_indicators
                    nifty_input = pd.DataFrame({
                        'date': nifty_df['date'],
                        'close': nifty_series,
                        'open': nifty_series,
                        'high': nifty_series,
                        'low': nifty_series,
                        'volume': 0  # index has no volume, but calculate_all_indicators handles gracefully
                    })
                    nifty_indicators = calculate_all_indicators(nifty_input)
                    nifty_status = nifty_indicators.get('dma_status', 'Unconfirmed')
            except Exception as e:
                logger.warning(f"Could not determine Nifty status: {e}")

        regime = MarketRegime(nifty_status, bull_pct, self.config)
        return regime

    def filter_and_rank_recommendations(self, scan_df: pd.DataFrame, regime: MarketRegime) -> pd.DataFrame:
        """
        Apply filters and produce ranked list of buy recommendations.
        """
        # Filter by minimum scores from config
        min_enhanced = self.config['strategy']['min_enhanced_score']
        min_speed = self.config['strategy']['min_speed_score']
        min_beta = self.config['strategy']['beta_min']

        # Also consider regime-based thresholds
        regime_class = regime.classify()
        if regime_class == "FULL_BULL":
            pass  # use configured minimums
        elif regime_class == "CAUTIOUS":
            min_enhanced = max(min_enhanced, 9)  # stricter
            min_speed = max(min_speed, 5)
        elif regime_class == "REDUCED":
            min_enhanced = max(min_enhanced, 10)  # even stricter
            min_speed = max(min_speed, 6)
        else:  # PAUSE
            return pd.DataFrame()  # no new trades

        # Filter
        filtered = scan_df[
            (scan_df['master_signal'].isin(['PRIME FAST', 'PRIME BUY', 'BUY'])) &
            (scan_df['enhanced_score'] >= min_enhanced) &
            (scan_df['speed_score'] >= min_speed) &
            (scan_df['beta'] >= min_beta) &
            (scan_df['rsi_14'] < 70)  # not overbought
        ].copy()

        if filtered.empty:
            return pd.DataFrame()

        # Rank
        filtered['rank'] = (
            -filtered['enhanced_score'] * 2 +
            -filtered['speed_score'] +
            (filtered['master_signal'] == 'PRIME FAST').astype(int) * 5 +
            (filtered['master_signal'] == 'PRIME BUY').astype(int) * 3 +
            (filtered['dma_status'] == 'In Bull Run').astype(int) * 2
        )

        # Sort: master signal priority, then enhanced score, then speed score
        signal_order = {'PRIME FAST': 0, 'PRIME BUY': 1, 'BUY': 2}
        filtered['signal_rank'] = filtered['master_signal'].map(signal_order)
        filtered = filtered.sort_values(['signal_rank', 'enhanced_score', 'speed_score'], ascending=[True, False, False])

        # Add recommended investment based on regime
        base_investment = self.config['strategy']['chain_start_capital']
        pos_mult = regime.get_position_size_multiplier()
        filtered['recommended_investment'] = base_investment * pos_mult

        return filtered

    def generate_daily_recommendations(self, symbols: list = None) -> dict:
        """
        Main entry point: run full scan and produce recommendations.
        Returns a dict with regime info, top picks, and full list.

        Args:
            symbols: Optional list of symbols to scan. If None, loads from config file.
        """
        logger.info("Starting daily recommendation scan...")

        # 1. Load stock universe
        if symbols is None:
            from .utils import parse_nse_codes_from_file
            symbols = parse_nse_codes_from_file(self.config['data']['nifty_500_file'])
        logger.info(f"Loaded {len(symbols)} symbols to scan")

        # 2. Fetch index data (once)
        from .data_fetcher import DataFetcher
        fetcher = DataFetcher(self.config)
        index_df = fetcher.get_index_data(days=300)
        if index_df.empty:
            logger.warning("No Nifty data found, fetching...")
            index_df = fetcher.fetch_index_data(years=5)

        # 3. Scan all stocks
        scan_df = self.scan_universe(symbols, index_df)
        logger.info(f"Scanned {len(scan_df)} symbols with complete data")

        # 4. Market regime
        regime = self.compute_market_regime(scan_df)
        regime_class = regime.classify()
        position_multiplier = regime.get_position_size_multiplier()
        logger.info(f"Market Regime: {regime_class} (Nifty: {regime.nifty_status}, Bull %: {regime.bull_percentage:.1%}), Position Size: {position_multiplier:.0%}")

        # 5. Filter and rank
        recommendations = self.filter_and_rank_recommendations(scan_df, regime)
        logger.info(f"Filtered to {len(recommendations)} recommendations")

        # 6. Prepare output
        output = {
            'date': datetime.now().date().isoformat(),
            'market_regime': {
                'classification': regime_class,
                'nifty_status': regime.nifty_status,
                'bull_percentage': round(regime.bull_percentage, 4),
                'position_multiplier': round(position_multiplier, 2)
            },
            'top_picks': recommendations.head(20).to_dict(orient='records'),
            'all_recommendations': recommendations.to_dict(orient='records'),
            'total_scan': len(scan_df),
            'total_qualified': len(recommendations)
        }

        return output


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    engine = StrategyEngine()
    recs = engine.generate_daily_recommendations()
    print("\nDaily Recommendations:")
    print(f"Regime: {recs['market_regime']['classification']}")
    print(f"Top picks: {len(recs['top_picks'])}")
    for i, pick in enumerate(recs['top_picks'][:5], 1):
        print(f"  {i}. {pick['symbol']} - {pick['master_signal']} (Score: {pick['enhanced_score']}/15, Speed: {pick['speed_score']}/10)")
