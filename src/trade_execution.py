"""
Enhanced trade management - entry, averaging, exit automation.
"""

from datetime import date, datetime
from typing import Optional, List
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


class TradeManager:
    """
    Complete trade lifecycle management.
    Integrates with broker API (Zerodha/Upstox/Dhan) for order placement.
    """

    def __init__(self, db_engine, config, broker_api=None):
        self.db_engine = db_engine
        self.config = config
        self.broker = broker_api  # TODO: integrate broker SDK

    def enter_trade(self, symbol: str, entry_price: float, signal_strength: str,
                    enhanced_score: int) -> int:
        """
        Create a new trade entry.
        Returns trade ID.
        """
        from .strategy import TradeJournal

        journal = TradeJournal(self.db_engine, self.config)

        # Determine position size based on regime and signal strength
        base_capital = self.config['strategy']['chain_start_capital']
        multiplier = self._get_position_multiplier(signal_strength, enhanced_score)
        investment = base_capital * multiplier

        # Calculate quantity (round to nearest integer)
        quantity = int(investment / entry_price)

        if quantity < 1:
            logger.warning(f"Investment too small for {symbol}: ₹{investment:.2f} at price ₹{entry_price}")
            return None

        trade_data = {
            'chain': 1,  # TODO: determine chain based on correlation
            'slot': 1,   # first slot in chain
            'stock': symbol,
            'entry_date': date.today(),
            'entry_price': entry_price,
            'investment': investment,
            'avg_reserve': investment * 0.5,  # 50% reserve for averaging
            'notes': f"Entry: {signal_strength}, Score: {enhanced_score}/15"
        }

        trade_id = journal.add_trade(trade_data)

        # Place actual order via broker API (when enabled)
        if self.broker:
            self._place_buy_order(symbol, quantity, order_type='MARKET')

        logger.info(f"Entered trade #{trade_id}: {symbol} x{quantity} @ ₹{entry_price:.2f}")
        return trade_id

    def _get_position_multiplier(self, signal_strength: str, score: int) -> float:
        """Determine position sizing multiplier based on signal."""
        base = self.config['strategy'].get('position_size_full', 1.0)

        if signal_strength == 'PRIME FAST':
            return base * 1.5  # boost for prime signals
        elif signal_strength == 'PRIME BUY':
            return base * 1.2
        elif signal_strength == 'BUY':
            return base
        else:
            return 0.0  # don't trade

    def check_averaging_opportunity(self, trade_id: int, current_price: float,
                                    car_signal: str, dma_status: str) -> Optional[str]:
        """
        Check if a trade qualifies for averaging.
        Returns reason string if qualifies, else None.
        """
        from .strategy import TradeJournal
        journal = TradeJournal(self.db_engine, self.config)

        trades = journal.get_open_trades()
        trade = trades[trades['id'] == trade_id]

        if trade.empty:
            return None

        trade = trade.iloc[0]

        should_average, reason = journal.should_average(
            trade, current_price, car_signal, dma_status
        )

        if should_average:
            # Calculate average amount (fixed 1/15 of initial slot or from config)
            initial_investment = float(trade['investment'])
            avg_amount = initial_investment * self.config['strategy']['avg_fixed_amount_ratio']

            # Execute average
            journal.add_average(trade_id, date.today(), current_price, avg_amount)

            # Place broker order
            if self.broker:
                quantity = int(avg_amount / current_price)
                self._place_buy_order(trade['stock'], quantity, order_type='MARKET')

            logger.info(f"Averaged trade #{trade_id}: +₹{avg_amount:.2f} at ₹{current_price:.2f}")

        return reason if should_average else None

    def monitor_open_trades(self):
        """
        Daily: Check all open trades for exit conditions and averaging opportunities.
        This should be called after market close each day.
        """
        from .strategy import TradeJournal
        journal = TradeJournal(self.db_engine, self.config)

        open_trades = journal.get_open_trades()
        logger.info(f"Monitoring {len(open_trades)} open trades")

        for _, trade in open_trades.iterrows():
            symbol = trade['stock']

            # Fetch latest data for this symbol
            from .data_fetcher import DataFetcher
            fetcher = DataFetcher(self.config)
            df = fetcher.get_data_for_symbol(symbol, days=300)

            if df.empty or len(df) < 200:
                logger.warning(f"Insufficient data for {symbol} during monitoring")
                continue

            # Get latest indicators
            from .indicators import calculate_all_indicators
            indicators = calculate_all_indicators(df)

            if not indicators:
                logger.warning(f"Could not calculate indicators for {symbol}")
                continue

            current_price = indicators['cmp']
            dma_status = indicators['dma_status']
            car_signal = indicators['car_signal']

            # Check exit conditions
            exit_reason = journal.check_exit_conditions(
                trade, dma_status, car_signal,
                days_in_bear=0  # TODO: track this in trade
            )

            if exit_reason:
                logger.info(f"Exit triggered for trade #{trade['id']}: {exit_reason}")
                self._exit_trade(trade['id'], current_price, exit_reason)
                continue

            # Check averaging
            avg_reason = self.check_averaging_opportunity(trade['id'], current_price, car_signal, dma_status)
            if avg_reason:
                logger.info(f"Averaging opportunity for trade #{trade['id']}: {avg_reason}")

    def _exit_trade(self, trade_id: int, exit_price: float, reason: str):
        """Exit a trade and record P&L."""
        from .strategy import TradeJournal
        journal = TradeJournal(self.db_engine, self.config)

        # Get trade details to calculate P&L
        trades = journal.get_open_trades()
        trade = trades[trades['id'] == trade_id]

        if trade.empty:
            logger.error(f"Trade #{trade_id} not found for exit")
            return

        trade = trade.iloc[0]

        # Calculate realized P&L
        avg_price = float(trade['avg_price'])
        investment = float(trade['investment'])
        shares = investment / avg_price if avg_price > 0 else 0
        profit = (exit_price - avg_price) * shares

        journal.close_trade(trade_id, date.today(), profit, reason)

        # Place sell order via broker
        if self.broker:
            quantity = int(shares)
            self._place_sell_order(trade['stock'], quantity)

        logger.info(f"Exited trade #{trade_id}: ₹{profit:.2f} profit ({reason})")

    def _place_buy_order(self, symbol: str, quantity: int, order_type='MARKET'):
        """Placeholder for broker integration."""
        if self.broker:
            # Example for Zerodha Kite:
            # self.broker.place_order(
            #     variety=self.broker.VARIETY_REGULAR,
            #     exchange=self.broker.EXCHANGE_NSE,
            #     tradingsymbol=symbol.replace('NSE:', ''),
            #     transaction_type=self.broker.TRANSACTION_TYPE_BUY,
            #     quantity=quantity,
            #     order_type=order_type,
            #     product=self.broker.PRODUCT_DELIVERY
            # )
            pass
        else:
            logger.info(f"[DRY RUN] Would BUY {quantity} of {symbol}")

    def _place_sell_order(self, symbol: str, quantity: int):
        """Placeholder for broker integration."""
        if self.broker:
            # Similar to buy
            pass
        else:
            logger.info(f"[DRY RUN] Would SELL {quantity} of {symbol}")


if __name__ == "__main__":
    print("Trade Manager module - ready to integrate with broker")
