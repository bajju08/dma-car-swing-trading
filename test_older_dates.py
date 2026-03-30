from src.backtest import Backtester
from src.utils import load_config
from datetime import date, timedelta

config = load_config()
bt = Backtester(config, initial_capital=150000)

test_dates = [
    date(2022, 1, 15),
    date(2022, 6, 1),
    date(2022, 10, 1),
    date(2023, 1, 15),
    date(2023, 6, 1),
    date(2023, 10, 1),
]

print("Scanning older dates...\n")
for d in test_dates:
    scan_date = d
    candidates = bt._get_top_symbols_by_volume(scan_date, limit=50)
    if not candidates:
        print(f"{scan_date}: No candidates")
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
    bull_count = (scan_df['dma_status'] == 'In Bull Run').sum()
    total = len(scan_df)
    signals = scan_df['master_signal'].value_counts().to_dict()

    print(f"{scan_date}: Regime={regime_class:12} | Bull: {bull_count}/{total} | Signals: {signals}")

print("\nDone")
