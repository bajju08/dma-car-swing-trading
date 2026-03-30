"""
Database schema management - run migrations automatically on startup.
"""

from sqlalchemy import MetaData, Table, Column, Integer, String, Float, Date, DateTime, Boolean, Text
from .utils import get_db_engine, logger


def create_scan_history_table(engine):
    """Create table to log each scan run."""
    metadata = MetaData()
    Table('scan_history', metadata,
          Column('id', Integer, primary_key=True),
          Column('scan_time', DateTime, nullable=False),
          Column('total_symbols_scanned', Integer),
          Column('total_recommendations', Integer),
          Column('market_regime', String(20)),
          Column('nifty_status', String(20)),
          Column('bull_percentage', Float),
          Column('json_file', String(255)),  # path to saved recommendations.json
          )
    metadata.create_all(engine)
    logger.info("Ensured scan_history table exists")


def create_recommendations_archive_table(engine):
    """Create table to store all recommendations over time."""
    metadata = MetaData()
    Table('recommendations_archive', metadata,
          Column('id', Integer, primary_key=True),
          Column('scan_time', DateTime, nullable=False),
          Column('symbol', String(50), nullable=False),
          Column('master_signal', String(20)),
          Column('enhanced_score', Integer),
          Column('speed_score', Integer),
          Column('cmp', Float),
          Column('dma_status', String(20)),
          Column('car_signal', String(20)),
          Column('beta', Float),
          Column('rsi_14', Float),
          Column('volume_ratio', Float),
          Column('recommended_investment', Float),
          Column('exit_price_10pct', Float),  # 10% below entry for stop
          Column('target_price', Float),  # based on target_pct
          )
    metadata.create_all(engine)
    logger.info("Ensured recommendations_archive table exists")


def create_trade_journal_table(engine):
    """Create table to track actual trades (already exists as 'trades' in strategy.py)."""
    # This is already created by TradeJournal._ensure_table()
    pass


def run_all_migrations(engine):
    """Run all pending migrations."""
    create_scan_history_table(engine)
    create_recommendations_archive_table(engine)
    logger.info("All migrations completed")


if __name__ == "__main__":
    from .utils import load_config
    config = load_config()
    engine = get_db_engine(config=config)
    run_all_migrations(engine)
