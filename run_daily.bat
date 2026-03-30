@echo off
cd /d "C:\Users\bhara\OneDrive\Desktop\Trading"
call venv\Scripts\activate

REM Trade monitoring
python -c "from src.trade_execution import TradeManager; from src.utils import load_config, get_db_engine; config = load_config(); engine = get_db_engine(config=config); manager = TradeManager(engine, config); manager.monitor_open_trades()"

REM Daily scanner
python -m src.screener --tickers ""

echo Daily run completed at %date% %time%
pause
