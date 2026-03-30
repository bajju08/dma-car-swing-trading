"""
Swing Trading Dashboard - Streamlit
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
import logging
import os

from src.utils import load_config, get_db_engine
from src.data_fetcher import DataFetcher
from src.strategy import StrategyEngine
from src.indicators import calculate_all_indicators
from src.backtest import Backtester

# Page config
st.set_page_config(page_title="DMA-DMA+CAR Platform", layout="wide", page_icon="📈")

# Load config - merge local config with Streamlit secrets
config = load_config()

# Override with Streamlit secrets if available (for cloud deployment)
if hasattr(st, 'secrets'):
    # Telegram
    if 'telegram' in st.secrets:
        config.setdefault('telegram', {})
        config['telegram']['bot_token'] = st.secrets.get('telegram', {}).get('bot_token', config['telegram'].get('bot_token', ''))
        config['telegram']['chat_id'] = st.secrets.get('telegram', {}).get('chat_id', config['telegram'].get('chat_id', ''))

    # Database URL (if using external DB like Neon/Supabase)
    if 'database' in st.secrets and 'url' in st.secrets['database']:
        config['data']['db_path'] = st.secrets['database']['url']

    # Dhan credentials
    if 'dhan' in st.secrets:
        config.setdefault('dhan', {})
        config['dhan']['client_id'] = st.secrets.get('dhan', {}).get('client_id', config['dhan'].get('client_id', ''))
        config['dhan']['access_token'] = st.secrets.get('dhan', {}).get('access_token', config['dhan'].get('access_token', ''))
        config['dhan']['api_key'] = st.secrets.get('dhan', {}).get('api_key', config['dhan'].get('api_key', ''))
        config['dhan']['secret'] = st.secrets.get('dhan', {}).get('secret', config['dhan'].get('secret', ''))

engine = get_db_engine(config=config)

# Title
st.title("📈 DMA-DMA+CAR Swing Trading Platform")
st.markdown("Institutional-grade swing trading system based on DMA crossovers and CAR momentum")

# Sidebar navigation
page = st.sidebar.radio("Navigate", ["Live Scanner", "Recommendations", "Trade Journal", "Backtest", "Analytics", "Settings"])

if page == "Live Scanner":
    st.header("🔍 Live Market Scanner")

    col1, col2, col3 = st.columns(3)
    with col1:
        symbols_input = st.text_input("Test Symbols (comma-separated)", "NSE:RELIANCE,NSE:TCS,NSE:INFY")
    with col2:
        scan_button = st.button("Run Scan", type="primary")
    with col3:
        st.write("")
        st.write(f"Market Date: **{date.today()}**")

    if scan_button:
        symbols = [s.strip() for s in symbols_input.split(',') if s.strip()]
        with st.spinner(f"Scanning {len(symbols)} symbols..."):
            engine = StrategyEngine(config)
            recommendations = engine.generate_daily_recommendations(symbols=symbols)

        # Display market regime
        regime = recommendations['market_regime']
        st.metric("Market Regime", regime['classification'],
                  f"Nifty: {regime['nifty_status']} | Bull %: {regime['bull_percentage']:.1%}")

        # Top picks table
        st.subheader(f"🎯 Top Recommendations ({len(recommendations['top_picks'])})")
        if recommendations['top_picks']:
            df_top = pd.DataFrame(recommendations['top_picks'])
            st.dataframe(df_top[['symbol', 'master_signal', 'enhanced_score', 'speed_score',
                                 'cmp', 'dma_status', 'car_signal', 'beta', 'rsi_14']],
                         use_container_width=True)
        else:
            st.info("No recommendations generated (PAUSE regime or insufficient scores)")

elif page == "Recommendations":
    st.header("📊 Historical Recommendations")

    # Query archive from DB
    try:
        df = pd.read_sql("""
            SELECT
                scan_time, symbol, master_signal, enhanced_score, speed_score,
                cmp, dma_status, car_signal, beta, rsi_14, volume_ratio
            FROM recommendations_archive
            WHERE scan_time >= date('now', '-30 days')
            ORDER BY scan_time DESC, enhanced_score DESC
        """, engine)

        if not df.empty:
            st.dataframe(df, use_container_width=True)

            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Signals (30d)", len(df))
            with col2:
                prime_fast = len(df[df['master_signal'] == 'PRIME FAST'])
                st.metric("PRIME FAST", prime_fast)
            with col3:
                avg_score = df['enhanced_score'].mean()
                st.metric("Avg Enhanced Score", f"{avg_score:.1f}")
        else:
            st.info("No recommendations in last 30 days")
    except Exception as e:
        st.error(f"Could not load recommendations: {e}")

elif page == "Trade Journal":
    st.header("📒 Trade Journal")

    try:
        # Show open trades
        from src.strategy import TradeJournal
        journal = TradeJournal(engine, config)
        open_trades = journal.get_open_trades()

        if not open_trades.empty:
            st.subheader("Open Positions")
            st.dataframe(open_trades[['stock', 'entry_date', 'entry_price', 'avg_price',
                                     'investment', 'target_price', 'status']], use_container_width=True)

            # P&L update button
            if st.button("Update Current Prices"):
                data_fetcher = DataFetcher(config)
                def price_fetcher(symbol):
                    return data_fetcher.get_latest_price(symbol)
                journal.update_prices(price_fetcher)
                st.success("Prices updated")
                st.rerun()
        else:
            st.info("No open positions")

        # Show closed trades
        closed_trades = journal.get_all_trades()
        closed_trades = closed_trades[closed_trades['status'] == 'CLOSED']
        if not closed_trades.empty:
            st.subheader("Trade History")
            st.dataframe(closed_trades[['stock', 'entry_date', 'close_date',
                                        'entry_price', 'avg_price', 'profit_booked', 'days_held']],
                         use_container_width=True)

            # Summary
            total_profit = closed_trades['profit_booked'].sum()
            win_rate = (closed_trades['profit_booked'] > 0).mean()
            st.metric("Total Realized P&L", f"₹{total_profit:,.0f}", f"Win Rate: {win_rate:.1%}")
    except Exception as e:
        st.error(f"Error loading trades: {e}")

elif page == "Backtest":
    st.header("🎮 Backtest Lab")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start Date", value=date(2021, 1, 1))
    with col2:
        end_date = st.date_input("End Date", value=date.today())
    with col3:
        initial_capital = st.number_input("Initial Capital", value=150000, min_value=10000)

    if st.button("Run Backtest", type="primary"):
        with st.spinner("Running backtest..."):
            bt = Backtester(config)
            results = bt.run_backtest(
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                symbols=None,  # use all
                hold_period_days=config['strategy']['max_holding_days']
            )

        st.subheader("Performance Metrics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("CAGR", f"{results.get('cagr', 0):.1f}%")
        with col2:
            st.metric("Max Drawdown", f"{results.get('max_drawdown', 0):.1f}%")
        with col3:
            st.metric("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}")
        with col4:
            st.metric("Win Rate", f"{results.get('win_rate', 0):.1%}")

        st.metric("Total Return", f"₹{results.get('final_capital', 0):,.0f}",
                  f"Profit: ₹{results.get('total_profit', 0):,.0f}")

        # More details in expandable section
        with st.expander("Full Results"):
            st.json(results)

elif page == "Analytics":
    st.header("📈 Analytics")

    # 1. Regime distribution over time
    try:
        regime_df = pd.read_sql("""
            SELECT
                date(scan_time) as date,
                market_regime,
                COUNT(*) as count
            FROM scan_history
            WHERE scan_time >= date('now', '-90 days')
            GROUP BY date, market_regime
            ORDER BY date
        """, engine)

        if not regime_df.empty:
            st.subheader("Market Regime Timeline")
            fig = px.bar(regime_df, x='date', y='count', color='market_regime',
                         title="Regime Distribution Over Time")
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Regime timeline not available: {e}")

    # 2. Signal quality
    try:
        signal_df = pd.read_sql("""
            SELECT master_signal, COUNT(*) as count, AVG(enhanced_score) as avg_score
            FROM recommendations_archive
            WHERE scan_time >= date('now', '-30 days')
            GROUP BY master_signal
            ORDER BY count DESC
        """, engine)

        if not signal_df.empty:
            st.subheader("Signal Distribution")
            fig = px.pie(signal_df, values='count', names='master_signal')
            st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.info(f"Signal distribution not available: {e}")

elif page == "Settings":
    st.header("⚙️ Configuration")
    st.write("Current config loaded from:", config.get('config_file', 'config_local.yaml'))

    with st.expander("Edit Strategy Parameters"):
        st.write("Strategy thresholds:")
        new_min_score = st.slider("Minimum Enhanced Score", 5, 15, config['strategy']['min_enhanced_score'])
        new_min_speed = st.slider("Minimum Speed Score", 1, 10, config['strategy']['min_speed_score'])
        if st.button("Save Changes"):
            # TODO: write to config_local.yaml
            st.success("Settings saved (implementation pending)")

st.sidebar.markdown("---")
st.sidebar.info("Built with Claude Code | DMA-DMA+CAR Strategy")
