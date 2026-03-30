-- Migration: Add indexes and constraints to market_data
-- Run: sqlite3 data/market_data.db < migrations/001_improve_market_data.sql

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date ON market_data(symbol, date DESC);

-- Create index for date-only queries (e.g., scan by date)
CREATE INDEX IF NOT EXISTS idx_market_data_date ON market_data(date);

-- Add check constraint to ensure close > 0 (data quality)
-- Note: SQLite doesn't enforce CHECK constraints by default in older versions,
-- but we document the intent
ALTER TABLE market_data ADD COLUMN CONSTRAINT chk_close_positive CHECK (close > 0 OR close IS NULL);

-- Optional: Create a view for latest prices (daily scanner use case)
CREATE VIEW IF NOT EXISTS latest_market_data AS
SELECT * FROM market_data
WHERE (symbol, date) IN (
    SELECT symbol, MAX(date)
    FROM market_data
    GROUP BY symbol
);
