from src.utils import load_config, get_db_engine
from src.data_fetcher import DataFetcher
from src.indicators import calculate_all_indicators
from datetime import date
from sqlalchemy import text

config = load_config()
engine = get_db_engine(config=config)

# Check candidate symbols for a specific date
test_date = date(2025, 1, 15)
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT symbol, AVG(volume) as avg_vol
        FROM market_data
        WHERE date >= date(:as_of, '-30 days') AND date <= :as_of
        GROUP BY symbol
        ORDER BY avg_vol DESC
        LIMIT 10
    """), {'as_of': test_date})
    symbols = [row[0] for row in result]
    print("Top symbols by volume on 2025-01-15:", symbols)

    idx = conn.execute(text("SELECT COUNT(*) FROM index_data WHERE date <= '2025-01-15'")).scalar()
    print("Index data rows before 2025-01-15:", idx)

fetcher = DataFetcher(config)
index_df = fetcher.get_index_data(days=300)
print("\nIndex_df shape:", index_df.shape)
print("Index_df latest dates:", index_df['date'].tail(3).tolist() if not index_df.empty else "empty")

for symbol in symbols[:3]:
    df = fetcher.get_data_for_symbol(symbol, days=300)
    print(f"\n{symbol}: {len(df)} rows, latest date: {df['date'].max() if not df.empty else 'empty'}")
    if len(df) >= 200:
        try:
            ind = calculate_all_indicators(df, index_df)
            print(f"  enhanced_score: {ind.get('enhanced_score')}, master_signal: {ind.get('master_signal')}")
        except Exception as e:
            print(f"  error: {e}")
            import traceback
            traceback.print_exc()

print("\nNow testing if we have data for 2025-01-02 (first trading day of year)")
test_date2 = date(2025, 1, 2)
with engine.connect() as conn:
    count = conn.execute(text("SELECT COUNT(*) FROM market_data WHERE date = :d"), {'d': test_date2}).scalar()
    print(f"Rows on 2025-01-02: {count}")
