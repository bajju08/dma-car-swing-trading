from src.utils import get_db_engine, load_config
from src.data_fetcher import DataFetcher
from src.indicators import calculate_all_indicators
from datetime import date
import pandas as pd

config = load_config()
fetcher = DataFetcher(config)

symbol = "NSE:RELIANCE"
dates_to_test = [
    date(2024, 1, 15),
    date(2024, 3, 1),
    date(2024, 6, 1),
    date(2024, 9, 1),
    date(2024, 12, 1),
    date(2025, 3, 1),
    date(2025, 6, 1),
    date(2025, 9, 1),
    date(2025, 12, 1),
    date(2026, 3, 1),
]

print(f"Testing {symbol} signals at various dates (using data up to that date):\n")

for test_date in dates_to_test:
    # Get stock data up to test_date
    df = fetcher.get_data_for_symbol(symbol, end_date=test_date, days=300)
    if len(df) < 200:
        print(f"{test_date}: Insufficient data ({len(df)} rows)")
        continue

    # Get index data up to test_date
    index_df = fetcher.get_index_data(days=300)
    # Convert to date
    index_df['date'] = pd.to_datetime(index_df['date']).dt.date
    index_df = index_df[index_df['date'] <= test_date]
    if len(index_df) < 200:
        print(f"{test_date}: Insufficient index data ({len(index_df)} rows)")
        continue

    try:
        indicators = calculate_all_indicators(df, index_df)
        if indicators:
            print(f"{test_date}: {indicators['master_signal']} | Score: {indicators['enhanced_score']}/15 | DMA: {indicators['dma_status']} | CMP: ₹{indicators['cmp']:.1f}")
        else:
            print(f"{test_date}: No indicators returned")
    except Exception as e:
        print(f"{test_date}: Error - {e}")
