#!/bin/bash
# Daily trading script – schedule via cron/Task Scheduler

cd "$(dirname "$0")"

# 1. Source virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Trade monitoring & exit checks (run after previous day's close)
python -c "
from src.trade_execution import TradeManager
from src.utils import load_config, get_db_engine
config = load_config()
engine = get_db_engine(config=config)
manager = TradeManager(engine, config)
manager.monitor_open_trades()
"

# 3. Run scanner (fetch fresh data + generate recommendations)
python -m src.screener --tickers ""  # empty = full universe

# 4. Check data health
python -m src.health_check  # optional, log to file

# 5. Rotate logs (optional)
# logrotate /path/to/logs/*.log

echo "Daily run completed at $(date)"
