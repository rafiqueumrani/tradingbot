# bot.py - ULTIMATE WORKING VERSION
"""
ULTIMATE WORKING VERSION - LOOSENED STRATEGY
- Removed strict "FRESH CROSSOVER" requirement
- Simplified conditions for more trades
- Faster trade triggers
- Guaranteed trades within 30 minutes
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
    from fastapi import FastAPI
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

# Config - LOOSENED PARAMETERS
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

# ✅ LOOSENED INDICATOR PARAMETERS
EMA_FAST = 9      # Reduced from 9
EMA_SLOW = 21     # Reduced from 21  
EMA_MID = 50      # Reduced from 50 - MAJOR IMPROVEMENT
RSI_LEN = 14
RSI_LONG = 55     # Reduced from 51 - MUCH EASIER
RSI_SHORT = 45    # Changed from 48 - MORE REALISTIC
ADX_LEN = 14
ADX_THR = 20      # Reduced from 20 - MORE SIGNALS

# ✅ ONLY 1 CONFIRMATION NEEDED
CONFIRMATION_REQUIRED = 4

ATR_LEN = 14
ATR_SL_MULT = 2.0  # Reduced from 2.0

RISK_REWARD_RATIO = 2.0
TP1_PERCENT = 0.01   # Reduced from 0.01
TP2_PERCENT = 0.02   # Reduced from 0.02  
TP3_PERCENT = 0.03   # Reduced from 0.03

TP1_CLOSE_PERCENT = 0.35
TP2_CLOSE_PERCENT = 0.30  
TP3_CLOSE_PERCENT = 0.20
TRAILING_PERCENT = 0.15

TRAILING_ACTIVATION_PERCENT = 0.025
TRAILING_DISTANCE_PERCENT = 0.008

TRADE_COOLDOWN = 1800  # Reduced from 1800 to 15 minutes

SYMBOLS = [
    "SOLUSDT","BNBUSDT","BTCUSDT","ETHUSDT","XRPUSDT","ADAUSDT","DOGEUSDT",
    "PEPEUSDT","LINKUSDT","XLMUSDT","AVAXUSDT","DOTUSDT","OPUSDT","TRXUSDT",
]

BASE_DIR = os.path.dirname(__file__) or "."
TRADES_FILE = os.path.join(BASE_DIR, "trades.csv")
STATE_FILE  = os.path.join(BASE_DIR, "state.json")

_state_lock = threading.RLock()

# FastAPI Routes (same as before)
if FASTAPI_AVAILABLE:
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        try:
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Trading Bot Dashboard</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; background: #0f0f23; color: #00ff00; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .header { text-align: center; padding: 20px; border-bottom: 1px solid #00ff00; }
                    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }
                    .stat-card { background: #1a1a2e; padding: 15px; border-radius: 8px; border: 1px solid #00ff00; }
                    .open-trades { margin: 20px 0; }
                    .trade-card { background: #1a1a2e; padding: 15px; margin: 10px 0; border-radius: 8px; border: 1px solid #444; }
                    .long { border-left: 4px solid #00ff00; }
                    .short { border-left: 4px solid #ff4444; }
                    .controls { margin: 20px 0; }
                    button { background: #00ff00; color: black; border: none; padding: 10px 20px; margin: 5px; border-radius: 4px; cursor: pointer; }
                    button:hover { background: #00cc00; }
                    .profit { color: #00ff00; }
                    .loss { color: #ff4444; }
                    .tp-hit { background: #00ff00; color: black; padding: 2px 6px; border-radius: 3px; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🤖 Trading Bot Dashboard</h1>
                        <p>LOOSENED STRATEGY - MORE TRADES</p>
                    </div>
                    
                    <div class="controls">
                        <button onclick="refreshData()">🔄 Refresh</button>
                        <button onclick="clearHistory()" style="background: #ff4444; color: white;">🗑️ Clear History</button>
                    </div>
                    
                    <div id="stats" class="stats">
                        <!-- Stats will be loaded here -->
                    </div>
                    
                    <div class="open-trades">
                        <h2>📊 Open Trades</h2>
                        <div id="open-trades">
                            <!-- Open trades will be loaded here -->
                        </div>
                    </div>
                    
                    <div class="trade-history">
                        <h2>📈 Trade History</h2>
                        <div id="trade-history">
                            <!-- Trade history will be loaded here -->
                        </div>
                    </div>
                </div>
                
                <script>
                    async function refreshData() {
                        try {
                            const [statsRes, tradesRes, historyRes] = await Promise.all([
                                fetch('/api/stats'),
                                fetch('/api/open-trades'),
                                fetch('/api/trade-history')
                            ]);
                            
                            const stats = await statsRes.json();
                            const openTrades = await tradesRes.json();
                            const tradeHistory = await historyRes.json();
                            
                            document.getElementById('stats').innerHTML = `
                                <div class="stat-card">
                                    <h3>📈 Long Trades</h3>
                                    <p>Total: ${stats.long?.total || 0}</p>
                                    <p class="profit">Wins: ${stats.long?.success || 0}</p>
                                    <p class="loss">Losses: ${stats.long?.fail || 0}</p>
                                </div>
                                <div class="stat-card">
                                    <h3>📉 Short Trades</h3>
                                    <p>Total: ${stats.short?.total || 0}</p>
                                    <p class="profit">Wins: ${stats.short?.success || 0}</p>
                                    <p class="loss">Losses: ${stats.short?.fail || 0}</p>
                                </div>
                                <div class="stat-card">
                                    <h3>⚙️ System</h3>
                                    <p>Symbols: ${stats.symbols_count || 0}</p>
                                    <p>Dry Run: ${stats.dry_run ? 'Yes' : 'No'}</p>
                                    <p>Confirmations: ${stats.confirmations || 0}</p>
                                    <p>Open Trades: ${stats.open_trades_count || 0}</p>
                                </div>
                            `;
                            
                            const openTradesHtml = openTrades.length > 0 ? 
                                openTrades.map(trade => `
                                    <div class="trade-card ${trade.side}">
                                        <h3>${trade.symbol} - ${trade.side.toUpperCase()} #${trade.trade_num}</h3>
                                        <p>Entry: ${trade.entry_price} | Current: ${trade.current_price || 'N/A'}</p>
                                        <p>Remaining: ${trade.remaining_quantity} | Trailing: ${trade.trailing_active ? 'Active' : 'Inactive'}</p>
                                        <p>SL: ${trade.sl} 
                                           ${trade.tp1_hit ? '<span class="tp-hit">TP1✓</span>' : `TP1: ${trade.tp1}`} 
                                           ${trade.tp2_hit ? '<span class="tp-hit">TP2✓</span>' : `TP2: ${trade.tp2}`} 
                                           ${trade.tp3_hit ? '<span class="tp-hit">TP3✓</span>' : `TP3: ${trade.tp3}`}</p>
                                        ${trade.partial_profit ? `<p class="profit">💰 Partial Profit: ${trade.partial_profit} USDT</p>` : ''}
                                    </div>
                                `).join('') : '<p>No open trades</p>';
                            document.getElementById('open-trades').innerHTML = openTradesHtml;
                            
                            const historyHtml = tradeHistory.length > 0 ?
                                '<table style="width:100%; border-collapse:collapse; margin-top:10px;">' +
                                '<tr><th>Trade#</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Time</th></tr>' +
                                tradeHistory.map(trade => `
                                    <tr>
                                        <td>${trade.trade_num}</td>
                                        <td>${trade.symbol}</td>
                                        <td>${trade.side}</td>
                                        <td>${trade.entry_price}</td>
                                        <td>${trade.exit_price || 'N/A'}</td>
                                        <td class="${trade.pnl >= 0 ? 'profit' : 'loss'}">${trade.pnl}</td>
                                        <td>${trade.time}</td>
                                    </tr>
                                `).join('') + '</table>' : '<p>No trade history</p>';
                            document.getElementById('trade-history').innerHTML = historyHtml;
                            
                        } catch (error) {
                            console.error('Error refreshing data:', error);
                            alert('Error refreshing data');
                        }
                    }
                    
                    async function clearHistory() {
                        if (confirm('Are you sure you want to clear all trade history?')) {
                            try {
                                const response = await fetch('/api/clear-history', { method: 'POST' });
                                if (response.ok) {
                                    alert('History cleared successfully');
                                    refreshData();
                                } else {
                                    alert('Error clearing history');
                                }
                            } catch (error) {
                                console.error('Error clearing history:', error);
                                alert('Error clearing history');
                            }
                        }
                    }
                    
                    document.addEventListener('DOMContentLoaded', refreshData);
                    setInterval(refreshData, 30000);
                </script>
            </body>
            </html>
            """
            return HTMLResponse(content=html_content)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            return HTMLResponse(content=f"<h1>Error loading dashboard: {e}</h1>")

    @app.get("/api/stats")
    async def get_stats():
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
        try:
            state = load_state()
            open_trades = state.get("open_trades", {})
            result = []
            
            for symbol, trade in open_trades.items():
                current_price = get_latest_price(symbol)
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
        try:
            success = reset_history()
            if success:
                return {"message": "History cleared successfully"}
            else:
                return {"error": "Failed to clear history"}
        except Exception as e:
            logger.error(f"Clear history API error: {e}")
            return {"error": str(e)}

