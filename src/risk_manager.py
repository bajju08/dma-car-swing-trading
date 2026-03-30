"""
Risk Management Module
"""

import numpy as np
from typing import Dict


class RiskManager:
    """
    Portfolio-level risk management:
    - Position sizing (Kelly, Fixed Fractional)
    - Correlation-based diversification
    - Maximum drawdown controls
    - Circuit breakers for daily loss limits
    """

    def __init__(self, config: dict, portfolio_value: float):
        self.config = config
        self.portfolio_value = portfolio_value
        self.max_position_size = config['strategy'].get('max_position_size_pct', 0.10)  # 10% max
        self.max_correlated_positions = 2  # max 2 from same sector (TODO: need sector mapping)

    def calculate_position_size(self, signal_strength: str, enhanced_score: int,
                                regime_multiplier: float, current_drawdown: float) -> float:
        """
        Calculate recommended position size based on:
        - Signal strength (PRIME FAST > PRIME BUY > BUY)
        - Score (0-15)
        - Regime multiplier (PAUSE=0, FULL_BULL=1.0, etc.)
        - Current portfolio drawdown (reduce size if underwater)

        Formula: Base Capital × Strength Factor × Score Factor × Regime × Drawdown Factor
        """
        base_capital = self.config['strategy']['chain_start_capital']

        # Strength factor
        strength_factors = {
            'PRIME FAST': 1.5,
            'PRIME BUY': 1.2,
            'BUY': 1.0,
            'WATCH': 0.5,
            'SKIP': 0.0
        }
        strength_factor = strength_factors.get(signal_strength, 0)

        # Score factor (linear: 8-15 maps to 1.0-1.2)
        if enhanced_score >= 13:
            score_factor = 1.2
        elif enhanced_score >= 10:
            score_factor = 1.1
        elif enhanced_score >= 8:
            score_factor = 1.0
        else:
            score_factor = 0

        # Drawdown reduction
        if current_drawdown < -0.10:  # >10% drawdown
            dd_factor = 0.5
        elif current_drawdown < -0.05:  # >5% drawdown
            dd_factor = 0.75
        else:
            dd_factor = 1.0

        position = base_capital * strength_factor * score_factor * regime_multiplier * dd_factor

        # Apply portfolio-level limits
        max_by_portfolio = self.portfolio_value * self.max_position_size
        final_position = min(position, max_by_portfolio)

        return round(final_position, 2)

    def check_correlation_exposure(self, new_symbol: str, existing_positions: list, sector_map: Dict) -> bool:
        """
        Check if adding this position would exceed sector concentration limits.
        Sector map: {symbol: "sector_name"}
        """
        current_sector = sector_map.get(new_symbol)
        if not current_sector:
            return True  # no sector info, allow

        count = sum(1 for pos in existing_positions if sector_map.get(pos['symbol']) == current_sector)
        return count < self.max_correlated_positions

    def check_daily_loss_limit(self, realized_pnl_today: float, unrealized_pnl: float) -> bool:
        """
        Circuit breaker: If daily loss exceeds limit, stop trading for the day.
        Default: 2% of portfolio value.
        """
        daily_loss_limit = self.portfolio_value * 0.02
        total_pnl = realized_pnl_today + unrealized_pnl
        return total_pnl < -daily_loss_limit


def calculate_kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """
    Kelly Criterion: f* = p - (1-p)/W
    where p = win rate, W = win/loss ratio
    """
    if avg_loss == 0:
        return 0.0
    win_loss_ratio = abs(avg_win / avg_loss)
    kelly = win_rate - (1 - win_rate) / win_loss_ratio
    return max(0, min(kelly, 0.25))  # cap at 25% of capital


if __name__ == "__main__":
    # Example usage
    config = {
        'strategy': {
            'chain_start_capital': 15000,
            'max_position_size_pct': 0.10
        }
    }
    rm = RiskManager(config, portfolio_value=1000000)
    pos = rm.calculate_position_size('PRIME FAST', 14, 1.0, 0.0)
    print(f"Recommended position size: ₹{pos:,.0f}")
