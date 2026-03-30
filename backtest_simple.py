"""Simplified backtest to diagnose issues."""
from src.backtest import Backtester
from src.utils import load_config
from datetime import date

config = load_config()
bt = Backtester(config, initial_capital=150000)

# Overload the backtest: just test one specific date
from src.utils import get_db_engine
engine = get_db_engine(config=config)

# Pick a date in 2024 that should have data
test_dates = [date(2024, 6, 3), date(2024, 9, 2), date(2024, 12, 2)]
for current_date in test_dates:
    print(f"\nTesting {current_date}:")
    scan_date = current_date  # for simplicity

    # Get candidate symbols
    candidate_symbols = bt._get_top_symbols_by_volume(scan_date, limit=50)
    print(f"  Candidates: {len(candidate_symbols)} symbols")

    if not candidate_symbols:
        continue

    # Scan
    scan_df = bt._scan_symbols(candidate_symbols, scan_date)
    print(f"  Scan results: {len(scan_df)} symbols with indicators")
    if not scan_df.empty:
        print(f"  Columns: {scan_df.columns.tolist()}")
        # Show some signal stats
        print(f"  DMA status counts: {scan_df['dma_status'].value_counts().to_dict()}")
        print(f"  Enhanced score range: {scan_df['enhanced_score'].min()} - {scan_df['enhanced_score'].max()}")
        print(f"  Master signals: {scan_df['master_signal'].value_counts().to_dict()}")

    # Load index and compute regime
    index_df = bt.load_index_data(scan_date - scan_date.replace(day=1) - timedelta(days=300), scan_date) # not exact
    # Better: index_df = bt.load_index_data(scan_date - timedelta(days=300), scan_date)
    index_df = bt.load_index_data(scan_date - timedelta(days=300), scan_date)
    print(f"  Index data rows: {len(index_df)}")
    if len(index_df) >= 200:
        regime = bt.strategy_engine.compute_market_regime(scan_df, index_df=index_df)
        regime_class = regime.classify()
        bull_pct = regime.bull_percentage
        print(f"  Regime: {regime_class}, Bull%: {bull_pct:.1%}, Nifty: {regime.nifty_status}")

        # Filter
        filtered = bt.strategy_engine.filter_and_rank_recommendations(scan_df, regime)
        print(f"  Filtered recommendations: {len(filtered)}")
        if not filtered.empty:
            print("  Top 3:")
            for i, row in filtered.head(3).iterrows():
                print(f"    {row['symbol']}: {row['master_signal']}, score {row['enhanced_score']}, cmp {row['cmp']}")
    else:
        print("  Not enough index data")

print("\nDone")
