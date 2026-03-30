#!/usr/bin/env python3
"""
Screener CLI – Run daily scan and output recommendations.

Usage:
    python screener.py [--output recommendations.json] [--full-update]
    python screener.py --test-dhan

This script:
1. Fetches latest data for Nifty 500 stocks
2. Runs strategy engine to compute scores
3. Outputs recommendations to JSON file
4. Optionally sends alerts
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, date, timedelta
from sqlalchemy import text
import logging

from .utils import load_config, logger, ist_now, parse_nse_codes_from_file, get_db_engine
from .data_fetcher import DataFetcher
from .strategy import StrategyEngine
from .alerts import send_daily_report

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def main():
    parser = argparse.ArgumentParser(description="DMA-DMA+CAR Daily Screener")
    parser.add_argument("--output", "-o", default="recommendations.json", help="Output JSON file")
    parser.add_argument("--full-update", action="store_true", help="Fetch fresh historical data for all stocks (slow)")
    parser.add_argument("--test-connection", action="store_true", help="Test data source connection (Dhan or yfinance)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--no-alerts", action="store_true", help="Skip sending Telegram/Email alerts")
    parser.add_argument("--config", default="config_local.yaml", help="Config file path")
    parser.add_argument("--tickers", help="Comma-separated list of tickers for testing (e.g., NSE:RELIANCE,NSE:TCS)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to fetch for testing")

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger.info("="*60)
    logger.info("DMA-DMA+CAR Screener Started")
    logger.info("="*60)

    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        sys.exit(1)

    # Test mode
    if args.test_connection:
        logger.info("Testing data source connection...")
        fetcher = DataFetcher(config)
        # Test if we can fetch
        test_symbols = ["NSE:RELIANCE", "NSE:TCS"]
        end = date.today()
        start = end - timedelta(days=10)
        success = False
        for sym in test_symbols:
            df = fetcher.fetch_historical(sym, start, end)
            if not df.empty:
                logger.info(f"✅ Fetched {len(df)} days for {sym}")
                success = True
            else:
                logger.warning(f"⚠ No data for {sym}")
        if success:
            logger.info("✅ Data source connection OK (using yfinance fallback)")
        else:
            logger.error("❌ Could not fetch data from any source")
        sys.exit(0 if success else 1)

    # Load stock universe
    universe_file = config['data']['nifty_500_file']
    if not Path(universe_file).exists():
        logger.error(f"Universe file not found: {universe_file}")
        sys.exit(1)

    # If tickers provided for testing, use those instead of full universe
    if args.tickers:
        symbols = [t.strip() for t in args.tickers.split(',') if t.strip()]
        logger.info(f"Using test tickers: {len(symbols)} symbols")
    else:
        symbols = parse_nse_codes_from_file(universe_file)
        logger.info(f"Loaded {len(symbols)} symbols from {universe_file}")

    # Initialize data fetcher
    fetcher = DataFetcher(config)

    # Determine if we need to fetch data
    if args.tickers:
        # Test mode with specific tickers – fetch full history for proper indicator calculation
        logger.info(f"Test mode: fetching full history for {len(symbols)} tickers")
        end_date = date.today()
        start_date = date(end_date.year - config['data']['history_years'], end_date.month, end_date.day)
        for symbol in symbols:
            try:
                df = fetcher.fetch_historical(symbol, start_date, end_date)
                if not df.empty:
                    # Delete existing data for this symbol to avoid duplicates
                    with fetcher.db_engine.connect() as conn:
                        conn.execute(text("DELETE FROM market_data WHERE symbol = :sym"), {'sym': symbol})
                        df['symbol'] = symbol
                        df.to_sql('market_data', conn, if_exists='append', index=False)
                    logger.info(f"Fetched {len(df)} days for {symbol}")
                else:
                    logger.warning(f"No data for {symbol}")
                time.sleep(0.5)  # rate limiting
            except Exception as e:
                logger.error(f"Error fetching {symbol}: {e}")
        # Also fetch index data
        fetcher.fetch_index_data(years=config['data']['history_years'])
    elif args.full_update:
        # Full update: fetch full history for all symbols
        logger.info("Full update mode: fetching historical data for all symbols...")
        end_date = date.today()
        start_date = date(end_date.year - config['data']['history_years'], end_date.month, end_date.day)
        success = fetcher.update_daily_data(symbols, date=end_date)
        logger.info(f"Full update complete: updated {success} symbols")
        # Also fetch index data
        fetcher.fetch_index_data(years=config['data']['history_years'])
    else:
        # Daily incremental: just fetch last few days for all symbols
        logger.info("Daily update: fetching latest data")
        end_date = date.today()
        success = fetcher.update_daily_data(symbols, date=end_date)
        logger.info(f"Daily update complete: updated {success} symbols")

    # Run strategy engine
    engine = StrategyEngine(config)
    # In test mode (--tickers), pass the limited symbol list; else None loads full universe
    recommendations = engine.generate_daily_recommendations(symbols=symbols if args.tickers else None)

    # Save to JSON
    output_file = args.output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(recommendations, f, indent=2, default=str, ensure_ascii=False)
    logger.info(f"✅ Recommendations saved to {output_file}")
    logger.info(f"   Regime: {recommendations['market_regime']['classification']}")
    logger.info(f"   Qualified: {recommendations['total_qualified']} out of {recommendations['total_scan']}")

    # Archive to database
    try:
        from .db_schema import create_scan_history_table, create_recommendations_archive_table
        from sqlalchemy import text
        from datetime import datetime

        engine = get_db_engine(config=config)

        # Ensure tables exist
        create_scan_history_table(engine)
        create_recommendations_archive_table(engine)

        # Insert scan history
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO scan_history (
                    scan_time, total_symbols_scanned, total_recommendations,
                    market_regime, nifty_status, bull_percentage, json_file
                ) VALUES (
                    :time, :total_scanned, :total_qual,
                    :regime, :nifty_status, :bull_pct, :json_file
                )
            """), {
                'time': datetime.now(),
                'total_scanned': recommendations['total_scan'],
                'total_qual': recommendations['total_qualified'],
                'regime': recommendations['market_regime']['classification'],
                'nifty_status': recommendations['market_regime']['nifty_status'],
                'bull_pct': recommendations['market_regime']['bull_percentage'],
                'json_file': output_file
            })

            # Insert each recommendation
            for rec in recommendations['all_recommendations']:
                conn.execute(text("""
                    INSERT INTO recommendations_archive (
                        scan_time, symbol, master_signal, enhanced_score, speed_score,
                        cmp, dma_status, car_signal, beta, rsi_14, volume_ratio,
                        recommended_investment, exit_price_10pct, target_price
                    ) VALUES (
                        :time, :symbol, :signal, :enh_score, :speed_score,
                        :cmp, :dma_status, :car_signal, :beta, :rsi, :vol_ratio,
                        :inv, :exit_10pct, :target
                    )
                """), {
                    'time': datetime.now(),
                    'symbol': rec['symbol'],
                    'signal': rec['master_signal'],
                    'enh_score': rec['enhanced_score'],
                    'speed_score': rec['speed_score'],
                    'cmp': rec['cmp'],
                    'dma_status': rec['dma_status'],
                    'car_signal': rec['car_signal'],
                    'beta': rec['beta'],
                    'rsi': rec['rsi_14'],
                    'vol_ratio': rec['volume_ratio'],
                    'inv': rec.get('recommended_investment'),
                    'exit_10pct': rec['cmp'] * 0.9 if rec.get('cmp') else None,
                    'target': rec['cmp'] * 1.0628 if rec.get('cmp') else None,
                })
            conn.commit()
        logger.info("✅ Recommendations archived to database")
    except Exception as e:
        logger.error(f"Failed to archive recommendations: {e}")

    # Print top 10 to console
    print("\n" + "="*80)
    print("TOP 10 RECOMMENDATIONS")
    print("="*80)
    for i, pick in enumerate(recommendations['top_picks'][:10], 1):
        print(f"{i:2d}. {pick['symbol']}")
        print(f"    Signal: {pick['master_signal']} | Score: {pick['enhanced_score']}/15 | Speed: {pick['speed_score']}/10")
        print(f"    CMP: {pick['cmp']} | Target: {pick['cmp']*1.0628:.2f} (6.28%)")
        print(f"    DMA: {pick['dma_status']} | CAR: {pick['car_signal']}")
        print(f"    Beta: {pick['beta']} | RSI: {pick['rsi_14']}")
        print()

    # Send alerts unless disabled
    if not args.no_alerts:
        try:
            send_daily_report(recommendations, config)
            logger.info("✅ Alerts sent")
        except Exception as e:
            logger.error(f"Failed to send alerts: {e}")

    logger.info("Screener completed successfully")
    return 0

if __name__ == "__main__":
    sys.exit(main())
