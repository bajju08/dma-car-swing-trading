import pandas as pd
from src.utils import get_db_engine, load_config
from src.indicators import calculate_all_indicators
from datetime import date

config = load_config()
engine = get_db_engine(config=config)

# Get Nifty index data up to 2025-01-15
query = """
SELECT * FROM index_data
WHERE index_name = 'NIFTY_50' AND date <= '2025-01-15'
ORDER BY date
LIMIT 300
"""
df = pd.read_sql(query, engine)
print(f"Nifty rows (up to 2025-01-15): {len(df)}")
print("Date range:", df['date'].min(), "to", df['date'].max())

if len(df) >= 200:
    ind = calculate_all_indicators(df.rename(columns={'close': 'close'})[['date', 'close']])
    print("\nNifty indicators as of 2025-01-15:")
    print(f"  dma_status: {ind.get('dma_status')}")
    print(f"  golden_dma: {ind.get('golden_dma')}")
    print(f"  cmp: {ind.get('cmp')}")
    print(f"  ma50: {ind.get('ma50')}, ma100: {ind.get('ma100')}, ma200: {ind.get('ma200')}")
