from src.backtest import Backtester
from src.utils import load_config
from datetime import date, timedelta

config = load_config()
bt = Backtester(config, initial_capital=150000)

# Get candidate symbols from volume query (top 50)
test_dates = [
    date(2024, 1, 15),
    date(2024, 4, 1),
    date(2024, 7, 1),
    date(2024, 10, 1),
    date(2025, 1, 15),
    date(2025, 4, 1),
    date(2025, 7, 1),
    date(2025, 10, 1),
    date(2026, 1, 15),
    date(2026, 3, 1),
]

print("Scanning for bullish periods...\n")
for d in test_dates:
    scan_date = d  # use exact date as scan_date (in backtest we use d-1 but here just test)
    candidates = bt._get_top_symbols_by_volume(scan_date, limit=50)
    if not candidates:
        print(f"{scan_date}: No candidates (volume query returned 0)")
        continue

    scan_df = bt._scan_symbols(candidates, scan_date)
    if scan_df.empty:
        print(f"{scan_date}: No scan results")
        continue

    index_df = bt.load_index_data(scan_date - timedelta(days=300), scan_date)
    if index_df.empty:
        print(f"{scan_date}: No index data")
        continue

    regime = bt.strategy_engine.compute_market_regime(scan_df, index_df=index_df)
    regime_class = regime.classify()

    # Count bullish signals
    signal_counts = scan_df['master_signal'].value_counts().to_dict()
    bull_count = (scan_df['dma_status'] == 'In Bull Run').sum()
    total = len(scan_df)

    print(f"{scan_date}: Regime={regime_class:12} | Bull stocks: {bull_count}/{total} | Signals: {signal_counts}")

print("\nDone")
