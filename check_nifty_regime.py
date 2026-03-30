from src.utils import get_db_engine, load_config
from src.indicators import calculate_all_indicators
from datetime import date
import pandas as pd

config = load_config()
engine = get_db_engine(config=config)

# Get Nifty data up to 2025-01-15
query = """
SELECT * FROM index_data
WHERE index_name = 'NIFTY_50' AND date <= '2025-01-15'
ORDER BY date
LIMIT 300
"""
df = pd.read_sql(query, engine)
print(f"Nifty rows up to 2025-01-15: {len(df)}, dates: {df['date'].min()} to {df['date'].max()}")

if len(df) >= 200:
    # Build OHLC from close
    df_input = pd.DataFrame({
        'date': df['date'],
        'close': df['close'],
        'open': df['close'],
        'high': df['close'],
        'low': df['close'],
        'volume': 0
    })
    indicators = calculate_all_indicators(df_input)
    print("\nNifty status as of 2025-01-15:")
    print(f"  dma_status: {indicators.get('dma_status')}")
    print(f"  cmp: {indicators.get('cmp')}, ma50: {indicators.get('ma50')}, ma100: {indicators.get('ma100')}, ma200: {indicators.get('ma200')}")
    print(f"  golden_dma: {indicators.get('golden_dma')}")
    print(f"  pct_from_200: {indicators.get('pct_from_200')}%")
else:
    print("Insufficient data (<200 rows)")

# Also check later date: 2024-06-01
print("\n" + "="*60)
query2 = """
SELECT * FROM index_data
WHERE index_name = 'NIFTY_50' AND date <= '2024-06-01'
ORDER BY date
LIMIT 300
"""
df2 = pd.read_sql(query2, engine)
print(f"Nifty rows up to 2024-06-01: {len(df2)}")
if len(df2) >= 200:
    df2_input = pd.DataFrame({
        'date': df2['date'],
        'close': df2['close'],
        'open': df2['close'],
        'high': df2['close'],
        'low': df2['close'],
        'volume': 0
    })
    ind2 = calculate_all_indicators(df2_input)
    print("Nifty status as of 2024-06-01:")
    print(f"  dma_status: {ind2.get('dma_status')}, cmp: {ind2.get('cmp')}, golden_dma: {ind2.get('golden_dma')}")
