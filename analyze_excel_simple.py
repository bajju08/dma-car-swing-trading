import pandas as pd
from openpyxl import load_workbook

def analyze_excel_simple(filepath):
    """Simplified Excel analysis without encoding issues"""
    print("=" * 80)
    print("EXCEL FILE - SCANNER & TRADING DATA")
    print("=" * 80)

    try:
        # Get sheet names first
        xl = pd.ExcelFile(filepath)
        sheets = xl.sheet_names
        print(f"\nSheets found: {sheets}")

        for sheet in sheets:
            print(f"\n{'='*60}")
            print(f"SHEET: {sheet}")
            print(f"{'='*60}")

            # Read the sheet
            df = pd.read_excel(filepath, sheet_name=sheet)

            print(f"Dimensions: {df.shape[0]} rows x {df.shape[1]} columns")
            print(f"\nColumn names:")
            for i, col in enumerate(df.columns, 1):
                print(f"  {i:2d}. {col}")

            print(f"\nFirst 5 rows of data:")
            print(df.head().to_string())

            # Check for formula-like columns
            print(f"\nSample data types:")
            print(df.dtypes.head(10))

            # Look for trading/history columns
            if 'stock' in sheet.lower() or 'trade' in sheet.lower() or 'history' in sheet.lower():
                print(f"\n--- This looks like a trading/history sheet ---")
                if 'date' in str(df.columns).lower():
                    date_cols = [c for c in df.columns if 'date' in str(c).lower()]
                    print(f"Date columns: {date_cols}")
                if 'profit' in str(df.columns).lower() or 'pnl' in str(df.columns).lower():
                    pnl_cols = [c for c in df.columns if any(x in str(c).lower() for x in ['profit', 'pnl', 'gain', 'return'])]
                    print(f"P&L columns: {pnl_cols}")

            # Save to CSV for easier analysis
            csv_name = f"{sheet.replace(' ', '_').replace('/', '_')}.csv"
            df.to_csv(csv_name, index=False)
            print(f"\nSaved to: {csv_name}")

        return {"sheets": sheets, "status": "success"}

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

if __name__ == "__main__":
    filepath = r"C:\Users\bhara\OneDrive\Desktop\Trading\DMA_CAR_Enhanced_500.xlsx"
    result = analyze_excel_simple(filepath)

    print("\n" + "=" * 80)
    print("EXCEL ANALYSIS COMPLETE")
    print("=" * 80)