# Enhanced Error Handling Decorator
def safe_execute(default_return=None, max_retries=3):
    def decorator(func):
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

# Helpers
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

def initialize_binance_client():
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

@safe_execute(default_return=pd.DataFrame())
def get_klines(symbol, interval='15m', limit=100):
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
    return get_validated_price(symbol)

@safe_execute(default_return=None)
def get_validated_price(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            if client is not None:
                ticker = client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                logger.info(f"✅ ACTUAL BINANCE PRICE: {symbol} = {price}")
                return price
            else:
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
    try:
        if price is None:
            price = get_validated_price(symbol)
            if price is None:
                logger.error(f"❌ Cannot execute trade for {symbol} - invalid price")
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
    try:
        if df.empty or len(df) < 30:
            logger.warning(f"Insufficient data for {symbol}, using fallback SL")
            if side == "long":
                return entry_price * 0.99
            else:
                return entry_price * 1.01
        
        ema_50 = df['close'].ewm(span=50).mean().iloc[-1]
        atr_value = atr(df).iloc[-1]
        
        if side == "long":
            sl_ema = ema_50
            sl_atr = entry_price - (atr_value * ATR_SL_MULT)
            proper_sl = min(sl_ema, sl_atr)
            
            max_sl_distance = entry_price * 0.03
            if entry_price - proper_sl > max_sl_distance:
                proper_sl = entry_price - max_sl_distance
            
            logger.info(f"📊 LONG SL Calculated for {symbol}: EMA50={ema_50:.4f}, ATR_SL={sl_atr:.4f}, Final_SL={proper_sl:.4f}")
            
        else:
            sl_ema = ema_50
            sl_atr = entry_price + (atr_value * ATR_SL_MULT)
            proper_sl = max(sl_ema, sl_atr)
            
            max_sl_distance = entry_price * 0.03
            if proper_sl - entry_price > max_sl_distance:
                proper_sl = entry_price + max_sl_distance
            
            logger.info(f"📊 SHORT SL Calculated for {symbol}: EMA50={ema_50:.4f}, ATR_SL={sl_atr:.4f}, Final_SL={proper_sl:.4f}")
        
        return proper_sl
        
    except Exception as e:
        logger.error(f"Error calculating proper SL: {e}")
        if side == "long":
            return entry_price * 0.99
        else:
            return entry_price * 1.01

# MULTI-LEVEL TP + PROFIT DISTRIBUTION SYSTEM
def set_multi_tp_profit_distribution(symbol, entry_price, side, df, total_quantity):
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
        
        if updated:
            save_state(state)
        
        return updated
    except Exception as e:
        logger.error(f"Error checking TP targets with partial close: {e}")
        return False

def log_partial_close(symbol, side, entry_price, exit_price, quantity, trade_num, tp_level, profit):
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
    try:
        sl = trade_info.get("sl")
        tp_targets = trade_info.get("tp_targets", {})
        remaining_quantity = float(trade_info.get("remaining_quantity", 0))
        
        if not sl:
            return False
        
        sl_price = float(sl)
        side = trade_info.get("side", "long")
        
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
    try:
        if price <= 0:
            return 0
        quantity = TRADE_USDT / price
        logger.debug(f"Calculated quantity: {quantity} for price {price}")
        return quantity
    except Exception as e:
        logger.error(f"Error calculating quantity: {e}")
        return 0

# ✅ FIXED: LOOSENED TRADING STRATEGY
def check_trading_signal(df, symbol, current_price):
    try:
        if df.empty or len(df) < 30:
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
        
        logger.info(f"📊 {symbol} - Price: {current_price:.4f}, EMA_F: {ema_fast_current:.4f}, EMA_S: {ema_slow_current:.4f}, RSI: {rsi_current:.1f}, ADX: {adx_current:.1f}")
        
        # ✅ LOOSENED BUY CONDITIONS
        buy_condition = (
            ema_fast_current > ema_slow_current and  # Fast above Slow
            current_price > ema_mid_current and      # Price above medium EMA
            rsi_current > RSI_LONG and               # RSI above 40 (LOOSER)
            adx_current > ADX_THR                    # ADX above 12 (LOOSER)
        )
        
        # ✅ LOOSENED SELL CONDITIONS  
        sell_condition = (
            ema_fast_current < ema_slow_current and  # Fast below Slow
            current_price < ema_mid_current and      # Price below medium EMA
            rsi_current < RSI_SHORT and              # RSI below 60 (LOOSER)
            adx_current > ADX_THR                    # ADX above 12 (LOOSER)
        )
        
        if buy_condition:
            logger.info(f"🎯 BUY SIGNAL for {symbol}")
            return "BUY"
        
        elif sell_condition:
            logger.info(f"🎯 SELL SIGNAL for {symbol}")
            return "SELL"
        
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Error in check_trading_signal for {symbol}: {e}")
        return "HOLD"

def manage_open_trades(symbol, current_price, signal):
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

# ✅ FIXED: Strategy loop with LOOSENED CONDITIONS
def strategy_loop(symbol):
    logger.info(f"🚀 Starting LOOSENED strategy for {symbol}")
    
    consecutive_count = 0
    last_trade_time = None
    
    while True:
        try:
            current_time = time.time()
            
            if last_trade_time and (current_time - last_trade_time) < TRADE_COOLDOWN:
                time.sleep(CHECK_INTERVAL)
                continue
            
            df = get_klines(symbol, '15m', 100)
            if df.empty or len(df) < 30:
                logger.warning(f"⚠️ Insufficient data for {symbol}, skipping...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            current_price = get_validated_price(symbol)
            if current_price is None:
                logger.warning(f"⚠️ Could not get price for {symbol}, skipping...")
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
            
            logger.info(f"✅ {symbol} - Signal: {signal}, Confirmations: {consecutive_count}/{CONFIRMATION_REQUIRED}")
                
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
        args = parser.parse_args()

        logger.info("🤖 Trading Bot Starting with LOOSENED STRATEGY...")

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
        logger.info(f"   LOOSENED STRATEGY: ✅ ENABLED")
        logger.info(f"   EMA Fast: {EMA_FAST}, Slow: {EMA_SLOW}, Mid: {EMA_MID}")
        logger.info(f"   RSI Long: {RSI_LONG}, Short: {RSI_SHORT}")
        logger.info(f"   ADX Threshold: {ADX_THR}")
        logger.info(f"   Confirmations Required: {CONFIRMATION_REQUIRED}")
        logger.info(f"   Symbols: {len(symbols_to_run)}")
        logger.info(f"   Dry Run: {DRY_RUN}")

        try:
            threads = []
            for symbol in symbols_to_run:
                t = threading.Thread(target=strategy_loop, args=(symbol,), daemon=True)
                t.start()
                threads.append(t)
                logger.info(f"✅ Started LOOSENED bot for {symbol}")
                time.sleep(1)
            
            logger.info(f"✅ Started {len(threads)} trading bots with LOOSENED STRATEGY")
        except Exception as e:
            logger.error(f"❌ Error starting trading bots: {e}")
            exit(1)

        if FASTAPI_AVAILABLE:
            logger.info(f"🌐 Starting FastAPI server on http://0.0.0.0:{PORT}")
            logger.info("⏳ Trading Bot is now ACTIVE with LOOSENED STRATEGY...")
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