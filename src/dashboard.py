"""
Streamlit Dashboard – Institutional-grade UI for DMA-DMA+CAR platform.

Pages:
1. Home – Market regime, top picks, watchlist
2. Trade Entry – Log new trades
3. Trades – View & manage open positions, averaging, P&L
4. Backtest – Run historical simulation & optimization
5. Settings – Configure platform

Run with: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import json
import logging
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px

from .utils import load_config, get_db_engine, logger, ist_now, format_currency, format_percent, safe_round
from .strategy import StrategyEngine, TradeJournal
from .data_fetcher import DataFetcher
from .alerts import send_alert_target_hit, send_alert_bear_run

# Page config
st.set_page_config(
    page_title="DMA-DMA+CAR Institutional",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional look
st.markdown("""
<style>
    .main .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    .metric-card {background-color: #f0f2f6; padding: 1rem; border-radius: 0.5rem; margin: 0.5rem;}
    .positive {color: #00c853;}
    .negative {color: #ff1744;}
    .stTabs [data-baseweb="tab-list"] {gap: 1rem;}
    .stTabs [data-baseweb="tab"] {height: 3rem; white-space: pre-wrap;}
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'config' not in st.session_state:
    try:
        st.session_state.config = load_config()
    except Exception as e:
        st.error(f"Config load error: {e}. Please create config_local.yaml")
        st.stop()

if 'db_engine' not in st.session_state:
    st.session_state.db_engine = get_db_engine(config=st.session_state.config)

if 'trade_journal' not in st.session_state:
    st.session_state.trade_journal = TradeJournal(st.session_state.db_engine, st.session_state.config)

if 'strategy_engine' not in st.session_state:
    st.session_state.strategy_engine = StrategyEngine(st.session_state.config)

if 'recommendations' not in st.session_state:
    # Load from latest JSON file if exists
    rec_file = Path("recommendations.json")
    if rec_file.exists():
        with open(rec_file) as f:
            st.session_state.recommendations = json.load(f)
    else:
        st.session_state.recommendations = None

# Navigation
st.sidebar.title("📊 DMA-DMA+CAR")
page = st.sidebar.radio("Navigate", ["Home", "Trade Entry", "Trades", "Backtest", "Settings"])

# ==================== PAGE 1: HOME ====================
if page == "Home":
    st.title("🏠 Dashboard Home")
    st.markdown("---")

    # Refresh button
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Refresh Data", type="primary"):
            with st.spinner("Running screener..."):
                try:
                    engine = st.session_state.strategy_engine
                    recs = engine.generate_daily_recommendations()
                    st.session_state.recommendations = recs
                    # Save to file
                    with open('recommendations.json', 'w') as f:
                        json.dump(recs, f, indent=2, default=str)
                    st.success("Screener updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Screener failed: {e}")

    # Load recommendations
    recs = st.session_state.recommendations
    if recs is None:
        st.warning("No recommendations data. Click 'Refresh Data' to run the screener.")
        st.stop()

    # Market Regime Summary
    st.subheader("Market Regime")
    regime = recs['market_regime']
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Regime", regime['classification'])
    with col2:
        st.metric("Nifty Status", regime['nifty_status'])
    with col3:
        st.metric("Stocks in Bull Run", f"{regime['bull_percentage']*100:.1f}%")
    with col4:
        st.metric("Position Size", f"{regime['position_multiplier']:.0%}")

    st.markdown("---")

    # Top Picks
    st.subheader(f"🚀 Top {min(15, len(recs['top_picks']))} Picks")

    if len(recs['top_picks']) == 0:
        st.warning("No qualified recommendations for current market regime.")
        st.info("Consider waiting for better entry conditions. The strategy filters are designed to protect capital.")
    else:
        # Create DataFrame for display
        picks_df = pd.DataFrame(recs['top_picks'])
        display_df = picks_df[['symbol', 'master_signal', 'enhanced_score', 'speed_score',
                              'cmp', 'dma_status', 'car_signal', 'beta', 'rsi_14']].copy()
        display_df['Target (₹)'] = (display_df['cmp'] * 1.0628).round(2)
        display_df['Upside %'] = ((display_df['Target (₹)'] - display_df['cmp']) / display_df['cmp'] * 100).round(2)
        display_df = display_df.rename(columns={
            'symbol': 'Stock',
            'master_signal': 'Signal',
            'enhanced_score': 'Score',
            'speed_score': 'Speed',
            'cmp': 'CMP',
            'dma_status': 'DMA Status',
            'car_signal': 'CAR',
            'beta': 'Beta',
            'rsi_14': 'RSI'
        })

        # Color code signals
        def highlight_signal(val):
            colors = {
                'PRIME FAST': 'background-color: #ffeb3b; color: #000',
                'PRIME BUY': 'background-color: #4caf50; color: #fff',
                'BUY': 'background-color: #8bc34a; color: #000',
                'WATCH': 'background-color: #fff59d; color: #000',
                'SKIP': 'background-color: #ffccbc; color: #000',
                'REVERSE TRADE': 'background-color: #f44336; color: #fff'
            }
            return colors.get(val, '')

        styled_df = display_df.style.applymap(highlight_signal, subset=['Signal'])
        st.dataframe(styled_df, use_container_width=True, height=400)

        # Download CSV
        csv = display_df.to_csv(index=False)
        st.download_button("📥 Download Picks CSV", csv, "recommendations.csv", "text/csv")

    st.markdown("---")

    # Watchlist (Unconfirmed/Near-Bull)
    if recs['all_recommendations']:
        st.subheader("👀 Near-Bull Watchlist")
        watchlist = [p for p in recs['all_recommendations'] if p['dma_status'] == 'Unconfirmed' and p['enhanced_score'] >= 6]
        if watchlist:
            watch_df = pd.DataFrame(watchlist)[['symbol', 'enhanced_score', 'pct_from_200', 'master_signal']].head(10)
            st.dataframe(watch_df, use_container_width=True)
        else:
            st.info("No stocks near Bull Run transition.")

    st.markdown("---")

    # Quick Stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Scanned", recs['total_scan'])
        st.metric("Qualified", recs['total_qualified'])
    with col2:
        # Load open trades count
        try:
            open_trades = st.session_state.trade_journal.get_open_trades()
            st.metric("Open Trades", len(open_trades))
            if not open_trades.empty:
                total_unrealized = open_trades['unrealized_pnl'].sum()
                st.metric("Unrealized P&L", format_currency(total_unrealized))
        except:
            pass

# ==================== PAGE 2: TRADE ENTRY ====================
elif page == "Trade Entry":
    st.title("📝 Trade Entry")
    st.markdown("---")

    # Load recommendations for quick select
    recs = st.session_state.recommendations
    stock_choices = []
    if recs and recs['top_picks']:
        stock_choices = [p['symbol'] for p in recs['top_picks']]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("New Trade")
        with st.form("new_trade_form"):
            stock = st.selectbox("Stock *", options=stock_choices if stock_choices else [""], placeholder="Select from recommendations")
            if not stock:
                manual_stock = st.text_input("Or enter NSE code manually (e.g., NSE:RELIANCE)")
                stock = manual_stock if manual_stock.startswith("NSE:") else f"NSE:{manual_stock}"

            entry_date = st.date_input("Entry Date *", value=date.today())
            entry_price = st.number_input("Entry Price *", min_value=0.01, step=0.05, format="%.2f")
            quantity = st.number_input("Quantity *", min_value=1, step=1, value=1)

            # Chain selection
            chain = st.number_input("Chain #", min_value=1, max_value=10, value=1)
            slot = st.number_input("Slot (Row) #", min_value=1, value=1)

            # Investment calculation
            investment = entry_price * quantity
            st.write(f"Investment Amount: ₹{investment:,.2f}")

            # Auto-calc target & reserve
            target_mult = 1 + st.session_state.config['strategy']['target_pct']
            target_price = investment * target_mult
            avg_reserve = investment * 0.5  # 50% of initial

            st.write(f"Target Price: ₹{target_price:,.2f}")
            st.write(f"Avg Reserve (50%): ₹{avg_reserve:,.2f}")

            notes = st.text_area("Notes")

            submitted = st.form_submit_button("✅ Add Trade", type="primary")
            if submitted:
                if not stock or entry_price <= 0 or quantity <= 0:
                    st.error("Please fill all required fields")
                else:
                    try:
                        trade_data = {
                            'chain': int(chain),
                            'slot': int(slot),
                            'stock': stock,
                            'entry_date': entry_date,
                            'entry_price': float(entry_price),
                            'investment': float(investment),
                            'target_price': float(target_price),
                            'avg_reserve': float(avg_reserve),
                            'notes': notes
                        }
                        trade_id = st.session_state.trade_journal.add_trade(trade_data)
                        st.success(f"Trade #{trade_id} added successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add trade: {e}")

    with col2:
        st.subheader("Quick Stats")
        # Show summary of recommendation if selected
        if stock and recs:
            pick = next((p for p in recs['top_picks'] if p['symbol'] == stock), None)
            if pick:
                st.info(f"""
                **{stock}**
                - Signal: {pick['master_signal']}
                - Score: {pick['enhanced_score']}/15
                - Current Price: ₹{pick['cmp']}
                - Target: ₹{pick['cmp']*1.0628:.2f}
                - DMA Status: {pick['dma_status']}
                - CAR: {pick['car_signal']}
                """)

# ==================== PAGE 3: TRADES ====================
elif page == "Trades":
    st.title("💼 Trade Journal")
    st.markdown("---")

    # Tabs: Open Trades, Closed Trades, All Trades
    tab1, tab2, tab3 = st.tabs(["Open Trades", "Closed Trades", "All Trades"])

    with tab1:
        open_trades = st.session_state.trade_journal.get_open_trades()
        if open_trades.empty:
            st.info("No open trades.")
        else:
            # Display open trades
            for _, trade in open_trades.iterrows():
                with st.container():
                    cols = st.columns([3, 2, 2, 2, 2, 2, 3])
                    cols[0].subheader(f"{trade['stock']} (Chain {trade['chain']}, Slot {trade['slot']})")
                    cols[1].metric("Entry", format_currency(trade['entry_price']))
                    cols[2].metric("Avg", format_currency(trade['avg_price']))
                    cols[3].metric("Current", format_currency(trade['current_price']) if not pd.isna(trade['current_price']) else "N/A")
                    cols[4].metric("Target", format_currency(trade['target_price']))
                    pnl = trade['unrealized_pnl']
                    pnl_str = format_currency(pnl) if not pd.isna(pnl) else "N/A"
                    cols[5].metric("P&L", pnl_str, delta=pnl_str)
                    with cols[6]:
                        st.write(f"Days: {trade['days_held']}")
                        st.write(f"Signal: {trade.get('notes', '')[:50]}...")
                        if st.button(f"Average ➕", key=f"avg_{trade['id']}"):
                            # Show averaging modal
                            st.session_state[f"show_avg_form_{trade['id']}"] = True

                    # Average Form (expandable)
                    if st.session_state.get(f"show_avg_form_{trade['id']}"):
                        with st.form(f"avg_form_{trade['id']}"):
                            st.write("### Add Average")
                            avg_price = st.number_input("Average Price", min_value=0.01, key=f"avg_price_{trade['id']}")
                            avg_amount = st.number_input("Amount to Add", min_value=100.0, key=f"avg_amt_{trade['id']}")
                            cola, colb = st.columns(2)
                            with cola:
                                if st.form_submit_button("Confirm Average"):
                                    try:
                                        st.session_state.trade_journal.add_average(trade['id'], date.today(), avg_price, avg_amount)
                                        st.success("Average added!")
                                        st.session_state[f"show_avg_form_{trade['id']}"] = False
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            with colb:
                                if st.form_submit_button("Cancel"):
                                    st.session_state[f"show_avg_form_{trade['id']}"] = False
                                    st.rerun()

                    st.divider()

    with tab2:
        closed_trades = pd.read_sql("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY close_date DESC LIMIT 100", st.session_state.db_engine)
        if closed_trades.empty:
            st.info("No closed trades.")
        else:
            st.dataframe(closed_trades[['stock', 'entry_date', 'close_date', 'entry_price', 'exit_price', 'profit_booked', 'days_held']], use_container_width=True)

    with tab3:
        all_trades = st.session_state.trade_journal.get_all_trades()
        st.dataframe(all_trades, use_container_width=True)
        csv = all_trades.to_csv(index=False)
        st.download_button("📥 Export Trades CSV", csv, "trades_export.csv", "text/csv")

# ==================== PAGE 4: BACKTEST ====================
elif page == "Backtest":
    st.title("📈 Backtesting Engine")
    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("Start Date", value=date(2021, 1, 1))
    with col2:
        end_date = st.date_input("End Date", value=date.today())
    with col3:
        initial_capital = st.number_input("Initial Capital (₹)", value=15000, min_value=1000)

    st.subheader("Backtest Parameters")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        min_score = st.slider("Min Enhanced Score", 0, 15, 8)
        min_speed = st.slider("Min Speed Score", 0, 10, 4)
    with col_b:
        min_beta = st.slider("Min Beta", 0.0, 2.0, 0.8, step=0.1)
        require_golden = st.checkbox("Require Golden DMA", value=True)
    with col_c:
        max_position_pct = st.slider("Max Position % of Capital", 0.01, 1.0, 0.33)
        use_regime_filter = st.checkbox("Use Market Regime Filter", value=True)

    if st.button("▶ Run Backtest", type="primary"):
        with st.spinner("Running backtest... this may take minutes"):
            try:
                # Placeholder for backtest logic
                st.info("Backtest module implementation in progress...")
                # Future: load historical data, simulate day-by-day entries/exits
            except Exception as e:
                st.error(f"Backtest failed: {e}")

    st.markdown("---")
    st.subheader("Historical Performance (Placeholder)")
    # Show a sample chart for now
    dates = pd.date_range(start=start_date, end=end_date)
    portfolio = pd.Series(initial_capital * (1 + np.random.randn(len(dates)).cumsum() * 0.002), index=dates)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=portfolio, mode='lines', name='Portfolio Value'))
    fig.update_layout(title='Equity Curve (Sample)', xaxis_title='Date', yaxis_title='Value (₹)')
    st.plotly_chart(fig, use_container_width=True)

# ==================== PAGE 5: SETTINGS ====================
elif page == "Settings":
    st.title("⚙️ Settings")
    st.markdown("---")

    st.subheader("Strategy Configuration")
    config = st.session_state.config

    with st.form("config_form"):
        st.write("**Filters**")
        col1, col2 = st.columns(2)
        with col1:
            min_enhanced = st.number_input("Min Enhanced Score", value=config['strategy']['min_enhanced_score'], min_value=0, max_value=15)
            min_speed = st.number_input("Min Speed Score", value=config['strategy']['min_speed_score'], min_value=0, max_value=10)
            beta_min = st.number_input("Min Beta", value=config['strategy']['beta_min'], min_value=0.0, max_value=5.0, step=0.1)
        with col2:
            vol_min = st.number_input("Min Volume Ratio", value=config['strategy']['volume_ratio_min'], min_value=0.0, step=0.1)
            rsi_max = st.number_input("Max RSI (avoid overbought)", value=config['strategy']['rsi_max'], min_value=0, max_value=100)
            adx_min = st.number_input("Min ADX for trend", value=config['strategy']['adx_min'], min_value=0, max_value=100)

        st.write("**Averaging**")
        col3, col4 = st.columns(2)
        with col3:
            avg_max = st.number_input("Max Averages", value=config['strategy']['avg_max_count'], min_value=0, max_value=30)
            avg_drop = st.number_input("Price Drop Trigger %", value=config['strategy']['avg_price_drop_pct']*100, min_value=0.0, max_value=50.0) / 100
        with col4:
            avg_day = st.selectbox("Average Day of Week", options=[0,1,2,3,4,5,6],
                                   format_func=lambda x: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][x],
                                   index=config['strategy']['avg_weekly_day'])

        st.write("**Exit Rules**")
        col5, col6 = st.columns(2)
        with col5:
            max_hold = st.number_input("Max Holding Days", value=config['strategy']['max_holding_days'], min_value=30, max_value=365)
            exit_days = st.number_input("Days in Bear Run before exit", value=config['strategy']['exit_hopeless_days'], min_value=1, max_value=180)

        submitted = st.form_submit_button("💾 Save Configuration")
        if submitted:
            config['strategy']['min_enhanced_score'] = min_enhanced
            config['strategy']['min_speed_score'] = min_speed
            config['strategy']['beta_min'] = beta_min
            config['strategy']['volume_ratio_min'] = vol_min
            config['strategy']['rsi_max'] = rsi_max
            config['strategy']['adx_min'] = adx_min
            config['strategy']['avg_max_count'] = avg_max
            config['strategy']['avg_price_drop_pct'] = avg_drop
            config['strategy']['avg_weekly_day'] = avg_day
            config['strategy']['max_holding_days'] = max_hold
            config['strategy']['exit_hopeless_days'] = exit_days

            # Save to config_local.yaml
            import yaml
            with open('config_local.yaml', 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            st.success("Configuration saved to config_local.yaml")
            st.rerun()

    st.markdown("---")
    st.subheader("Dhan API Status")
    try:
        fetcher = DataFetcher(config)
        token = fetcher._get_dhan_access_token()
        if token:
            st.success("✅ Dhan API connected")
        else:
            st.warning("⚠ Dhan credentials not configured or invalid")
    except Exception as e:
        st.error(f"❌ Dhan connection error: {e}")

    st.markdown("---")
    st.subheader("Telegram Alerts")
    tg_cfg = config.get('telegram', {})
    if tg_cfg.get('bot_token') and tg_cfg.get('chat_id'):
        st.success("✅ Telegram configured")
        if st.button("📤 Send Test Alert"):
            send_daily_report(st.session_state.recommendations or {}, config)
    else:
        st.warning("⚠ Telegram not configured. See SETUP_TELEGRAM.md")

    st.markdown("---")
    st.subheader("Export/Import Data")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 Export Trades CSV"):
            df = st.session_state.trade_journal.get_all_trades()
            csv = df.to_csv(index=False)
            st.download_button("Download", csv, "trades_export.csv", "text/csv")
    with col2:
        if st.button("📥 Import Trades CSV"):
            uploaded = st.file_uploader("Upload CSV", type=['csv'])
            if uploaded:
                # TODO: implement import
                st.info("Import feature coming soon")

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("v1.0 Institutional Edition")
st.sidebar.caption("Built with ❤️ by you")
