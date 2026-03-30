import pandas as pd
from openpyxl import load_workbook
import json

filepath = r"C:\Users\bhara\OneDrive\Desktop\Trading\DMA_CAR_Enhanced_500.xlsx"
results = {}

try:
    xl = pd.ExcelFile(filepath)
    sheet_names = xl.sheet_names
    results["sheet_names"] = sheet_names
    results["sheets"] = {}

    for sheet in sheet_names:
        try:
            df = pd.read_excel(filepath, sheet_name=sheet)
            info = {
                "rows": int(df.shape[0]),
                "cols": int(df.shape[1]),
                "columns": list(df.columns),
            }
            # Save CSV
            safe_name = "".join(c if c.isalnum() else "_" for c in sheet)
            csv_name = f"{safe_name}.csv"
            df.to_csv(csv_name, index=False, encoding='utf-8')
            info["csv_file"] = csv_name
            results["sheets"][sheet] = info
        except Exception as e:
            results["sheets"][sheet] = {"error": str(e)}

except Exception as e:
    results["error"] = str(e)

with open("excel_analysis.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

print("Excel analysis complete")  # simple ASCII message
