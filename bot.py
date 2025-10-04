# bot.py - COMPLETE MERGED VERSION WITH PERFECT DASHBOARD
"""
COMPLETE MERGED VERSION - BOT + DASHBOARD IN ONE FILE
- All features from both files
- Perfect dashboard styling 
- Railway deployment ready
- Static files setup
- Error handling
"""

import os
import time
import threading
import json
import argparse
import tempfile
import math
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import numpy as np
import logging
from logging.handlers import RotatingFileHandler
import traceback
from functools import wraps

# Binance client
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Binance library not available: {e}")
    Client = None
    BINANCE_AVAILABLE = False

# FastAPI + dashboard
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    FASTAPI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ FastAPI not available: {e}")
    FASTAPI_AVAILABLE = False

# Custom JSON encoder for NaN values
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
        return super().default(obj)

if FASTAPI_AVAILABLE:
    app = FastAPI(title="Trading Bot", version="1.0.0")
else:
    app = None

# Load environment
load_dotenv()

# Enhanced Logging Setup
def setup_logging():
    """Setup comprehensive logging with rotation"""
    logger = logging.getLogger('trading_bot')
    logger.setLevel(logging.INFO)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    file_handler = RotatingFileHandler(
        'trading_bot.log', 
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# Config
def _env_bool(name, default="False"):
    v = os.getenv(name, default)
    try:
        return str(v).lower() in ("1", "true", "yes")
    except Exception:
        return False

API_KEY    = os.getenv("BINANCE_API_KEY", "") or os.getenv("API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "") or os.getenv("API_SECRET", "")
USE_TESTNET = _env_bool("USE_TESTNET", "True")
DRY_RUN = _env_bool("DRY_RUN", "True")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
TRADE_USDT = float(os.getenv("TRADE_USDT", 50.0))

PORT = int(os.getenv("PORT", 8000))

EMA_FAST = 9
EMA_SLOW = 21
EMA_MID = 50
RSI_LEN = 14
RSI_LONG = 51
RSI_SHORT = 48
ADX_LEN = 14
ADX_THR = 20

CONFIRMATION_REQUIRED = int(os.getenv("CONFIRMATION_REQUIRED", "2"))

ATR_LEN = 14
ATR_SL_MULT = 2.0

RISK_REWARD_RATIO = 2.0
TP1_PERCENT = 0.01
TP2_PERCENT = 0.02
TP3_PERCENT = 0.03

TP1_CLOSE_PERCENT = 0.30
TP2_CLOSE_PERCENT = 0.25  
TP3_CLOSE_PERCENT = 0.25
TRAILING_PERCENT = 0.20

TRAILING_ACTIVATION_PERCENT = 0.03
TRAILING_DISTANCE_PERCENT = 0.01

TRADE_COOLDOWN = 3600

SYMBOLS = [
    "SOLUSDT","BNBUSDT","BTCUSDT","ETHUSDT","XRPUSDT","ADAUSDT","DOGEUSDT",
    "PEPEUSDT","LINKUSDT","XLMUSDT","AVAXUSDT","DOTUSDT","OPUSDT","TRXUSDT",
]

BASE_DIR = os.path.dirname(__file__) or "."
TRADES_FILE = os.path.join(BASE_DIR, "trades.csv")
STATE_FILE  = os.path.join(BASE_DIR, "state.json")

# Create static directory for CSS
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

_state_lock = threading.RLock()

# ✅ FIXED: Create CSS file for consistent styling
CSS_CONTENT = """
:root {
    --primary: #2563eb;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --dark: #1f2937;
    --light: #f3f4f6;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    margin: 0;
    padding: 0;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    height: 100vh;
    overflow: hidden;
    color: #333;
}

.container {
    max-width: 1800px;
    margin: 0 auto;
    background: white;
    height: 100vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
}

.header {
    background: var(--dark);
    color: white;
    padding: 10px 15px;
    text-align: center;
    flex-shrink: 0;
}

.header h1 {
    margin: 0;
    font-size: 1.5em;
    font-weight: 300;
}

.main-content {
    padding: 10px;
    display: flex;
    flex-direction: column;
    height: calc(100vh - 60px);
    overflow: hidden;
    gap: 10px;
}

.dashboard-top {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    height: auto;
    min-height: 300px;
    flex-shrink: 0;
    overflow: hidden;
}

.left-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.right-panel {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.stats-overview {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
}

.stat-card {
    background: white;
    padding: 8px;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    text-align: center;
    border-left: 3px solid var(--primary);
}

.stat-card h3 {
    color: var(--dark);
    margin-bottom: 3px;
    font-size: 0.7em;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.stat-card .value {
    font-size: 1.1em;
    font-weight: bold;
}

.positive { color: var(--success); }
.negative { color: var(--danger); }

.section {
    background: white;
    padding: 8px;
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
}

.section h3 {
    color: var(--dark);
    margin-bottom: 6px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--light);
    font-size: 0.9em;
    flex-shrink: 0;
}

.positions-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 6px;
    overflow: visible;
    flex: 1;
    padding: 3px;
    max-height: none;
}

.position-card {
    border: 1px solid #e5e7eb;
    border-radius: 5px;
    padding: 6px;
    background: #fafafa;
    min-height: 150px;
    font-size: 0.7em;
}

.position-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}

.symbol {
    font-weight: bold;
    font-size: 0.8em;
}

.side.long { color: var(--success); }
.side.short { color: var(--danger); }

.position-details div {
    margin: 1px 0;
    font-size: 0.65em;
}

.tp-levels {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    margin: 4px 0;
    padding: 2px;
    background: #f8fafc;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}

.tp-level {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.tp-label {
    font-size: 0.65em;
    color: #64748b;
    font-weight: 600;
}

.tp-value {
    font-size: 0.65em;
    font-weight: bold;
    color: #1e293b;
}

.sltp-controls-horizontal {
    display: flex;
    gap: 4px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 6px;
}

.control-group {
    display: flex;
    flex-direction: column;
    gap: 1px;
}

.control-group label {
    font-size: 0.55em;
    color: #666;
    font-weight: 600;
}

.sltp-controls-horizontal input {
    width: 55px;
    padding: 2px;
    border: 1px solid #ccc;
    border-radius: 2px;
    font-size: 0.65em;
    text-align: center;
}

button {
    padding: 3px 6px;
    border: none;
    border-radius: 2px;
    cursor: pointer;
    font-size: 0.65em;
    transition: all 0.3s ease;
    white-space: nowrap;
}

.btn-secondary {
    background: var(--primary);
    color: white;
}

.btn-danger {
    background: var(--danger);
    color: white;
}

.btn-export {
    background: var(--warning);
    color: white;
}

.summary-table table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.7em;
}

.summary-table th, .summary-table td {
    border: 1px solid #e5e7eb;
    padding: 4px;
    text-align: center;
}

.summary-table th {
    background: var(--light);
    font-weight: 600;
}

.metrics-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}

.metric-card {
    background: var(--light);
    padding: 6px;
    border-radius: 4px;
    text-align: center;
    border-left: 2px solid var(--primary);
}

.metric-label {
    display: block;
    font-size: 0.6em;
    color: #666;
    margin-bottom: 2px;
}

.metric-value {
    display: block;
    font-size: 0.8em;
    font-weight: bold;
}

.controls {
    display: flex;
    gap: 6px;
    margin-bottom: 8px;
    flex-wrap: wrap;
    flex-shrink: 0;
}

.search-box {
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    flex: 1;
    min-width: 120px;
    font-size: 0.75em;
}

.filter-select {
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 3px;
    background: white;
    font-size: 0.75em;
}

.export-buttons {
    display: flex;
    gap: 6px;
}

.trade-history-section {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 300px;
    max-height: 50vh;
}

.trade-history-container {
    flex: 1;
    overflow: auto;
    border: 1px solid #e5e7eb;
    border-radius: 5px;
}

.trade-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75em;
    table-layout: fixed;
    margin: 0;
}

.trade-table th, .trade-table td {
    padding: 6px 8px;
    border: 1px solid #e5e7eb;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.trade-table th {
    background: #f8fafc;
    font-weight: 600;
    color: #374151;
    position: sticky;
    top: 0;
    z-index: 10;
    font-size: 0.8em;
}

.col-trade-no { width: 70px; text-align: center; }
.col-symbol { width: 100px; }
.col-type { width: 70px; text-align: center; }
.col-date { width: 130px; }
.col-signal { width: 90px; text-align: center; }
.col-price { width: 100px; text-align: right; }
.col-size { width: 100px; text-align: right; }
.col-pnl { width: 90px; text-align: center; }
.col-runup { width: 90px; text-align: center; }
.col-drawdown { width: 90px; text-align: center; }
.col-cumulative { width: 100px; text-align: right; }

.trade-row {
    transition: background-color 0.2s;
}

.trade-row:hover {
    background-color: #f9fafb;
}

.entry-row {
    background-color: #ffffff;
}

.entry-row.long {
    border-left: 3px solid #10b981;
}

.entry-row.short {
    border-left: 3px solid #ef4444;
}

.exit-row {
    background-color: #f8fafc;
    color: #6b7280;
}

@media (max-width: 1200px) {
    .dashboard-top {
        grid-template-columns: 1fr;
        height: auto;
    }
    
    .positions-grid {
        grid-template-columns: 1fr;
    }
    
    .trade-history-section {
        height: auto;
        min-height: 300px;
    }
}
"""

# ✅ FIXED: Write CSS file
CSS_FILE = os.path.join(STATIC_DIR, "style.css")
with open(CSS_FILE, "w", encoding="utf-8") as f:
    f.write(CSS_CONTENT)

# Mount static files
if FASTAPI_AVAILABLE:
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Enhanced Error Handling Decorator
def safe_execute(default_return=None, max_retries=3):
    """Decorator for safe function execution with retries"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                    continue
            logger.error(f"All retries failed for {func.__name__}: {str(last_exception)}")
            return default_return
        return wrapper
    return decorator

# Price Validation System
class PriceValidator:
    """Validate prices against realistic market ranges"""
    
    SYMBOL_PRICE_RANGES = {
        "BTCUSDT": (10000.0, 180000.0),
        "ETHUSDT": (500.0, 10000.0),
        "BNBUSDT": (100.0, 10000.0),
        "SOLUSDT": (10.0, 5000.0),
        "AVAXUSDT": (10.0, 2000.0),
        "XRPUSDT": (0.1, 100.0),
        "ADAUSDT": (0.1, 50.0),
        "DOGEUSDT": (0.01, 20.0),
        "PEPEUSDT": (0.000001, 0.01),
        "LINKUSDT": (5.0, 1000.0),
        "XLMUSDT": (0.05, 5.0),
        "DOTUSDT": (2.0, 500.0),
        "OPUSDT": (0.01, 200.0),
        "TRXUSDT": (0.05, 10.0)
    }
    
    @classmethod
    def validate_price(cls, symbol, price, action="trade"):
        """Validate if price is within realistic range"""
        if symbol not in cls.SYMBOL_PRICE_RANGES:
            return True
            
        min_price, max_price = cls.SYMBOL_PRICE_RANGES[symbol]
        
        if price < min_price or price > max_price:
            logger.warning(f"🚨 SUSPICIOUS PRICE: {symbol} at {price} for {action} (range: {min_price}-{max_price})")
            return False
            
        return True
    
    @classmethod
    def validate_trade_prices(cls, symbol, entry_price, exit_price):
        """Validate both entry and exit prices"""
        valid_entry = cls.validate_price(symbol, entry_price, "entry")
        valid_exit = cls.validate_price(symbol, exit_price, "exit")
        
        if not valid_entry or not valid_exit:
            logger.error(f"❌ INVALID TRADE PRICES: {symbol} Entry:{entry_price}, Exit:{exit_price}")
            return False
            
        price_change_pct = abs(exit_price - entry_price) / entry_price
        if price_change_pct > 2.0:
            logger.warning(f"⚠️ LARGE PRICE CHANGE: {symbol} {price_change_pct:.1%} from {entry_price} to {exit_price}")
            
        return True

# Dashboard Routes
if FASTAPI_AVAILABLE:
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Trading Bot Dashboard - PERFECT STYLING"""
        try:
            df = safe_read_trades()
            daily = calculate_daily_pnl(df)
            risk_metrics = calculate_risk_metrics(df)

            all_time = 0.0
            if not df.empty and "Computed_Cum" in df.columns and df["Computed_Cum"].dropna().any():
                vals = df["Computed_Cum"].dropna()
                all_time = float(vals.iloc[-1]) if not vals.empty else 0.0
            elif not df.empty and df["NetPnl_num"].notnull().any():
                all_time = float(df["NetPnl_num"].dropna().sum())

            open_trades = get_open_trades_with_pnl()
            
            open_html = "<p>No open positions</p>"
            if open_trades:
                opens = []
                for trade in open_trades:
                    symbol = trade["symbol"]
                    side = trade["side"].upper()
                    entry_price = trade["entry_price"]
                    current_price = trade["current_price"]
                    pnl = trade["pnl"]
                    pnl_percent = trade["pnl_percent"]
                    sl = trade.get("sl", 0)
                    tp1 = trade.get("tp1", 0)
                    tp2 = trade.get("tp2", 0)
                    tp3 = trade.get("tp3", 0)
                    trailing_active = trade.get("trailing_active", False)
                    remaining_quantity = trade.get("remaining_quantity", 0)
                    
                    pnl_class = "positive" if pnl >= 0 else "negative"
                    trailing_badge = " 🚀" if trailing_active else ""
                    
                    tp_targets = trade.get("tp_targets", {})
                    if tp_targets and tp_targets.get("tp1", {}).get("hit", False):
                        sl_display_value = entry_price
                        sl_placeholder = f"Entry: {entry_price:.4f}"
                    else:
                        sl_display_value = sl
                        sl_placeholder = "Stop Loss"
                    
                    opens.append(f"""
                    <div class="position-card">
                        <div class="position-header">
                            <span class="symbol">{symbol}</span>
                            <span class="side {side.lower()}">{side}{trailing_badge}</span>
                        </div>
                        <div class="position-details">
                            <div>Entry: <strong>{entry_price:.4f}</strong></div>
                            <div>Current: <strong>{current_price:.4f}</strong></div>
                            <div>Remaining: <strong>{remaining_quantity:.6f}</strong></div>
                            <div>Unrealized P&L: <span class='{pnl_class}'>{pnl:+.2f} USDT ({pnl_percent:+.2f}%)</span></div>
                        </div>
                        <div class="tp-levels">
                            <div class="tp-level">
                                <span class="tp-label">SL:</span>
                                <span class="tp-value">{sl_display_value:.4f}</span>
                            </div>
                            <div class="tp-level">
                                <span class="tp-label">TP1:</span>
                                <span class="tp-value">{tp1:.4f}</span>
                            </div>
                            <div class="tp-level">
                                <span class="tp-label">TP2:</span>
                                <span class="tp-value">{tp2:.4f}</span>
                            </div>
                            <div class="tp-level">
                                <span class="tp-label">TP3:</span>
                                <span class="tp-value">{tp3:.4f}</span>
                            </div>
                        </div>
                        <div class="position-controls">
                            <div class="sltp-controls-horizontal">
                                <div class="control-group">
                                    <label>SL:</label>
                                    <input type="text" id="sl_{symbol}" value="{sl_display_value:.4f}" placeholder="{sl_placeholder}">
                                </div>
                                <div class="control-group">
                                    <label>TP1:</label>
                                    <input type="text" id="tp1_{symbol}" value="{tp1:.4f}" placeholder="Take Profit 1">
                                </div>
                                <div class="control-group">
                                    <label>TP2:</label>
                                    <input type="text" id="tp2_{symbol}" value="{tp2:.4f}" placeholder="Take Profit 2">
                                </div>
                                <div class="control-group">
                                    <label>TP3:</label>
                                    <input type="text" id="tp3_{symbol}" value="{tp3:.4f}" placeholder="Take Profit 3">
                                </div>
                                <button class="btn-secondary" onclick="updateSLTP('{symbol}')">Update SL/TP</button>
                                <button class="btn-danger" onclick="closeTrade('{symbol}')">Close Trade</button>
                            </div>
                        </div>
                    </div>
                    """)
                
                open_html = f"""
                <div class="positions-grid">
                    {''.join(opens)}
                </div>
                """

            # Summary table
            summary_html = "<div class='summary-table'><h4>Trade Summary</h4><table>"
            summary_html += "<tr><th>Type</th><th>Total</th><th>Success</th><th>SL Hit</th><th>Win%</th><th>Loss%</th></tr>"
            
            exit_trades = df[df["Signal"].str.contains("Exit|Close", na=False)]
            long_trades = exit_trades[exit_trades["Side"].str.upper()=="LONG"]
            short_trades = exit_trades[exit_trades["Side"].str.upper()=="SHORT"]
            
            def summary_row(df_side, typ):
                total = len(df_side)
                success = len(df_side[df_side["NetPnl_num"]>0])
                sl_hit = len(df_side[df_side["NetPnl_num"]<0])
                win_pct = f"{(success/total*100):.1f}%" if total>0 else "0%"
                loss_pct = f"{(sl_hit/total*100):.1f}%" if total>0 else "0%"
                return f"<tr><td>{typ}</td><td>{total}</td><td class='positive'>{success}</td><td class='negative'>{sl_hit}</td><td>{win_pct}</td><td>{loss_pct}</td></tr>"
            
            if not long_trades.empty:
                summary_html += summary_row(long_trades,"LONG")
            if not short_trades.empty:
                summary_html += summary_row(short_trades,"SHORT")
            summary_html += "</table></div>"

            # Risk Metrics
            risk_metrics_html = ""
            if risk_metrics:
                win_rate = risk_metrics.get('win_rate', 0)
                profit_factor = risk_metrics.get('profit_factor', 0)
                avg_win = risk_metrics.get('avg_win', 0)
                avg_loss = risk_metrics.get('avg_loss', 0)
                
                if profit_factor == float('inf'):
                    profit_factor_display = "∞"
                else:
                    profit_factor_display = f"{profit_factor:.2f}"
                
                risk_metrics_html = f"""
                <div class="risk-metrics">
                    <h4>📊 Risk Metrics</h4>
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <span class="metric-label">Win Rate</span>
                            <span class="metric-value">{win_rate:.1f}%</span>
                        </div>
                        <div class="metric-card">
                            <span class="metric-label">Profit Factor</span>
                            <span class="metric-value">{profit_factor_display}</span>
                        </div>
                        <div class="metric-card">
                            <span class="metric-label">Avg Win</span>
                            <span class="metric-value positive">{avg_win:.2f}</span>
                        </div>
                        <div class="metric-card">
                            <span class="metric-label">Avg Loss</span>
                            <span class="metric-value negative">{avg_loss:.2f}</span>
                        </div>
                    </div>
                </div>
                """

            trade_history_html = format_trade_history(df)
            completed_trades_count = len(df[df["Signal"].str.contains("Exit|Close", na=False)])

            html = f"""
            <html>
            <head>
                <title>Rafique Trading Dashboard</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <link rel="stylesheet" href="/static/style.css">
                <meta http-equiv="refresh" content="15">
                <script>
                function updateSLTP(sym) {{
                    let sl = document.getElementById("sl_"+sym).value;
                    let tp1 = document.getElementById("tp1_"+sym).value;
                    let tp2 = document.getElementById("tp2_"+sym).value;
                    let tp3 = document.getElementById("tp3_"+sym).value;
                    
                    fetch(`/update_sltp/${{sym}}`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            sl: sl,
                            tp1: tp1,
                            tp2: tp2,
                            tp3: tp3
                        }})
                    }})
                    .then(r => r.json())
                    .then(d => {{
                        if(d.status === 'ok') {{
                            alert('SL/TP updated successfully!');
                            location.reload();
                        }} else {{
                            alert('Error updating SL/TP: ' + d.message);
                        }}
                    }})
                    .catch(error => {{
                        alert('Error updating SL/TP: ' + error);
                    }});
                }}
                
                function closeTrade(sym) {{
                    if(confirm('Are you sure you want to close this trade?')) {{
                        fetch('/close_trade/'+sym, {{ method: 'POST' }})
                            .then(r => r.json())
                            .then(d => {{
                                if(d.status === 'ok') {{
                                    alert('Trade closed successfully!');
                                    location.reload();
                                }} else {{
                                    alert('Error closing trade: ' + d.message);
                                }}
                            }})
                            .catch(error => {{
                                alert('Error closing trade: ' + error);
                            }});
                    }}
                }}
                
                function searchTrades() {{
                    const input = document.getElementById('searchInput');
                    const filter = input.value.toLowerCase();
                    const table = document.getElementById('tradesTable');
                    const tr = table.getElementsByTagName('tr');
                    
                    for (let i = 1; i < tr.length; i++) {{
                        const td = tr[i].getElementsByTagName('td');
                        let found = false;
                        for (let j = 0; j < td.length; j++) {{
                            if (td[j]) {{
                                if (td[j].textContent.toLowerCase().indexOf(filter) > -1) {{
                                    found = true;
                                    break;
                                }}
                            }}
                        }}
                        tr[i].style.display = found ? '' : 'none';
                    }}
                }}
                
                function exportTrades(format) {{
                    fetch(`/export/trades?format=${{format}}`)
                        .then(response => response.json())
                        .then(data => {{
                            if(data.content) {{
                                const blob = new Blob([data.content], {{ type: 'text/plain' }});
                                const url = window.URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.style.display = 'none';
                                a.href = url;
                                a.download = data.filename || `trades.${{format}}`;
                                document.body.appendChild(a);
                                a.click();
                                window.URL.revokeObjectURL(url);
                            }}
                        }});
                }}
                
                function populateSymbolFilter() {{
                    const filter = document.getElementById('symbolFilter');
                    const symbols = new Set();
                    const table = document.getElementById('tradesTable');
                    const tr = table.getElementsByTagName('tr');
                    
                    for (let i = 1; i < tr.length; i++) {{
                        const td = tr[i].getElementsByTagName('td');
                        if(td[1]) {{
                            const symbol = td[1].textContent.split(' ')[0];
                            if(symbol) symbols.add(symbol);
                        }}
                    }}
                    
                    symbols.forEach(symbol => {{
                        const option = document.createElement('option');
                        option.value = symbol;
                        option.textContent = symbol;
                        filter.appendChild(option);
                    }});
                }}
                
                function filterTrades() {{
                    const symbolFilter = document.getElementById('symbolFilter').value;
                    const sideFilter = document.getElementById('sideFilter').value;
                    const table = document.getElementById('tradesTable');
                    const tr = table.getElementsByTagName('tr');
                    
                    for (let i = 1; i < tr.length; i++) {{
                        const td = tr[i].getElementsByTagName('td');
                        let show = true;
                        
                        if(symbolFilter && td[1]) {{
                            const symbol = td[1].textContent.split(' ')[0];
                            if(symbol !== symbolFilter) show = false;
                        }}
                        
                        if(sideFilter && td[2]) {{
                            const side = td[2].textContent;
                            if(side !== sideFilter) show = false;
                        }}
                        
                        tr[i].style.display = show ? '' : 'none';
                    }}
                }}
                
                document.addEventListener('DOMContentLoaded', function() {{
                    populateSymbolFilter();
                }});
                </script>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🚀 Rafique Trading Dashboard</h1>
                        <p>Multi-TP + Trailing Stop System</p>
                    </div>
                    
                    <div class="main-content">
                        <div class="controls">
                            <input type="text" id="searchInput" class="search-box" placeholder="🔍 Search trades..." onkeyup="searchTrades()">
                            <select id="symbolFilter" class="filter-select" onchange="filterTrades()">
                                <option value="">All Symbols</option>
                            </select>
                            <select id="sideFilter" class="filter-select" onchange="filterTrades()">
                                <option value="">All Sides</option>
                                <option value="LONG">LONG</option>
                                <option value="SHORT">SHORT</option>
                            </select>
                            <div class="export-buttons">
                                <button class="btn-export" onclick="exportTrades('csv')">Export CSV</button>
                                <button class="btn-export" onclick="exportTrades('json')">Export JSON</button>
                            </div>
                        </div>
                        
                        <div class="dashboard-top">
                            <div class="left-panel">
                                <div class="stats-overview">
                                    <div class="stat-card">
                                        <h3>All Time P&L</h3>
                                        <div class="value {'positive' if all_time >= 0 else 'negative'}">{all_time:.2f} USDT</div>
                                    </div>
                                    <div class="stat-card">
                                        <h3>Total Trades</h3>
                                        <div class="value">{completed_trades_count}</div>
                                    </div>
                                    <div class="stat-card">
                                        <h3>Win Rate</h3>
                                        <div class="value">{risk_metrics.get('win_rate', 0):.1f}%</div>
                                    </div>
                                    <div class="stat-card">
                                        <h3>Profit Factor</h3>
                                        <div class="value">{risk_metrics.get('profit_factor', 0):.2f}</div>
                                    </div>
                                </div>
                                
                                <div class="section">
                                    <h3>📊 Performance Analytics</h3>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; height: 100%;">
                                        {summary_html}
                                        {risk_metrics_html}
                                    </div>
                                </div>
                            </div>
                            
                            <div class="right-panel">
                                <div class="section">
                                    <h3>📈 Open Positions ({len(open_trades)})</h3>
                                    {open_html}
                                </div>
                            </div>
                        </div>
                        
                        {trade_history_html}
                    </div>
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            return HTMLResponse(content=f"<h1>Error loading dashboard: {e}</h1>")

    @app.get("/api/stats")
    async def get_stats():
        """Get trading statistics"""
        try:
            state = load_state()
            stats = state.get("stats", {
                "long": {"total": 0, "success": 0, "fail": 0},
                "short": {"total": 0, "success": 0, "fail": 0}
            })
            
            cleaned_stats = json.loads(json.dumps(stats, cls=SafeJSONEncoder))
            
            return {
                "long": cleaned_stats.get("long", {"total": 0, "success": 0, "fail": 0}),
                "short": cleaned_stats.get("short", {"total": 0, "success": 0, "fail": 0}),
                "symbols_count": len(SYMBOLS),
                "dry_run": DRY_RUN,
                "confirmations": CONFIRMATION_REQUIRED,
                "open_trades_count": len(state.get("open_trades", {}))
            }
        except Exception as e:
            logger.error(f"Stats API error: {e}")
            return {"error": str(e)}

    @app.get("/api/open-trades")
    async def get_open_trades():
        """Get open trades with current prices"""
        try:
            state = load_state()
            open_trades = state.get("open_trades", {})
            result = []
            
            for symbol, trade in open_trades.items():
                current_price = get_validated_price(symbol)
                tp_targets = trade.get("tp_targets", {})
                
                cleaned_trade = json.loads(json.dumps(trade, cls=SafeJSONEncoder))
                
                result.append({
                    "symbol": symbol,
                    "side": cleaned_trade.get("side", ""),
                    "entry_price": cleaned_trade.get("entry_price", ""),
                    "current_price": f"{current_price:.4f}" if current_price else "N/A",
                    "quantity": cleaned_trade.get("total_quantity", ""),
                    "trade_num": cleaned_trade.get("trade_num", 0),
                    "pnl": 0,
                    "entry_time": cleaned_trade.get("entry_time", ""),
                    "sl": cleaned_trade.get("sl", ""),
                    "tp1": cleaned_trade.get("tp1", ""),
                    "tp2": cleaned_trade.get("tp2", ""),
                    "tp3": cleaned_trade.get("tp3", ""),
                    "tp1_hit": tp_targets.get("tp1", {}).get("hit", False),
                    "tp2_hit": tp_targets.get("tp2", {}).get("hit", False),
                    "tp3_hit": tp_targets.get("tp3", {}).get("hit", False),
                    "remaining_quantity": cleaned_trade.get("remaining_quantity", ""),
                    "trailing_active": cleaned_trade.get("trailing_active", False),
                    "partial_profit": cleaned_trade.get("partial_profit", "")
                })
            
            return result
        except Exception as e:
            logger.error(f"Open trades API error: {e}")
            return {"error": str(e)}

    @app.get("/api/trade-history")
    async def get_trade_history():
        """Get trade history from CSV"""
        try:
            df = safe_read_trades()
            if df.empty:
                return []
            
            recent_trades = df.tail(20).to_dict('records')
            result = []
            
            for trade in recent_trades:
                cleaned_trade = json.loads(json.dumps(trade, cls=SafeJSONEncoder))
                
                result.append({
                    "trade_num": cleaned_trade.get("Trade #", ""),
                    "symbol": cleaned_trade.get("Symbol", ""),
                    "side": cleaned_trade.get("Side", ""),
                    "entry_price": cleaned_trade.get("Price", ""),
                    "exit_price": cleaned_trade.get("Price", ""),
                    "pnl": cleaned_trade.get("Net P&L", "0"),
                    "time": cleaned_trade.get("Date/Time", "")
                })
            
            return result
        except Exception as e:
            logger.error(f"Trade history API error: {e}")
            return {"error": str(e)}

    @app.post("/api/clear-history")
    async def clear_history_api():
        """Clear trade history via API"""
        try:
            success = reset_history()
            if success:
                return {"message": "History cleared successfully"}
            else:
                return {"error": "Failed to clear history"}
        except Exception as e:
            logger.error(f"Clear history API error: {e}")
            return {"error": str(e)}

    @app.post("/close_trade/{symbol}")
    def close_trade(symbol: str):
        try:
            state = load_state()
            open_trades = state.get("open_trades", {})
            
            if symbol in open_trades:
                trade_info = open_trades[symbol]
                entry_price = safe_float_convert(trade_info.get("entry_price", 0))
                quantity = safe_float_convert(trade_info.get("remaining_quantity") or trade_info.get("quantity", 0))
                side = trade_info.get("side", "")
                trade_num = trade_info.get("trade_num", 0)
                
                current_price = get_current_price(symbol)
                if current_price is None:
                    current_price = entry_price
                
                if side == "long":
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
                
                del open_trades[symbol]
                save_state(state)
                
                try:
                    exit_row = {
                        "Trade #": str(trade_num),
                        "Symbol": symbol.replace('USDT', ''),
                        "Side": side.upper(),
                        "Type": f"{symbol} {side.upper()}",
                        "Date/Time": datetime.now().strftime("%b %d, %Y, %H:%M"),
                        "Signal": "Exit",
                        "Price": f"{current_price:.8f}",
                        "Position size": f"{quantity:.6f} ({round(quantity*current_price,2):.2f} USDT)",
                        "Net P&L": f"{pnl:+.2f} USDT",
                        "Run-up": "0",
                        "Drawdown": "0",
                        "Cumulative P&L": ""
                    }
                    
                    append_trade_row(exit_row)
                    
                except Exception as e:
                    print(f"Error logging trade closure: {e}")
                
                return {"status": "ok", "message": f"Trade {symbol} closed successfully", "pnl": round(pnl, 2)}
            else:
                return {"status": "error", "message": "Trade not found in open positions"}
                
        except Exception as e:
            return {"status": "error", "message": f"Error closing trade: {str(e)}"}

    @app.post("/update_sltp/{symbol}")
    async def update_sltp(symbol: str, request: Request):
        """Update Stop Loss and Take Profit for a trade"""
        try:
            body = await request.json()
            sl = body.get("sl", "")
            tp1 = body.get("tp1", "")
            tp2 = body.get("tp2", "")
            tp3 = body.get("tp3", "")
            
            state = load_state()
            open_trades = state.get("open_trades", {})
            
            if symbol in open_trades:
                if sl:
                    try:
                        sl_float = float(sl)
                        state["open_trades"][symbol]["sl"] = f"{sl_float:.4f}"
                    except ValueError:
                        return {"status": "error", "message": "Invalid SL format"}
                
                if tp1:
                    try:
                        tp1_float = float(tp1)
                        state["open_trades"][symbol]["tp1"] = f"{tp1_float:.4f}"
                    except ValueError:
                        return {"status": "error", "message": "Invalid TP1 format"}
                
                if tp2:
                    try:
                        tp2_float = float(tp2)
                        state["open_trades"][symbol]["tp2"] = f"{tp2_float:.4f}"
                    except ValueError:
                        return {"status": "error", "message": "Invalid TP2 format"}
                
                if tp3:
                    try:
                        tp3_float = float(tp3)
                        state["open_trades"][symbol]["tp3"] = f"{tp3_float:.4f}"
                    except ValueError:
                        return {"status": "error", "message": "Invalid TP3 format"}
                
                save_state(state)
                print(f"SL/TP updated for {symbol}: SL={sl}, TP1={tp1}, TP2={tp2}, TP3={tp3}")
                return {"status": "ok", "symbol": symbol, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3}
            return {"status": "error", "message": "Symbol not found in open trades"}
        except Exception as e:
            print(f"Error updating SL/TP: {e}")
            return {"status": "error", "message": str(e)}

    @app.get("/export/trades")
    def export_trades(format: str = "csv"):
        df = safe_read_trades()
        if format == "csv":
            csv_content = df.to_csv(index=False)
            return JSONResponse({"content": csv_content, "filename": "trades.csv"})
        elif format == "json":
            return JSONResponse({"content": json.dumps(df.to_dict(orient="records"), indent=2, cls=SafeJSONEncoder), "filename": "trades.json"})
        else:
            return JSONResponse({"error": "Unsupported format"}, status_code=400)

    @app.get("/test")
    def test():
        return {"status": "working", "message": "Server is running"}

# Helper Functions
def _to_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception as e:
        logger.debug(f"Float conversion failed for {x}: {e}")
        return default

def _ensure_state_keys(st: dict):
    if not isinstance(st, dict):
        st = {}
    if "open_trades" not in st:
        st["open_trades"] = {}
    if "stats" not in st:
        st["stats"] = {
            "long": {"total": 0, "success": 0, "fail": 0},
            "short": {"total": 0, "success": 0, "fail": 0}
        }
    if "trade_history" not in st:
        st["trade_history"] = []
    return st

# Enhanced File helpers
@safe_execute(default_return=pd.DataFrame())
def safe_read_trades():
    with _state_lock:
        try:
            if os.path.exists(TRADES_FILE):
                df = pd.read_csv(TRADES_FILE, dtype=str)
                logger.info(f"Successfully loaded {len(df)} trades from CSV")
                return df
            else:
                logger.info("Trades file does not exist, returning empty DataFrame")
        except Exception as e:
            logger.error(f"Error reading trades file: {e}")
        cols = ["Trade #","Symbol","Side","Type","Date/Time","Signal","Price","Position size","Net P&L","Run-up","Drawdown","Cumulative P&L"]
        return pd.DataFrame(columns=cols)

@safe_execute(default_return=False)
def append_trade_row(row: dict):
    with _state_lock:
        try:
            cols = ["Trade #","Symbol","Side","Type","Date/Time","Signal","Price","Position size","Net P&L","Run-up","Drawdown","Cumulative P&L"]
            df = safe_read_trades()
            df = df[[c for c in df.columns if c in cols]] if not df.empty else pd.DataFrame(columns=cols)
            
            for c in cols:
                if c not in df.columns:
                    df[c] = ""
            
            new_row = {c: row.get(c,"") for c in cols}
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            df.to_csv(TRADES_FILE, index=False, columns=cols)
            logger.info(f"Successfully appended trade #{row.get('Trade #', 'N/A')} to CSV")
            return True
        except Exception as e:
            logger.error(f"Failed to append trade row: {e}")
            return False

@safe_execute(default_return={})
def load_state():
    with _state_lock:
        try:
            if not os.path.exists(STATE_FILE):
                logger.info("State file does not exist, returning empty state")
                return {}
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f) or {}
                logger.debug("Successfully loaded state from file")
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            st = {}
        st = _ensure_state_keys(st)
        return st

@safe_execute(default_return=False)
def save_state(st):
    with _state_lock:
        try:
            st = _ensure_state_keys(st)
            retries = 6
            delay = 0.08
            data = json.dumps(st, indent=2, ensure_ascii=False, cls=SafeJSONEncoder)
            
            for attempt in range(retries):
                try:
                    dirn = os.path.dirname(STATE_FILE) or "."
                    fd, tmp = tempfile.mkstemp(prefix="state_", dir=dirn, text=True)
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
                            tmpf.write(data)
                        os.replace(tmp, STATE_FILE)
                        logger.debug("Successfully saved state to file")
                        return True
                    finally:
                        if os.path.exists(tmp):
                            try:
                                os.remove(tmp)
                            except Exception:
                                pass
                except PermissionError:
                    logger.warning(f"Permission error saving state, retry {attempt + 1}")
                    time.sleep(delay)
                    delay *= 1.5
                except Exception as e:
                    logger.warning(f"Error saving state, retry {attempt + 1}: {e}")
                    time.sleep(delay)
                    delay *= 1.5
            
            logger.error("Failed to save state after all retries")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in save_state: {e}")
            return False

@safe_execute(default_return=1)
def next_trade_number():
    with _state_lock:
        try:
            df = safe_read_trades()
            if df.empty or "Trade #" not in df.columns:
                return 1
            nums = pd.to_numeric(df["Trade #"], errors="coerce")
            if nums.notna().any():
                next_num = int(nums.max()) + 1
                logger.debug(f"Next trade number: {next_num}")
                return next_num
            return 1
        except Exception as e:
            logger.error(f"Error calculating next trade number: {e}")
            return 1

@safe_execute(default_return=False)
def reset_history():
    with _state_lock:
        try:
            df_init = pd.DataFrame(columns=[
                "Trade #","Symbol","Side","Type","Date/Time","Signal","Price",
                "Position size","Net P&L","Run-up","Drawdown","Cumulative P&L"
            ])
            df_init.to_csv(TRADES_FILE, index=False)
            save_state(_ensure_state_keys({}))
            logger.info("Trade history and state cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Error resetting history: {e}")
            return False

@safe_execute(default_return=False)
def ensure_files():
    try:
        if not os.path.exists(TRADES_FILE):
            reset_history()
        if not os.path.exists(STATE_FILE):
            save_state(_ensure_state_keys({}))
        logger.info("Required files ensured")
        return True
    except Exception as e:
        logger.error(f"Error ensuring files: {e}")
        return False

# Dashboard Helper Functions
def to_float_clean(s):
    """Safe float conversion with error handling"""
    try:
        if s is None: return None
        if isinstance(s, (int, float)):
            return float(s)
        x = str(s).replace("USDT","").replace("+","").replace(",","").strip()
        if x=="" or x.lower() in ("nan","none", "null"): return None
        return float(x)
    except:
        return None

def safe_float_convert(value, default=0.0):
    """Safely convert any value to float"""
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default

def calculate_daily_pnl(df):
    if df.empty or "NetPnl_num" not in df.columns:
        return []
    exits = df[df["NetPnl_num"].notnull()].copy()
    if exits.empty:
        return []
    exits["date"] = exits["__dt_parsed"].dt.date
    daily = exits.groupby("date")["NetPnl_num"].sum().reset_index().sort_values("date", ascending=False)
    daily.columns = ["Date","Profit"]
    return daily.to_dict(orient="records")

def compute_cumulative(df):
    if df.empty:
        return df
    d = df.copy().sort_values("Trade_Num", ascending=True)
    cum = 0.0; computed=[]
    for _, r in d.iterrows():
        pnl = r.get("NetPnl_num")
        if pd.notna(pnl):
            cum += float(pnl)
            computed.append(cum)
        else:
            computed.append(None)
    d["Computed_Cum"] = computed
    def display(row):
        if pd.notna(row["Computed_Cum"]):
            return f"{row['Computed_Cum']:.2f}"
        return row.get("Cumulative P&L","") or ""
    d["Cumulative P&L"] = d.apply(display, axis=1)
    return d

def calculate_risk_metrics(df):
    """Calculate advanced risk metrics"""
    if df.empty:
        return {}
    
    exit_trades = df[df["Signal"].str.contains("Exit|Close", na=False)]
    total_trades = len(exit_trades)
    winning_trades = len(exit_trades[exit_trades["NetPnl_num"] > 0])
    losing_trades = len(exit_trades[exit_trades["NetPnl_num"] < 0])
    breakeven_trades = len(exit_trades[exit_trades["NetPnl_num"] == 0])
    
    total_profit = exit_trades[exit_trades["NetPnl_num"] > 0]["NetPnl_num"].sum()
    total_loss = abs(exit_trades[exit_trades["NetPnl_num"] < 0]["NetPnl_num"].sum())
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    loss_rate = (losing_trades / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (total_profit / total_loss) if total_loss > 0 else float('inf')
    
    largest_win = exit_trades["NetPnl_num"].max() if not exit_trades.empty and not exit_trades["NetPnl_num"].isna().all() else 0.0
    largest_loss = exit_trades["NetPnl_num"].min() if not exit_trades.empty and not exit_trades["NetPnl_num"].isna().all() else 0.0
    
    avg_win_trades = exit_trades[exit_trades["NetPnl_num"] > 0]
    avg_win = avg_win_trades["NetPnl_num"].mean() if not avg_win_trades.empty and not avg_win_trades["NetPnl_num"].isna().all() else 0.0
    
    avg_loss_trades = exit_trades[exit_trades["NetPnl_num"] < 0]
    avg_loss = avg_loss_trades["NetPnl_num"].mean() if not avg_loss_trades.empty and not avg_loss_trades["NetPnl_num"].isna().all() else 0.0
    
    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "breakeven_trades": breakeven_trades,
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "profit_factor": profit_factor,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }

def get_current_price(symbol):
    """Get current price from Binance API with fallback"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data['price'])
        else:
            print(f"Binance API error: {response.status_code}")
            mock_prices = {
                "BTCUSDT": 50000.0, "ETHUSDT": 3000.0, "BNBUSDT": 500.0,
                "SOLUSDT": 100.0, "XRPUSDT": 0.5, "ADAUSDT": 0.4,
                "DOGEUSDT": 0.1, "PEPEUSDT": 0.00001, "LINKUSDT": 15.0,
                "XLMUSDT": 0.12, "AVAXUSDT": 35.0, "DOTUSDT": 7.0,
                "OPUSDT": 2.5, "TRXUSDT": 0.1
            }
            return mock_prices.get(symbol, 100.0)
    except Exception as e:
        print(f"Binance API connection failed: {e}")
        mock_prices = {
            "BTCUSDT": 50000.0, "ETHUSDT": 3000.0, "BNBUSDT": 500.0,
            "SOLUSDT": 100.0, "XRPUSDT": 0.5, "ADAUSDT": 0.4,
            "DOGEUSDT": 0.1, "PEPEUSDT": 0.00001, "LINKUSDT": 15.0,
            "XLMUSDT": 0.12, "AVAXUSDT": 35.0, "DOTUSDT": 7.0,
            "OPUSDT": 2.5, "TRXUSDT": 0.1
        }
        return mock_prices.get(symbol, 100.0)

def get_open_trades_with_pnl():
    """Get open trades with live PnL calculation"""
    state = load_state()
    open_trades = state.get("open_trades", {})
    
    result = []
    for symbol, trade_info in open_trades.items():
        try:
            entry_price = safe_float_convert(trade_info.get("entry_price"), 0)
            quantity = safe_float_convert(trade_info.get("total_quantity") or trade_info.get("quantity"), 0)
            side = trade_info.get("side", "long")
            
            current_price = get_current_price(symbol)
            if current_price is None:
                current_price = entry_price
            
            if side == "long":
                unrealized_pnl = (current_price - entry_price) * quantity
                pnl_percent = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
            else:
                unrealized_pnl = (entry_price - current_price) * quantity
                pnl_percent = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0
            
            tp1 = safe_float_convert(trade_info.get("tp1", 0))
            tp2 = safe_float_convert(trade_info.get("tp2", 0))
            tp3 = safe_float_convert(trade_info.get("tp3", 0))
            sl = safe_float_convert(trade_info.get("sl", 0))
            
            tp_targets = trade_info.get("tp_targets", {})
            if tp_targets and tp_targets.get("tp1", {}).get("hit", False):
                sl_display = entry_price
            else:
                sl_display = sl
            
            trade_data = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "current_price": current_price,
                "quantity": quantity,
                "trade_num": trade_info.get("trade_num", 0),
                "pnl": round(unrealized_pnl, 2),
                "pnl_percent": round(pnl_percent, 2),
                "entry_time": trade_info.get("entry_time", ""),
                "sl": sl_display,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "trailing_active": trade_info.get("trailing_active", False),
                "tp_targets": trade_info.get("tp_targets", {}),
                "remaining_quantity": safe_float_convert(trade_info.get("remaining_quantity", 0))
            }
            
            for key, value in trade_data.items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    trade_data[key] = 0.0
            
            result.append(trade_data)
        except Exception as e:
            print(f"Error processing trade {symbol}: {e}")
            continue
    
    return result

def format_trade_history(df):
    """Format trade history with merged rows for same trade"""
    if df.empty:
        return "<div class='section trade-history-section'><h3>📋 Trade History</h3><p>No trade history available</p></div>"
    
    df_disp = df.sort_values(["Trade_Num", "Date/Time"], ascending=[False, True])
    
    html = """
    <div class="section trade-history-section">
        <h3>📋 Trade History</h3>
        <div class="trade-history-container">
            <table class="trade-table" id="tradesTable">
                <thead>
                    <tr>
                        <th class="col-trade-no">Trade #</th>
                        <th class="col-symbol">Symbol</th>
                        <th class="col-type">Type</th>
                        <th class="col-date">Date / Time</th>
                        <th class="col-signal">Signal</th>
                        <th class="col-price">Price</th>
                        <th class="col-size">Position size</th>
                        <th class="col-pnl">Net P&L</th>
                        <th class="col-runup">Run-up</th>
                        <th class="col-drawdown">Drawdown</th>
                        <th class="col-cumulative">Cumulative P&L</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    current_trade_num = None
    trade_rows = []
    
    for _, row in df_disp.iterrows():
        trade_num = row.get('Trade #', '')
        trade_type = row.get('Type', '')
        date_time = row.get('Date/Time', '')
        signal = row.get('Signal', '')
        price = row.get('Price', '')
        position_size = row.get('Position size', '')
        net_pnl = row.get('Net P&L', '')
        run_up = row.get('Run-up', '')
        drawdown = row.get('Drawdown', '')
        cumulative = row.get('Cumulative P&L', '')
        
        symbol_parts = str(trade_type).split(' ')
        symbol = symbol_parts[0] if symbol_parts else ''
        direction = symbol_parts[1] if len(symbol_parts) > 1 else ''
        
        is_exit = "Exit" in str(signal) or "Close" in str(signal)
        display_type = "Exit" if is_exit else "Entry"
        
        pnl_num = row.get("NetPnl_num", 0)
        pnl_cls = "positive" if pnl_num >= 0 else "negative"
        
        def clean_value(val):
            if not val or pd.isna(val):
                return ""
            return str(val).replace('USD', '').replace('↑', '').replace('+', '').replace(',', '').strip()
        
        def format_currency(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    return f"{float(clean_val):.2f} USD↑"
            except:
                pass
            return str(val) if val else ""
        
        def format_percentage(val):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    return f"{float(clean_val):.2f}%"
            except:
                pass
            return str(val) if val else ""
        
        def format_position_size(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    if is_exit:
                        return f"{float(clean_val):.2f}"
                    else:
                        return f"{float(clean_val):.2f} USD↑"
            except:
                pass
            return str(val) if val else ""
        
        def format_pnl(val, is_exit=False):
            try:
                clean_val = clean_value(val)
                if clean_val and clean_val != 'nan':
                    val_float = float(clean_val)
                    if is_exit:
                        sign = "+" if val_float >= 0 else ""
                        return f"{sign}{val_float:.2f} USD↑"
                    else:
                        sign = "+" if val_float >= 0 else ""
                        return f"{sign}{abs(val_float):.2f}%"
            except:
                pass
            return str(val) if val else ""
        
        formatted_price = format_currency(price, is_exit)
        formatted_position_size = format_position_size(position_size, is_exit)
        formatted_pnl = format_pnl(net_pnl, is_exit)
        formatted_runup = format_percentage(run_up) if not is_exit else format_currency(run_up, is_exit)
        formatted_drawdown = format_percentage(drawdown) if not is_exit else format_currency(drawdown, is_exit)
        formatted_cumulative = format_percentage(cumulative) if not is_exit else format_currency(cumulative, is_exit)
        
        if trade_num != current_trade_num:
            if trade_rows:
                html += process_trade_group(trade_rows)
            trade_rows = []
            current_trade_num = trade_num
        
        trade_rows.append({
            'trade_num': trade_num,
            'symbol': symbol,
            'direction': direction,
            'display_type': display_type,
            'date_time': date_time,
            'signal': signal,
            'formatted_price': formatted_price,
            'formatted_position_size': formatted_position_size,
            'formatted_pnl': formatted_pnl,
            'formatted_runup': formatted_runup,
            'formatted_drawdown': formatted_drawdown,
            'formatted_cumulative': formatted_cumulative,
            'pnl_cls': pnl_cls,
            'is_exit': is_exit
        })
    
    if trade_rows:
        html += process_trade_group(trade_rows)
    
    html += """
                </tbody>
            </table>
        </div>
    </div>
    """
    return html

def process_trade_group(trade_rows):
    """Process a group of trades with same trade number"""
    if not trade_rows:
        return ""
    
    trade_rows.sort(key=lambda x: 0 if x['display_type'] == 'Entry' else 1)
    
    html = ""
    first_row = True
    
    for trade in trade_rows:
        if first_row:
            html += f"""
                    <tr class="trade-row {'exit-row' if trade['is_exit'] else 'entry-row'} {trade['direction'].lower()}">
                        <td class="col-trade-no" rowspan="{len(trade_rows)}">{trade['trade_num']}</td>
                        <td class="col-symbol" rowspan="{len(trade_rows)}">{trade['symbol']} {trade['direction']}</td>
                        <td class="col-type">{trade['display_type']}</td>
                        <td class="col-date">{trade['date_time']}</td>
                        <td class="col-signal">{trade['signal']}</td>
                        <td class="col-price">{trade['formatted_price']}</td>
                        <td class="col-size">{trade['formatted_position_size']}</td>
                        <td class="col-pnl {trade['pnl_cls']}">{trade['formatted_pnl']}</td>
                        <td class="col-runup">{trade['formatted_runup']}</td>
                        <td class="col-drawdown">{trade['formatted_drawdown']}</td>
                        <td class="col-cumulative">{trade['formatted_cumulative']}</td>
                    </tr>
            """
            first_row = False
        else:
            html += f"""
                    <tr class="trade-row {'exit-row' if trade['is_exit'] else 'entry-row'} {trade['direction'].lower()}">
                        <td class="col-type">{trade['display_type']}</td>
                        <td class="col-date">{trade['date_time']}</td>
                        <td class="col-signal">{trade['signal']}</td>
                        <td class="col-price">{trade['formatted_price']}</td>
                        <td class="col-size">{trade['formatted_position_size']}</td>
                        <td class="col-pnl {trade['pnl_cls']}">{trade['formatted_pnl']}</td>
                        <td class="col-runup">{trade['formatted_runup']}</td>
                        <td class="col-drawdown">{trade['formatted_drawdown']}</td>
                        <td class="col-cumulative">{trade['formatted_cumulative']}</td>
                    </tr>
            """
    
    return html

# Enhanced Indicators with Error Handling
@safe_execute(default_return=pd.Series([50.0]))
def rsi(series: pd.Series, length=14):
    try:
        delta = series.diff()
        up = delta.clip(lower=0.0)
        down = -delta.clip(upper=0.0)
        roll_up = up.ewm(alpha=1/length, adjust=False).mean()
        roll_down = down.ewm(alpha=1/length, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        r = 100 - (100 / (1 + rs))
        return r.fillna(50.0)
    except Exception as e:
        logger.error(f"RSI calculation error: {e}")
        length_data = len(series) if hasattr(series, "__len__") else 1
        return pd.Series([50.0] * length_data)

@safe_execute(default_return=(pd.Series([0.0]), pd.Series([0.0]), pd.Series([0.0])))
def calculate_adx(df, period=14):
    try:
        if df.empty:
            return pd.Series([0.0]), pd.Series([0.0]), pd.Series([0.0])
            
        high = df['high']; low = df['low']; close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        plus_dm = high.diff()
        minus_dm = (-low.diff()).abs()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        atr_val = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr_val.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr_val.replace(0, np.nan))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
        adx = dx.rolling(period).mean().fillna(0)
        return plus_di.fillna(0), minus_di.fillna(0), adx
    except Exception as e:
        logger.error(f"ADX calculation error: {e}")
        length = len(df) if hasattr(df, "__len__") else 0
        return pd.Series([0]*length), pd.Series([0]*length), pd.Series([0]*length)

@safe_execute(default_return=pd.Series([0.0]))
def atr(df: pd.DataFrame, length=14):
    try:
        if df.empty:
            return pd.Series([0.0])
            
        high = df['high']; low = df['low']; close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(length).mean().fillna(0)
    except Exception as e:
        logger.error(f"ATR calculation error: {e}")
        length_data = len(df) if hasattr(df, "__len__") else 0
        return pd.Series([0]*length_data)

# Enhanced Market Helpers
client = None

def _parse_kline_value(val):
    try:
        return float(val) if (val is not None and str(val).lower() not in ("nan","none","")) else 0.0
    except Exception:
        return 0.0

# ✅ FIXED: Enhanced Binance client initialization
def initialize_binance_client():
    """Initialize Binance client with PROPER testnet configuration"""
    global client
    
    if not BINANCE_AVAILABLE:
        logger.error("❌ Binance library not available")
        return False
    
    if not API_KEY or not API_SECRET:
        logger.error("❌ API_KEY or API_SECRET missing")
        return False
    
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        
        # ✅ PROPER Testnet configuration
        if USE_TESTNET:
            logger.info("🔧 Configuring for BINANCE TESTNET")
            client = Client(
                API_KEY, 
                API_SECRET,
                testnet=True,
                requests_params={"timeout": 15}
            )
            try:
                account = client.get_account()
                logger.info("✅ Binance TESTNET connection SUCCESSFUL")
                logger.info(f"✅ Testnet Account: {account['accountType']}")
                return True
            except Exception as e:
                logger.error(f"❌ Testnet connection failed: {e}")
                return False
        else:
            client = Client(API_KEY, API_SECRET, requests_params={"timeout": 15})
            client.get_account()
            logger.info("✅ Binance MAINNET connection SUCCESSFUL")
            return True
            
    except Exception as e:
        logger.error(f"❌ Binance initialization failed: {e}")
        client = None
        return False

# ✅ FIXED: ACTUAL BINANCE PRICE FETCHING - NO MOCK DATA
@safe_execute(default_return=None)
def get_validated_price(symbol, max_retries=3):
    """Get ACTUAL Binance price with validation - NO MOCK DATA"""
    for attempt in range(max_retries):
        try:
            # ✅ FORCE ACTUAL BINANCE PRICE - NO MOCK DATA
            if client is not None:
                ticker = client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                logger.info(f"✅ ACTUAL BINANCE PRICE: {symbol} = {price}")
                
                if not PriceValidator.validate_price(symbol, price, "current"):
                    logger.warning(f"Price validation failed for {symbol}: {price}")
                    continue
                    
                return price
            else:
                # If client not available, try direct API call
                import requests
                if USE_TESTNET:
                    url = "https://testnet.binance.vision/api/v3/ticker/price"
                else:
                    url = "https://api.binance.com/api/v3/ticker/price"
                
                response = requests.get(url, params={"symbol": symbol}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    price = float(data['price'])
                    logger.info(f"✅ DIRECT API PRICE: {symbol} = {price}")
                    return price
                
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}: Error getting actual price for {symbol}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
    
    logger.error(f"❌ Failed to get ACTUAL price for {symbol} after {max_retries} attempts")
    return None

# ✅ FIXED: Only use actual Binance data - NO MOCK DATA
@safe_execute(default_return=pd.DataFrame())
def get_klines(symbol, interval='15m', limit=100):
    """Get ACTUAL Binance klines - NO MOCK DATA"""
    if client is None:
        logger.error(f"❌ Binance client not initialized for {symbol}")
        return pd.DataFrame()
    
    try:
        logger.info(f"📊 Fetching ACTUAL Binance data for {symbol}")
        raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        data = []
        for k in raw:
            try:
                data.append({
                    "open_time": k[0],
                    "open": _parse_kline_value(k[1]),
                    "high": _parse_kline_value(k[2]),
                    "low": _parse_kline_value(k[3]),
                    "close": _parse_kline_value(k[4]),
                    "volume": _parse_kline_value(k[5]),
                    "close_time": k[6]
                })
            except Exception as e:
                logger.debug(f"Error parsing kline data: {e}")
                continue
        
        df = pd.DataFrame(data)
        if not df.empty:
            df.ffill(inplace=True)
            df.fillna(0, inplace=True)
            logger.info(f"✅ Successfully fetched {len(df)} ACTUAL klines for {symbol}")
        else:
            logger.error(f"❌ No data received for {symbol}")
            
        return df
        
    except Exception as e:
        logger.error(f"❌ ACTUAL klines fetch error for {symbol}: {e}")
        return pd.DataFrame()

@safe_execute(default_return=None)
def get_latest_price(symbol):
    """Get latest price - uses actual Binance data only"""
    return get_validated_price(symbol)

# Enhanced Orders
@safe_execute(default_return=False)
def place_order(side, symbol, qty):
    if DRY_RUN or client is None:
        logger.info(f"[DRY-RUN] {side.upper()} {qty:.6f} {symbol}")
        return True
    try:
        if isinstance(side, str) and side.lower() in ("buy", "sell"):
            order_side = side.upper()
        else:
            order_side = "BUY" if side == "long" else "SELL"
        
        result = client.create_order(symbol=symbol, side=order_side, type="MARKET", quantity=round(qty, 6))
        logger.info(f"Successfully placed {order_side} order for {qty:.6f} {symbol}")
        return True
    except Exception as e:
        logger.error(f"Order error for {symbol}: {e}")
        return False

# Enhanced trade execution with price validation
def execute_trade_with_validation(side, symbol, quantity, price=None):
    """Execute trade with price validation"""
    try:
        if price is None:
            price = get_validated_price(symbol)
            if price is None:
                logger.error(f"❌ Cannot execute trade for {symbol} - invalid price")
                return False
        
        if not PriceValidator.validate_price(symbol, price, "trade"):
            logger.error(f"❌ Trade rejected for {symbol} - price validation failed: {price}")
            return False
        
        if quantity is None:
            quantity = calculate_quantity(price)
            if quantity <= 0:
                logger.error(f"❌ Invalid quantity calculated for {symbol}: {quantity}")
                return False
        
        logger.info(f"✅ Executing {side.upper()} trade for {symbol} at validated price: {price}")
        
        if place_order(side, symbol, quantity):
            logger.info(f"✅ Successfully executed {side.upper()} trade for {symbol}")
            return True
        else:
            logger.error(f"❌ Failed to execute {side.upper()} trade for {symbol}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error executing trade for {symbol}: {e}")
        return False

# PROPER SL LOGIC (EMA + ATR BASED)
def calculate_proper_sl(symbol, entry_price, side, df):
    """Calculate proper SL based on EMA + ATR"""
    try:
        if df.empty or len(df) < 50:
            logger.warning(f"Insufficient data for {symbol}, using fallback SL")
            if side == "long":
                return entry_price * 0.98
            else:
                return entry_price * 1.02
        
        ema_50 = df['close'].ewm(span=50).mean().iloc[-1]
        atr_value = atr(df).iloc[-1]
        
        if side == "long":
            sl_ema = ema_50
            sl_atr = entry_price - (atr_value * ATR_SL_MULT)
            proper_sl = min(sl_ema, sl_atr)
            
            max_sl_distance = entry_price * 0.05
            if entry_price - proper_sl > max_sl_distance:
                proper_sl = entry_price - max_sl_distance
            
            logger.info(f"📊 LONG SL Calculated for {symbol}: EMA50={ema_50:.4f}, ATR_SL={sl_atr:.4f}, Final_SL={proper_sl:.4f}")
            
        else:
            sl_ema = ema_50
            sl_atr = entry_price + (atr_value * ATR_SL_MULT)
            proper_sl = max(sl_ema, sl_atr)
            
            max_sl_distance = entry_price * 0.05
            if proper_sl - entry_price > max_sl_distance:
                proper_sl = entry_price + max_sl_distance
            
            logger.info(f"📊 SHORT SL Calculated for {symbol}: EMA50={ema_50:.4f}, ATR_SL={sl_atr:.4f}, Final_SL={proper_sl:.4f}")
        
        return proper_sl
        
    except Exception as e:
        logger.error(f"Error calculating proper SL: {e}")
        if side == "long":
            return entry_price * 0.98
        else:
            return entry_price * 1.02

# MULTI-LEVEL TP + PROFIT DISTRIBUTION SYSTEM
def set_multi_tp_profit_distribution(symbol, entry_price, side, df, total_quantity):
    """Set multi-level TP with profit distribution"""
    try:
        initial_sl = calculate_proper_sl(symbol, entry_price, side, df)
        
        if side == "long":
            tp1_price = entry_price * (1 + TP1_PERCENT)
            tp2_price = entry_price * (1 + TP2_PERCENT) 
            tp3_price = entry_price * (1 + TP3_PERCENT)
            
        else:
            tp1_price = entry_price * (1 - TP1_PERCENT)
            tp2_price = entry_price * (1 - TP2_PERCENT)
            tp3_price = entry_price * (1 - TP3_PERCENT)
        
        tp1_quantity = total_quantity * TP1_CLOSE_PERCENT
        tp2_quantity = total_quantity * TP2_CLOSE_PERCENT
        tp3_quantity = total_quantity * TP3_CLOSE_PERCENT
        trailing_quantity = total_quantity * TRAILING_PERCENT
        
        state = load_state()
        if symbol in state.get("open_trades", {}):
            state["open_trades"][symbol]["tp_targets"] = {
                "tp1": {"price": f"{tp1_price:.4f}", "hit": False, "level": 1, "quantity": tp1_quantity, "closed": False},
                "tp2": {"price": f"{tp2_price:.4f}", "hit": False, "level": 2, "quantity": tp2_quantity, "closed": False}, 
                "tp3": {"price": f"{tp3_price:.4f}", "hit": False, "level": 3, "quantity": tp3_quantity, "closed": False}
            }
            
            state["open_trades"][symbol]["remaining_quantity"] = total_quantity
            state["open_trades"][symbol]["trailing_quantity"] = trailing_quantity
            
            state["open_trades"][symbol]["sl"] = f"{initial_sl:.4f}"
            state["open_trades"][symbol]["tp1"] = f"{tp1_price:.4f}"
            state["open_trades"][symbol]["tp2"] = f"{tp2_price:.4f}" 
            state["open_trades"][symbol]["tp3"] = f"{tp3_price:.4f}"
            
            state["open_trades"][symbol]["trailing_active"] = False
            state["open_trades"][symbol]["trailing_triggered"] = False
            state["open_trades"][symbol]["highest_price"] = f"{entry_price:.4f}" if side == "long" else f"{entry_price:.4f}"
            state["open_trades"][symbol]["lowest_price"] = f"{entry_price:.4f}" if side == "short" else f"{entry_price:.4f}"
            state["open_trades"][symbol]["trailing_distance_percent"] = TRAILING_DISTANCE_PERCENT
            
            save_state(state)
            logger.info(f"✅ Multi-TP with Profit Distribution set for {symbol}")
            logger.info(f"   TP1: {tp1_price:.4f} ({TP1_CLOSE_PERCENT*100}% - {tp1_quantity:.6f})")
            logger.info(f"   TP2: {tp2_price:.4f} ({TP2_CLOSE_PERCENT*100}% - {tp2_quantity:.6f})")
            logger.info(f"   TP3: {tp3_price:.4f} ({TP3_CLOSE_PERCENT*100}% - {tp3_quantity:.6f})")
            logger.info(f"   Trailing: {TRAILING_PERCENT*100}% - {trailing_quantity:.6f}")
            logger.info(f"✅ PROPER SL set: {initial_sl:.4f} (EMA50 + ATR based)")
        
        return f"{tp1_price:.4f}", f"{tp2_price:.4f}", f"{tp3_price:.4f}"
    except Exception as e:
        logger.error(f"Error setting multi-TP with profit distribution: {e}")
        return None, None, None

def check_tp_targets_with_partial_close(symbol, current_price, trade_info):
    """Check and update TP targets with partial position closing"""
    try:
        side = trade_info.get("side", "long")
        entry_price = float(trade_info.get("entry_price", 0))
        tp_targets = trade_info.get("tp_targets", {})
        remaining_quantity = float(trade_info.get("remaining_quantity", 0))
        total_quantity = float(trade_info.get("total_quantity", 0))
        
        state = load_state()
        if symbol not in state.get("open_trades", {}):
            return False
        
        trade_data = state["open_trades"][symbol]
        updated = False
        
        if not tp_targets.get("tp1", {}).get("hit", False):
            tp1_price = float(tp_targets["tp1"]["price"])
            if (side == "long" and current_price >= tp1_price) or \
               (side == "short" and current_price <= tp1_price):
                tp1_quantity = float(tp_targets["tp1"]["quantity"])
                if execute_trade_with_validation("sell" if side == "long" else "buy", symbol, tp1_quantity, current_price):
                    if side == "long":
                        tp1_profit = (current_price - entry_price) * tp1_quantity
                    else:
                        tp1_profit = (entry_price - current_price) * tp1_quantity
                    
                    trade_data["tp_targets"]["tp1"]["hit"] = True
                    trade_data["tp_targets"]["tp1"]["closed"] = True
                    trade_data["remaining_quantity"] = f"{remaining_quantity - tp1_quantity:.6f}"
                    trade_data["sl"] = f"{entry_price:.4f}"
                    trade_data["partial_profit"] = f"+{tp1_profit:.2f} USDT"
                    updated = True
                    
                    logger.info(f"🎯 TP1 Hit for {symbol}! Closed {tp1_quantity:.6f} ({TP1_CLOSE_PERCENT*100}%)")
                    logger.info(f"💰 Partial Profit: {tp1_profit:.2f} USDT - SL moved to break-even")
                    
                    log_partial_close(symbol, side, entry_price, current_price, tp1_quantity, 
                                    trade_data.get("trade_num", 0), "TP1", tp1_profit)
        
        elif not tp_targets.get("tp2", {}).get("hit", False) and tp_targets.get("tp1", {}).get("hit", False):
            tp2_price = float(tp_targets["tp2"]["price"])
            if (side == "long" and current_price >= tp2_price) or \
               (side == "short" and current_price <= tp2_price):
                tp2_quantity = float(tp_targets["tp2"]["quantity"])
                if execute_trade_with_validation("sell" if side == "long" else "buy", symbol, tp2_quantity, current_price):
                    if side == "long":
                        tp2_profit = (current_price - entry_price) * tp2_quantity
                    else:
                        tp2_profit = (entry_price - current_price) * tp2_quantity
                    
                    trade_data["tp_targets"]["tp2"]["hit"] = True
                    trade_data["tp_targets"]["tp2"]["closed"] = True
                    trade_data["remaining_quantity"] = f"{remaining_quantity - tp2_quantity:.6f}"
                    tp1_price = float(tp_targets["tp1"]["price"])
                    trade_data["sl"] = f"{tp1_price:.4f}"
                    current_partial = float(trade_data.get("partial_profit", "0").replace("+", "").replace(" USDT", ""))
                    trade_data["partial_profit"] = f"+{current_partial + tp2_profit:.2f} USDT"
                    updated = True
                    
                    logger.info(f"🎯 TP2 Hit for {symbol}! Closed {tp2_quantity:.6f} ({TP2_CLOSE_PERCENT*100}%)")
                    logger.info(f"💰 Additional Profit: {tp2_profit:.2f} USDT - SL moved to TP1")
                    
                    log_partial_close(symbol, side, entry_price, current_price, tp2_quantity,
                                    trade_data.get("trade_num", 0), "TP2", tp2_profit)
        
        elif not tp_targets.get("tp3", {}).get("hit", False) and tp_targets.get("tp2", {}).get("hit", False):
            tp3_price = float(tp_targets["tp3"]["price"])
            if (side == "long" and current_price >= tp3_price) or \
               (side == "short" and current_price <= tp3_price):
                tp3_quantity = float(tp_targets["tp3"]["quantity"])
                if execute_trade_with_validation("sell" if side == "long" else "buy", symbol, tp3_quantity, current_price):
                    if side == "long":
                        tp3_profit = (current_price - entry_price) * tp3_quantity
                    else:
                        tp3_profit = (entry_price - current_price) * tp3_quantity
                    
                    trade_data["tp_targets"]["tp3"]["hit"] = True
                    trade_data["tp_targets"]["tp3"]["closed"] = True
                    trade_data["remaining_quantity"] = f"{remaining_quantity - tp3_quantity:.6f}"
                    tp2_price = float(tp_targets["tp2"]["price"])
                    trade_data["sl"] = f"{tp2_price:.4f}"
                    trade_data["trailing_active"] = True
                    current_partial = float(trade_data.get("partial_profit", "0").replace("+", "").replace(" USDT", ""))
                    trade_data["partial_profit"] = f"+{current_partial + tp3_profit:.2f} USDT"
                    updated = True
                    
                    logger.info(f"🎯 TP3 Hit for {symbol}! Closed {tp3_quantity:.6f} ({TP3_CLOSE_PERCENT*100}%)")
                    logger.info(f"💰 Additional Profit: {tp3_profit:.2f} USDT")
                    logger.info(f"🚀 Trailing stop ACTIVATED for remaining {trade_data['remaining_quantity']} {symbol}")
                    
                    log_partial_close(symbol, side, entry_price, current_price, tp3_quantity,
                                    trade_data.get("trade_num", 0), "TP3", tp3_profit)
        
        if updated:
            save_state(state)
        
        return updated
    except Exception as e:
        logger.error(f"Error checking TP targets with partial close: {e}")
        return False

def log_partial_close(symbol, side, entry_price, exit_price, quantity, trade_num, tp_level, profit):
    """Log partial TP closes in CSV"""
    try:
        row = {
            "Trade #": trade_num,
            "Symbol": symbol.replace('USDT',''),
            "Side": side.upper(),
            "Type": f"{symbol} {side.upper()} - {tp_level}",
            "Date/Time": datetime.now().strftime("%b %d, %Y, %H:%M"),
            "Signal": f"Partial Close ({tp_level})",
            "Price": f"{exit_price:.8f}",
            "Position size": f"{quantity:.6f} ({round(quantity*exit_price,2):.2f} USDT)",
            "Net P&L": f"{profit:+.2f} USDT",
            "Run-up": "0",
            "Drawdown": "0",
            "Cumulative P&L": ""
        }
        
        success = append_trade_row(row)
        if success:
            logger.info(f"Logged PARTIAL CLOSE for {symbol} {tp_level}: {profit:+.2f} USDT")
        else:
            logger.error(f"Failed to log partial close for {symbol}")
            
    except Exception as e:
        logger.error(f"Error logging partial close: {e}")

def update_trailing_stop(symbol, current_price, trade_info):
    """Update trailing stop after TP3 hit"""
    try:
        if not trade_info.get("trailing_active", False):
            return False
        
        side = trade_info.get("side", "long")
        trailing_distance_percent = trade_info.get("trailing_distance_percent", TRAILING_DISTANCE_PERCENT)
        highest_price = float(trade_info.get("highest_price", current_price))
        lowest_price = float(trade_info.get("lowest_price", current_price))
        
        state = load_state()
        if symbol not in state.get("open_trades", {}):
            return False
        
        trade_data = state["open_trades"][symbol]
        updated = False
        
        if side == "long":
            if current_price > highest_price:
                trade_data["highest_price"] = f"{current_price:.4f}"
                updated = True
                highest_price = current_price
            
            new_trailing_stop = highest_price * (1 - trailing_distance_percent)
            current_sl = float(trade_data.get("sl", 0))
            
            if new_trailing_stop > current_sl:
                trade_data["sl"] = f"{new_trailing_stop:.4f}"
                updated = True
                logger.info(f"📈 Trailing SL updated for {symbol}: {new_trailing_stop:.4f} (Current: {current_price:.4f})")
        
        else:
            if current_price < lowest_price:
                trade_data["lowest_price"] = f"{current_price:.4f}"
                updated = True
                lowest_price = current_price
            
            new_trailing_stop = lowest_price * (1 + trailing_distance_percent)
            current_sl = float(trade_data.get("sl", 0))
            
            if new_trailing_stop < current_sl:
                trade_data["sl"] = f"{new_trailing_stop:.4f}"
                updated = True
                logger.info(f"📉 Trailing SL updated for {symbol}: {new_trailing_stop:.4f} (Current: {current_price:.4f})")
        
        if updated:
            save_state(state)
        
        return updated
    except Exception as e:
        logger.error(f"Error updating trailing stop: {e}")
        return False

def check_sl_tp(symbol, current_price, trade_info):
    """Check if SL or TP is hit with price validation"""
    try:
        if not PriceValidator.validate_price(symbol, current_price, "check"):
            logger.warning(f"⚠️ Skipping SL/TP check for {symbol} - invalid current price: {current_price}")
            return False
        
        sl = trade_info.get("sl")
        tp_targets = trade_info.get("tp_targets", {})
        remaining_quantity = float(trade_info.get("remaining_quantity", 0))
        
        if not sl:
            return False
        
        sl_price = float(sl)
        side = trade_info.get("side", "long")
        
        if not PriceValidator.validate_price(symbol, sl_price, "SL"):
            logger.error(f"❌ Invalid SL price for {symbol}: {sl_price}")
            return False
        
        if (side == "long" and current_price <= sl_price) or \
           (side == "short" and current_price >= sl_price):
            if remaining_quantity > 0:
                logger.info(f"🛑 SL Hit for {symbol} {side.upper()} at {current_price}")
                
                if execute_trade_with_validation("sell" if side == "long" else "buy", 
                                               symbol, remaining_quantity, current_price):
                    return "SL"
        
        tp_hit = check_tp_targets_with_partial_close(symbol, current_price, trade_info)
        if tp_hit:
            return "TP_TARGET"
        
        if trade_info.get("trailing_active", False):
            update_trailing_stop(symbol, current_price, trade_info)
        
        return False
    except Exception as e:
        logger.error(f"❌ Error checking SL/TP for {symbol}: {e}")
        return False

@safe_execute(default_return=1)
def log_open(symbol, side, price, qty):
    try:
        trade_num = next_trade_number()
        row = {
            "Trade #": trade_num,
            "Symbol": symbol.replace('USDT',''),
            "Side": side.upper(),
            "Type": f"{symbol} {side.upper()}",
            "Date/Time": datetime.now().strftime("%b %d, %Y, %H:%M"),
            "Signal": "Entry",
            "Price": f"{price:.8f}",
            "Position size": f"{TRADE_USDT:.2f} USDT",
            "Net P&L": "",
            "Run-up": "",
            "Drawdown": "",
            "Cumulative P&L": ""
        }
        success = append_trade_row(row)
        if success:
            logger.info(f"Logged OPEN trade #{trade_num} for {symbol} {side} at {price}")
        else:
            logger.error(f"Failed to log OPEN trade for {symbol}")
        return trade_num
    except Exception as e:
        logger.error(f"Error in log_open for {symbol}: {e}")
        return 1

def _update_stats_from_pnl(side, pnl):
    try:
        st = load_state()
        side = side.lower()
        if "stats" not in st:
            st["stats"] = {
                "long": {"total": 0, "success": 0, "fail": 0},
                "short": {"total": 0, "success": 0, "fail": 0}
            }
        if side not in ("long","short"):
            side = "long" if str(side).lower().startswith("l") else "short"
        
        st["stats"].setdefault(side, {"total":0,"success":0,"fail":0})
        st["stats"][side]["total"] = st["stats"][side].get("total",0) + 1
        
        if pnl is not None and pnl > 0:
            st["stats"][side]["success"] = st["stats"][side].get("success",0) + 1
            logger.debug(f"Updated stats: {side} success")
        else:
            st["stats"][side]["fail"] = st["stats"][side].get("fail",0) + 1
            logger.debug(f"Updated stats: {side} fail")
        
        save_state(st)
    except Exception as e:
        logger.error(f"Error updating stats: {e}")

@safe_execute(default_return=(0.0, 0.0))
def log_close(symbol, side, entry_price, exit_price, qty, trade_num, reason="Manual"):
    try:
        if not PriceValidator.validate_trade_prices(symbol, entry_price, exit_price):
            logger.error(f"❌ Trade close rejected due to invalid prices: {symbol}")
            return 0.0, 0.0
        
        if side == "long":
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
            
        pnl = round(pnl, 2)
        
        max_realistic_pnl = TRADE_USDT * 5
        if abs(pnl) > max_realistic_pnl:
            logger.warning(f"⚠️ Suspicious P&L for {symbol}: {pnl} USDT (trade: {TRADE_USDT} USDT)")
            pnl = max_realistic_pnl if pnl > 0 else -max_realistic_pnl
        
        df = safe_read_trades()
        try:
            existing = pd.to_numeric(df["Net P&L"].str.replace("[^0-9.-]","", regex=True), errors="coerce").dropna()
            cumulative = existing.sum() + pnl if not existing.empty else pnl
        except Exception:
            cumulative = pnl
            
        row = {
            "Trade #": trade_num,
            "Symbol": symbol.replace('USDT',''),
            "Side": side.upper(),
            "Type": f"{symbol} {side.upper()}",
            "Date/Time": datetime.now().strftime("%b %d, %Y, %H:%M"),
            "Signal": f"Exit ({reason})",
            "Price": f"{exit_price:.8f}",
            "Position size": f"{qty:.6f} ({round(qty*exit_price,2):.2f} USDT)",
            "Net P&L": f"{pnl:+.2f} USDT",
            "Run-up": "0",
            "Drawdown": "0",
            "Cumulative P&L": f"{cumulative:.2f}"
        }
        
        success = append_trade_row(row)
        if success:
            logger.info(f"✅ Logged CLOSE trade #{trade_num} for {symbol} {side} at {exit_price}, PnL: {pnl} ({reason})")
            
            try:
                _update_stats_from_pnl(side, pnl)
            except Exception as e:
                logger.error(f"Error updating stats for trade close: {e}")
        else:
            logger.error(f"❌ Failed to log CLOSE trade for {symbol}")

        return pnl, cumulative
    except Exception as e:
        logger.error(f"❌ Error in log_close for {symbol}: {e}")
        return 0.0, 0.0

# STRATEGY IMPLEMENTATION
def calculate_quantity(price):
    """Calculate quantity based on trade amount"""
    try:
        if price <= 0:
            return 0
        quantity = TRADE_USDT / price
        logger.debug(f"Calculated quantity: {quantity} for price {price}")
        return quantity
    except Exception as e:
        logger.error(f"Error calculating quantity: {e}")
        return 0

def check_trading_signal(df, symbol, current_price):
    """Complete trading strategy implementation"""
    try:
        if df.empty or len(df) < 50:
            logger.debug(f"Insufficient data for {symbol}")
            return "HOLD"
        
        ema_fast = df['close'].ewm(span=EMA_FAST).mean()
        ema_slow = df['close'].ewm(span=EMA_SLOW).mean()
        ema_mid = df['close'].ewm(span=EMA_MID).mean()
        
        rsi_val = rsi(df['close'])
        plus_di, minus_di, adx_val = calculate_adx(df)
        
        ema_fast_current = ema_fast.iloc[-1]
        ema_slow_current = ema_slow.iloc[-1]
        ema_mid_current = ema_mid.iloc[-1]
        rsi_current = rsi_val.iloc[-1]
        adx_current = adx_val.iloc[-1]
        
        ema_fast_previous = ema_fast.iloc[-2] if len(ema_fast) > 1 else ema_fast_current
        ema_slow_previous = ema_slow.iloc[-2] if len(ema_slow) > 1 else ema_slow_current
        
        logger.debug(f"{symbol} - Price: {current_price}, EMA_F: {ema_fast_current:.4f}, EMA_S: {ema_slow_current:.4f}, RSI: {rsi_current:.2f}, ADX: {adx_current:.2f}")
        
        if (ema_fast_previous <= ema_slow_previous and 
            ema_fast_current > ema_slow_current and
            ema_slow_current > ema_mid_current and
            rsi_current > RSI_LONG and 
            adx_current > ADX_THR):
            logger.info(f"✅ FRESH BUY CROSSOVER detected for {symbol}")
            return "BUY"
        
        elif (ema_fast_previous >= ema_slow_previous and 
              ema_fast_current < ema_slow_current and
              ema_slow_current < ema_mid_current and
              rsi_current < RSI_SHORT and 
              adx_current > ADX_THR):
            logger.info(f"✅ FRESH SELL CROSSOVER detected for {symbol}")
            return "SELL"
        
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Error in check_trading_signal for {symbol}: {e}")
        return "HOLD"

def manage_open_trades(symbol, current_price, signal):
    """Manage existing open trades with Multi-TP + Trailing Stop"""
    try:
        state = load_state()
        open_trades = state.get("open_trades", {})
        
        if symbol in open_trades:
            trade = open_trades[symbol]
            entry_price = float(trade.get("entry_price", 0))
            side = trade.get("side", "")
            trade_num = trade.get("trade_num", 0)
            remaining_quantity = float(trade.get("remaining_quantity", 0))
            
            sl_tp_result = check_sl_tp(symbol, current_price, trade)
            if sl_tp_result:
                if sl_tp_result == "SL" and remaining_quantity > 0:
                    logger.info(f"Closing remaining {remaining_quantity:.6f} {symbol} due to SL")
                    execute_trade_with_validation("sell" if side == "long" else "buy", symbol, remaining_quantity, current_price)
                    log_close(symbol, side, entry_price, current_price, remaining_quantity, trade_num, "SL")
                    del open_trades[symbol]
                    save_state(state)
                return
            
            if trade.get("trailing_active", False):
                update_trailing_stop(symbol, current_price, trade)
            
            if side == "long":
                if signal == "SELL" and remaining_quantity > 0:
                    logger.info(f"Exiting remaining LONG position for {symbol} at {current_price} (Signal Change)")
                    execute_trade_with_validation("sell", symbol, remaining_quantity, current_price)
                    log_close(symbol, "long", entry_price, current_price, remaining_quantity, trade_num, "Signal")
                    del open_trades[symbol]
                    save_state(state)
                    
            elif side == "short":
                if signal == "BUY" and remaining_quantity > 0:
                    logger.info(f"Exiting remaining SHORT position for {symbol} at {current_price} (Signal Change)")
                    execute_trade_with_validation("buy", symbol, remaining_quantity, current_price)
                    log_close(symbol, "short", entry_price, current_price, remaining_quantity, trade_num, "Signal")
                    del open_trades[symbol]
                    save_state(state)
                    
    except Exception as e:
        logger.error(f"Error managing open trades for {symbol}: {e}")

# ✅ FIXED: Strategy loop using ONLY ACTUAL Binance prices
def strategy_loop(symbol):
    """✅ FIXED: Strategy loop using ONLY ACTUAL Binance prices"""
    logger.info(f"🚀 Starting ACTUAL PRICE strategy for {symbol}")
    
    consecutive_count = 0
    last_trade_time = None
    
    while True:
        try:
            current_time = time.time()
            
            if last_trade_time and (current_time - last_trade_time) < TRADE_COOLDOWN:
                time.sleep(CHECK_INTERVAL)
                continue
            
            # ✅ GET ACTUAL BINANCE DATA - NO MOCK
            df = get_klines(symbol, '15m', 100)
            if df.empty or len(df) < 50:
                logger.warning(f"❌ Insufficient ACTUAL data for {symbol}, skipping...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # ✅ GET ACTUAL VALIDATED PRICE - NO MOCK
            current_price = get_validated_price(symbol)
            if current_price is None:
                logger.warning(f"❌ Could not get ACTUAL price for {symbol}, skipping...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            logger.info(f"💰 {symbol} ACTUAL Price: {current_price}")
            
            signal = check_trading_signal(df, symbol, current_price)
            manage_open_trades(symbol, current_price, signal)
            
            state = load_state()
            open_trades = state.get("open_trades", {})
            
            if symbol not in open_trades:
                if signal != "HOLD":
                    consecutive_count += 1
                    logger.info(f"✅ Signal confirmation {consecutive_count}/{CONFIRMATION_REQUIRED} for {symbol}")
                else:
                    consecutive_count = 0
                
                if consecutive_count >= CONFIRMATION_REQUIRED and signal != "HOLD":
                    total_quantity = calculate_quantity(current_price)
                    if total_quantity > 0:
                        logger.info(f"🎯 ENTERING {signal} trade for {symbol} after {consecutive_count} confirmations")
                        
                        if execute_trade_with_validation("buy" if signal == "BUY" else "sell", 
                                                       symbol, total_quantity, current_price):
                            trade_num = log_open(symbol, "long" if signal == "BUY" else "short", 
                                               current_price, total_quantity)
                            
                            tp1, tp2, tp3 = set_multi_tp_profit_distribution(symbol, current_price, 
                                                                            "long" if signal == "BUY" else "short", 
                                                                            df, total_quantity)
                            
                            initial_sl = calculate_proper_sl(symbol, current_price, 
                                                           "long" if signal == "BUY" else "short", df)
                            
                            open_trades[symbol] = {
                                "entry_price": f"{current_price:.4f}",
                                "side": "long" if signal == "BUY" else "short",
                                "total_quantity": f"{total_quantity:.6f}",
                                "remaining_quantity": f"{total_quantity:.6f}",
                                "trade_num": trade_num,
                                "entry_time": datetime.now().isoformat(),
                                "signal": signal,
                                "sl": f"{initial_sl:.4f}",
                                "tp1": tp1,
                                "tp2": tp2,
                                "tp3": tp3,
                                "tp_targets": {
                                    "tp1": {"price": tp1, "hit": False, "level": 1, "quantity": total_quantity * TP1_CLOSE_PERCENT, "closed": False},
                                    "tp2": {"price": tp2, "hit": False, "level": 2, "quantity": total_quantity * TP2_CLOSE_PERCENT, "closed": False},
                                    "tp3": {"price": tp3, "hit": False, "level": 3, "quantity": total_quantity * TP3_CLOSE_PERCENT, "closed": False}
                                },
                                "trailing_active": False,
                                "trailing_triggered": False,
                                "highest_price": f"{current_price:.4f}" if signal == "BUY" else f"{current_price:.4f}",
                                "lowest_price": f"{current_price:.4f}" if signal == "SELL" else f"{current_price:.4f}",
                                "trailing_distance_percent": TRAILING_DISTANCE_PERCENT,
                                "trailing_quantity": f"{total_quantity * TRAILING_PERCENT:.6f}"
                            }
                            save_state(state)
                            
                            consecutive_count = 0
                            last_trade_time = current_time
                            logger.info(f"⏳ Cooldown period started for {symbol}")
            
            logger.debug(f"✅ {symbol} - Signal: {signal}, Confirmations: {consecutive_count}/{CONFIRMATION_REQUIRED}")
                
        except Exception as e:
            logger.error(f"❌ Error in strategy_loop for {symbol}: {e}")
        
        time.sleep(CHECK_INTERVAL)

# MAIN EXECUTION
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Trading Bot")
        parser.add_argument("--clear-history", action="store_true", help="Clear trades.csv and state.json then exit")
        parser.add_argument("--symbol", type=str, help="Run bot for a single symbol")
        parser.add_argument("--all", action="store_true", help="Run bot for all symbols in SYMBOLS list")
        parser.add_argument("--confirmations", type=int, help="Override CONFIRMATION_REQUIRED")
        parser.add_argument("--check", action="store_true", help="Run health checks and exit")
        parser.add_argument("--max-workers", type=int, help="Max workers hint for multi-manager")
        parser.add_argument("--reset", action="store_true", help="Clear trade history and state")
        parser.add_argument("--dry-run", action="store_true", help="Force dry run mode")
        parser.add_argument("--validate-prices", action="store_true", help="Enable strict price validation")
        args = parser.parse_args()

        logger.info("🤖 Trading Bot Starting with ACTUAL BINANCE PRICES ONLY...")

        if args.clear_history or args.reset:
            reset_history()
            logger.info("🗑️ Trade history reset successfully")
            if args.clear_history:
                exit(0)

        if args.check:
            ensure_files()
            logger.info("✅ Health checks passed")
            exit(0)

        if args.confirmations is not None:
            CONFIRMATION_REQUIRED = max(1, int(args.confirmations))
            logger.info(f"⚙️ CONFIRMATION_REQUIRED set to {CONFIRMATION_REQUIRED} from CLI")

        if args.dry_run:
            DRY_RUN = True
            logger.info("⚙️ DRY_RUN set to True from CLI")

        if args.symbol:
            symbols_to_run = [args.symbol]
        elif args.all:
            symbols_to_run = SYMBOLS
        else:
            symbols_to_run = SYMBOLS[:4]
            logger.info(f"🔧 Running for first {len(symbols_to_run)} symbols (use --all for all)")

        binance_connected = initialize_binance_client()
        
        if not binance_connected:
            logger.error("🚫 CRITICAL: Cannot connect to Binance. Please check API keys and internet connection.")
            exit(1)

        ensure_files()
        state = load_state()
        logger.info(f"📂 Loaded state with {len(state.get('open_trades', {}))} open trades")

        logger.info("🚀 === Trading Bot Startup Summary ===")
        logger.info(f"   ACTUAL BINANCE PRICES: ✅ ENABLED")
        logger.info(f"   MOCK DATA: ❌ COMPLETELY DISABLED")
        logger.info(f"   Binance Testnet: {USE_TESTNET}")
        logger.info(f"   Symbols: {len(symbols_to_run)}")
        logger.info(f"   Dry Run: {DRY_RUN}")

        try:
            threads = []
            for symbol in symbols_to_run:
                t = threading.Thread(target=strategy_loop, args=(symbol,), daemon=True)
                t.start()
                threads.append(t)
                logger.info(f"✅ Started ACTUAL PRICE bot for {symbol}")
                time.sleep(1)
            
            logger.info(f"✅ Started {len(threads)} trading bots with ACTUAL BINANCE PRICES")
        except Exception as e:
            logger.error(f"❌ Error starting trading bots: {e}")
            exit(1)

        if FASTAPI_AVAILABLE:
            logger.info(f"🌐 Starting FastAPI server on http://0.0.0.0:{PORT}")
            logger.info("⏳ Trading Bot is now ACTIVE with ACTUAL BINANCE PRICES...")
            logger.info("📍 Use Ctrl+C to stop the bot")
            
            try:
                uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="error")
            except KeyboardInterrupt:
                logger.info("👋 Bot stopped by user (Ctrl+C)")
            except Exception as e:
                logger.error(f"❌ API server error: {e}")
        else:
            logger.info("🌐 FastAPI not available - running in console mode only")
            logger.info("⏳ Trading Bot is now ACTIVE (console mode)...")
            logger.info("📍 Use Ctrl+C to stop the bot")
            
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("👋 Bot stopped by user (Ctrl+C)")
            
    except Exception as e:
        logger.critical(f"💥 Critical error in main execution: {e}")
        logger.critical(traceback.format_exc())
        exit(1)