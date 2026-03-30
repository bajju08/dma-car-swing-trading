"""
Backtesting Engine – Historical simulation of DMA-DMA+CAR strategy.

Features:
- Daily scanning simulation
- Entry/exit logic with transaction costs
- Regime-based position sizing
- Chain compounding model
- Comprehensive performance metrics

Usage:
    python backtest.py --start 2021-01-01 --end 2025-12-31 --capital 150000 --symbols-file nifty500.csv
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple
import logging
import json
from sqlalchemy import text

from .utils import load_config, get_db_engine, logger
from .strategy import StrategyEngine
from .indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


class Backtester:
    """
    Walk-forward backtest with realistic assumptions:
    - Scans each day using data up to previous day
    - Enters top N signals each day (limit by capital)
    - Exits at profit target (6.28%) OR stop loss (10%) OR max hold (180 days)
    - Tracks all trades with P&L
    """

    def __init__(self, config: dict = None, initial_capital: float = 150000):
        self.config = config or load_config()
        self.initial_capital = initial_capital
        self.db_engine = get_db_engine(config=self.config)
        self.strategy_engine = StrategyEngine(self.config)
        self.fetcher = None  # will be from data_fetcher

        # Backtest parameters
        self.max_positions = 10  # max concurrent positions
        self.position_size_pct = 0.10  # 10% of capital per position
        self.min_confidence = 8  # minimum enhanced_score to enter

    def load_index_data(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Load Nifty index data for market regime."""
        query = text("""
            SELECT date, close FROM index_data
            WHERE index_name = 'NIFTY_50' AND date BETWEEN :start AND :end
            ORDER BY date
        """)
        df = pd.read_sql(query, self.db_engine, params={'start': start_date, 'end': end_date})
        return df

    def get_scan_date_signals(self, scan_date: date, symbols: List[str]) -> pd.DataFrame:
        """
        For a given date, compute signals for all symbols using data up to that date.
        Returns DataFrame with signal info for each symbol.
        """
        # Get index data up to scan_date (need 200 days)
        index_start = scan_date - timedelta(days=300)
        index_df = self.load_index_data(index_start, scan_date)

        results = []
        for symbol in symbols:
            # Get stock data up to scan_date
            df_query = text("""
                SELECT * FROM market_data
                WHERE symbol = :symbol AND date <= :scan_date
                ORDER BY date
                LIMIT 300
            """)
            df = pd.read_sql(df_query, self.db_engine, params={'symbol': symbol, 'scan_date': scan_date})

            if len(df) < 200:
                continue

            try:
                # Calculate indicators
                indicators = calculate_all_indicators(df, index_df if not index_df.empty else None)
                if indicators and indicators.get('enhanced_score', 0) >= self.min_confidence:
                    indicators['symbol'] = symbol
                    results.append(indicators)
            except Exception as e:
                logger.debug(f"Error calculating {symbol} on {scan_date}: {e}")
                continue

        if not results:
            return pd.DataFrame()

        scan_df = pd.DataFrame(results)

        # Compute market regime using index data
        try:
            regime = self.strategy_engine.compute_market_regime(scan_df)
            regime_class = regime.classify()
            position_multiplier = regime.get_position_size_multiplier()
        except:
            regime_class = "PAUSE"
            position_multiplier = 0.0

        # Filter and rank by regime
        filtered = self.strategy_engine.filter_and_rank_recommendations(scan_df, regime)

        return filtered, regime_class, position_multiplier

    def calculate_transaction_cost(self, trade_value: float) -> float:
        """
        Calculate total transaction cost including:
        - Brokerage (0.247% both sides - from config)
        - STT (0.1% for delivery)
        - GST on brokerage (18%)
        - SEBI charges, stamp duty (~0.003%)
        """
        brokerage = trade_value * self.config['strategy']['brokerage_pct'] / 100
        stt = trade_value * 0.001  # 0.1% Securities Transaction Tax
        gst = brokerage * 0.18  # 18% GST on brokerage
        sebi = trade_value * 0.000001  # SEBI charge ~0.0001%
        stamp = trade_value * 0.0001  # Stamp duty ~0.01%

        total = brokerage + stt + gst + sebi + stamp
        return total

    def _get_top_symbols_by_volume(self, as_of_date: date, limit: int = 100) -> List[str]:
        """Get top N symbols by recent average volume (for backtest speed)."""
        # Get the most recent trading day before as_of_date
        query = text("""
            SELECT symbol, AVG(volume) as avg_vol
            FROM market_data
            WHERE date >= date(:as_of, '-30 days') AND date <= :as_of
            GROUP BY symbol
            ORDER BY avg_vol DESC
            LIMIT :limit
        """)
        with self.db_engine.connect() as conn:
            result = conn.execute(query, {'as_of': as_of_date, 'limit': limit})
            symbols = [row[0] for row in result]
        return symbols

    def _scan_symbols(self, symbols: List[str], scan_date: date) -> pd.DataFrame:
        """
        Calculate indicators for a list of symbols as of scan_date.
        Returns DataFrame with signal data.
        """
        # Get index data
        index_start = scan_date - timedelta(days=300)
        index_query = text("""
            SELECT date, close FROM index_data
            WHERE index_name = 'NIFTY_50' AND date BETWEEN :start AND :end
            ORDER BY date
        """)
        index_df = pd.read_sql(index_query, self.db_engine,
                               params={'start': index_start, 'end': scan_date})

        results = []
        for symbol in symbols:
            # Get stock data
            df_query = text("""
                SELECT * FROM market_data
                WHERE symbol = :symbol AND date <= :scan_date
                ORDER BY date
                LIMIT 300
            """)
            df = pd.read_sql(df_query, self.db_engine, params={'symbol': symbol, 'scan_date': scan_date})

            if len(df) < 200:
                continue

            try:
                indicators = calculate_all_indicators(df, index_df if not index_df.empty else None)
                if indicators:
                    indicators['symbol'] = symbol
                    results.append(indicators)
            except Exception as e:
                logger.debug(f"Indicator error for {symbol} on {scan_date}: {e}")
                continue

        if not results:
            return pd.DataFrame()

        return pd.DataFrame(results)

    def _infer_dma_status(self, row: pd.Series, index_df: pd.DataFrame) -> str:
        """Infer DMA status from indicator row (helper for regime calculation in backtest)."""
        # Use the dma_status from the row if present
        if 'dma_status' in row:
            return row['dma_status']
        return 'Unconfirmed'

    def run(self, start_date: date = None, end_date: date = None,
            initial_capital: float = None) -> Dict:
        """
        Main backtest execution.

        Args:
            start_date: Backtest start (default: from config)
            end_date: Backtest end (default: today)
            initial_capital: Starting capital

        Returns:
            Dictionary with performance metrics and trade log
        """
        if start_date is None:
            start_date = datetime.strptime(self.config['backtest']['default_start'], "%Y-%m-%d").date()
        if end_date is None:
            end_date = datetime.strptime(self.config['backtest'].get('default_end', str(date.today())), "%Y-%m-%d").date()
        if initial_capital is None:
            initial_capital = self.config['backtest']['initial_capital']

        logger.info(f"Backtest: {start_date} to {end_date}, initial capital: ₹{initial_capital:,.0f}")

        # Get all trading days (dates with index data)
        index_dates_query = text("""
            SELECT DISTINCT date FROM index_data
            WHERE index_name = 'NIFTY_50' AND date BETWEEN :start AND :end
            ORDER BY date
        """)
        with self.db_engine.connect() as conn:
            result = conn.execute(index_dates_query, {'start': start_date, 'end': end_date})
            trading_dates = []
            for row in result:
                # row[0] can be a string or date object; convert to date
                d = row[0]
                if isinstance(d, str):
                    d = datetime.strptime(d, "%Y-%m-%d").date()
                trading_dates.append(d)

        logger.info(f"Found {len(trading_dates)} trading days")

        # State
        cash = initial_capital
        positions = {}  # {symbol: {entry_date, entry_price, shares, investment, avg_price, ...}}
        trades = []  # completed trades
        daily_values = []  # equity curve

        # Main loop
        debug_counter = 0
        for current_date in trading_dates:
            debug_counter += 1
            if debug_counter <= 5:
                logger.info(f"Processing date {current_date} (day {debug_counter})")

            # 1. Process existing positions (check exits)
            positions_to_exit = []

            for symbol, pos in list(positions.items()):
                # Get today's price
                price_query = text("""
                    SELECT close FROM market_data
                    WHERE symbol = :symbol AND date = :date
                """)
                with self.db_engine.connect() as conn:
                    result = conn.execute(price_query, {'symbol': symbol, 'date': current_date}).fetchone()

                if not result:
                    continue

                current_price = result[0]
                if pd.isna(current_price):
                    continue

                # Ensure entry_date is date object
                entry_date = pos['entry_date']
                if isinstance(entry_date, str):
                    entry_date = datetime.strptime(entry_date, "%Y-%m-%d").date()

                days_held = (current_date - entry_date).days

                # Check exit conditions
                exit_reason = None

                # Profit target
                if current_price >= pos['target_price']:
                    exit_reason = 'TARGET'
                # Stop loss
                elif current_price <= pos['stop_loss']:
                    exit_reason = 'STOP_LOSS'
                # Max holding period
                elif days_held >= self.config['strategy']['max_holding_days']:
                    exit_reason = 'MAX_HOLD'
                # CAR signal turned bearish? (optional enhancement)
                # Check daily indicators for exit condition

                if exit_reason:
                    # Exit position
                    exit_value = pos['shares'] * current_price
                    gross_profit = exit_value - pos['investment']
                    # Deduct transaction costs on exit
                    exit_cost = self.calculate_transaction_cost(exit_value)
                    net_profit = gross_profit - exit_cost

                    trade_record = {
                        'entry_date': pos['entry_date'],
                        'exit_date': current_date,
                        'symbol': symbol,
                        'entry_price': pos['entry_price'],
                        'exit_price': current_price,
                        'shares': pos['shares'],
                        'investment': pos['investment'],
                        'gross_profit': gross_profit,
                        'net_profit': net_profit,
                        'return_pct': (current_price / pos['entry_price'] - 1) * 100,
                        'exit_reason': exit_reason,
                        'days_held': days_held
                    }
                    trades.append(trade_record)
                    cash += exit_value - exit_cost
                    positions_to_exit.append(symbol)
                    logger.info(f"EXIT: {symbol} @ {current_price:.2f}, net profit: ₹{net_profit:.2f} ({exit_reason})")

            # Remove exited positions
            for symbol in positions_to_exit:
                del positions[symbol]

            # 2. Generate signals for new entries (using data up to yesterday)
            scan_date = current_date - timedelta(days=1)
            if scan_date < start_date:
                continue

            # Check capacity
            if len(positions) >= self.max_positions:
                continue  # portfolio full

            # Load candidate symbols (limited for speed)
            # Use Nifty 50 or top 100 by volume
            candidate_symbols = self._get_top_symbols_by_volume(current_date, limit=100)

            if not candidate_symbols:
                continue

            # Scan candidates
            scan_df = self._scan_symbols(candidate_symbols, scan_date)

            if scan_df.empty:
                continue

            # Get market regime (need index data)
            index_df = self.load_index_data(scan_date - timedelta(days=300), scan_date)
            if index_df.empty:
                continue  # can't determine regime

            regime = self.strategy_engine.compute_market_regime(scan_df, index_df=index_df)

            regime_class = regime.classify()
            if regime_class == "PAUSE":
                continue  # don't enter new positions

            # Get filtered recommendations
            filtered = self.strategy_engine.filter_and_rank_recommendations(scan_df, regime)

            if filtered.empty:
                continue

            # Determine position size based on regime and capital
            position_multiplier = regime.get_position_size_multiplier()
            base_investment = self.config['strategy']['chain_start_capital']
            position_investment = base_investment * position_multiplier

            # Cap position by available cash and portfolio limit
            max_position_by_cash = cash * 0.10  # don't use more than 10% of cash per position
            position_investment = min(position_investment, max_position_by_cash)

            # Enter top signals (max one per day for simplicity in v1)
            top_signal = filtered.iloc[0]
            symbol = top_signal['symbol']

            if symbol in positions:
                continue  # already holding

            entry_price = top_signal['cmp']
            if pd.isna(entry_price) or entry_price <= 0:
                continue

            # Calculate shares
            shares = int(position_investment / entry_price)
            if shares < 1:
                continue

            actual_investment = shares * entry_price
            transaction_cost = self.calculate_transaction_cost(actual_investment)
            total_cost = actual_investment + transaction_cost

            if total_cost > cash:
                continue

            # Record entry
            positions[symbol] = {
                'entry_date': current_date,
                'entry_price': entry_price,
                'shares': shares,
                'investment': actual_investment,
                'avg_price': entry_price,
                'target_price': entry_price * (1 + self.config['strategy']['target_pct']),
                'stop_loss': entry_price * 0.9,
                'signal': top_signal['master_signal'],
                'score': top_signal['enhanced_score']
            }

            cash -= total_cost

            logger.info(f"ENTER: {symbol} x{shares} @ {entry_price:.2f}, "
                        f"investment: ₹{actual_investment:.0f}, total_cost: ₹{total_cost:.0f}, "
                        f"signal: {top_signal['master_signal']} ({top_signal['enhanced_score']}/15)")

            # 3. Record portfolio value
            portfolio_value = cash
            for symbol, pos in positions.items():
                # Get current price
                price_query = text("""
                    SELECT close FROM market_data
                    WHERE symbol = :symbol AND date = :date
                """)
                with self.db_engine.connect() as conn:
                    result = conn.execute(price_query, {'symbol': symbol, 'date': current_date}).fetchone()
                if result and not pd.isna(result[0]):
                    current_price = result[0]
                    pos_value = pos['shares'] * current_price
                    portfolio_value += pos_value

            daily_values.append({
                'date': current_date,
                'cash': cash,
                'positions_value': portfolio_value - cash,
                'total': portfolio_value,
                'num_positions': len(positions)
            })

        # After loop, close all open positions at end_date price
        for symbol, pos in list(positions.items()):
            # Get last available price
            price_query = text("""
                SELECT close FROM market_data
                WHERE symbol = :symbol AND date = :date
            """)
            with self.db_engine.connect() as conn:
                result = conn.execute(price_query, {'symbol': symbol, 'date': end_date}).fetchone()
            if result:
                exit_price = result[0]
                if not pd.isna(exit_price):
                    exit_value = pos['shares'] * exit_price
                    exit_cost = self.calculate_transaction_cost(exit_value)
                    net_profit = exit_value - pos['investment'] - exit_cost
                    trade_record = {
                        'entry_date': pos['entry_date'],
                        'exit_date': end_date,
                        'symbol': symbol,
                        'entry_price': pos['entry_price'],
                        'exit_price': exit_price,
                        'shares': pos['shares'],
                        'investment': pos['investment'],
                        'gross_profit': exit_value - pos['investment'],
                        'net_profit': net_profit,
                        'return_pct': (exit_price / pos['entry_price'] - 1) * 100,
                        'exit_reason': 'END_DATE',
                        'days_held': (end_date - pos['entry_date']).days
                    }
                    trades.append(trade_record)
                    cash += exit_value - exit_cost

        # Compute metrics
        results = self._compute_metrics(trades, daily_values, initial_capital)
        results['trades'] = trades
        results['equity_curve'] = daily_values

        return results

    def _compute_metrics(self, trades: List[Dict], daily_values: List[Dict], initial_capital: float) -> Dict:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return {'error': 'No trades executed'}

        trades_df = pd.DataFrame(trades)
        daily_df = pd.DataFrame(daily_values)

        # Basic trade metrics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['net_profit'] > 0])
        losing_trades = len(trades_df[trades_df['net_profit'] < 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        avg_win = trades_df[trades_df['net_profit'] > 0]['net_profit'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['net_profit'] < 0]['net_profit'].mean() if losing_trades > 0 else 0
        profit_factor = abs(trades_df[trades_df['net_profit'] > 0]['net_profit'].sum() /
                           trades_df[trades_df['net_profit'] < 0]['net_profit'].sum()) if losing_trades > 0 else np.inf

        total_profit = trades_df['net_profit'].sum()
        return_pct = (total_profit / initial_capital) * 100

        # CAGR
        if not daily_df.empty:
            start_date = daily_df['date'].iloc[0]
            end_date = daily_df['date'].iloc[-1]
            start_val = initial_capital
            end_val = daily_df['total'].iloc[-1]
            years = (end_date - start_date).days / 365.25
            cagr = (end_val / start_val) ** (1 / years) - 1 if years > 0 else 0
        else:
            cagr = 0

        # Drawdown
        if not daily_df.empty:
            daily_df['peak'] = daily_df['total'].cummax()
            daily_df['drawdown'] = (daily_df['total'] - daily_df['peak']) / daily_df['peak']
            max_dd = daily_df['drawdown'].min()
            avg_dd = daily_df['drawdown'].mean()
        else:
            max_dd = 0
            avg_dd = 0

        # Sharpe Ratio (annualized, 6% risk-free)
        if not daily_df.empty and len(daily_df) > 1:
            daily_df['daily_return'] = daily_df['total'].pct_change()
            excess_returns = daily_df['daily_return'].mean() - (0.06 / 252)
            volatility = daily_df['daily_return'].std()
            sharpe = (excess_returns / volatility) * np.sqrt(252) if volatility > 0 else 0
        else:
            sharpe = 0

        # Calmar Ratio (CAGR / Max DD)
        calmar = abs(cagr / max_dd) if max_dd != 0 else 0

        # Average trade metrics
        avg_trade_profit = trades_df['net_profit'].mean()
        avg_trade_days = trades_df['days_held'].mean()
        max_consecutive_wins = self._max_consecutive(trades_df['net_profit'] > 0)
        max_consecutive_losses = self._max_consecutive(trades_df['net_profit'] < 0)

        results = {
            'start_date': start_date.isoformat() if not daily_df.empty else None,
            'end_date': end_date.isoformat() if not daily_df.empty else None,
            'initial_capital': round(float(initial_capital), 2),
            'final_value': round(float(daily_df['total'].iloc[-1]), 2) if not daily_df.empty else float(initial_capital),
            'total_return_pct': round(float(return_pct), 2),
            'cagr_pct': round(float(cagr * 100), 2),
            'max_drawdown_pct': round(float(max_dd * 100), 2),
            'avg_drawdown_pct': round(float(avg_dd * 100), 2),
            'sharpe_ratio': round(float(sharpe), 3),
            'calmar_ratio': round(float(calmar), 3),
            'total_trades': int(total_trades),
            'win_rate': round(float(win_rate), 3),
            'avg_win': round(float(avg_win), 2),
            'avg_loss': round(float(avg_loss), 2),
            'profit_factor': round(float(profit_factor), 2),
            'avg_trade_profit': round(float(avg_trade_profit), 2),
            'avg_trade_days': round(float(avg_trade_days), 1),
            'max_consecutive_wins': int(max_consecutive_wins),
            'max_consecutive_losses': int(max_consecutive_losses),
            'gross_profit': round(float(trades_df['net_profit'].sum()), 2)
        }
        return results

    def _max_consecutive(self, condition_series: pd.Series) -> int:
        """Calculate maximum consecutive True values in a boolean series."""
        if condition_series.empty:
            return 0
        # Group by consecutive blocks
        groups = (condition_series != condition_series.shift()).cumsum()
        return condition_series.groupby(groups).sum().max() if len(condition_series) > 0 else 0


def main():
    """CLI for backtesting."""
    parser = argparse.ArgumentParser(description="Backtest DMA-DMA+CAR strategy")
    parser.add_argument("--config", default="config_local.yaml")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--capital", type=float, default=150000)
    parser.add_argument("--output", default="backtest_results.json")
    args = parser.parse_args()

    from .utils import load_config
    config = load_config(args.config)

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()

    bt = Backtester(config, args.capital)
    results = bt.run(start_dt, end_dt)

    print("\nBacktest Results:")
    print("=" * 60)
    for k, v in results.items():
        if k not in ['trades', 'equity_curve']:
            print(f"  {k}: {v}")

    # Save full results
    with open(args.output, 'w') as f:
        # Convert date objects to strings for JSON
        def serialize_dates(obj):
            if isinstance(obj, (date, datetime)):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        json.dump(results, f, indent=2, default=serialize_dates)

    print(f"\nFull results saved to {args.output}")
    print(f"Trades: {len(results.get('trades', []))}")


if __name__ == "__main__":
    import argparse
    main()
