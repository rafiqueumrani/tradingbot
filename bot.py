# bot.py - ACTUAL BINANCE DATA ONLY
"""
ACTUAL BINANCE TESTNET DATA ONLY - NO MOCK DATA
- Uses only real Binance testnet prices
- Removed ALL mock data functions
- Enhanced error handling for real data
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
import requests

# Binance client - MUST BE AVAILABLE
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except Exception as e:
    print(f"❌ Binance library not available: {e}")
    Client = None
    BINANCE_AVAILABLE = False

# FastAPI + dashboard
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except Exception as e:
    print(f"⚠️ FastAPI not available: {e}")
    FASTAPI_AVAILABLE = False

# Custom JSON encoder
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
        return super().default(obj)

if FASTAPI_AVAILABLE:
    app = FastAPI(title="Trading Bot - REAL DATA", version="3.0.0")
else:
    app = None

# Load environment
load_dotenv()

# Enhanced Logging
def setup_logging():
    logger = logging.getLogger('trading_bot')
    logger.setLevel(logging.INFO)
    
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    file_handler = RotatingFileHandler('trading_bot.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    console_handler = logging.StreamHandler()
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger

logger = setup_logging()

# Config
def _env_bool(name, default="False"):
    v = os.getenv(name, default)
    return str(v).lower() in ("1", "true", "yes")

API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
USE_TESTNET = _env_bool("USE_TESTNET", "True")
DRY_RUN = _env_bool("DRY_RUN", "True")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))
TRADE_USDT = float(os.getenv("TRADE_USDT", 50.0))
PORT = int(os.getenv("PORT", 8000))

# Strategy Config
EMA_FAST = 9
EMA_SLOW = 21
EMA_MID = 50
RSI_LEN = 14
RSI_LONG = 51
RSI_SHORT = 48
ADX_LEN = 14
ADX_THR = 20
CONFIRMATION_REQUIRED = 2

# Risk Management
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
STATE_FILE = os.path.join(BASE_DIR, "state.json")
_state_lock = threading.RLock()

# Enhanced Error Handling
def safe_execute(default_return=None, max_retries=3):
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

# Price Validation
class PriceValidator:
    SYMBOL_PRICE_RANGES = {
        "BTCUSDT": (10000.0, 180000.0), "ETHUSDT": (500.0, 10000.0), "BNBUSDT": (100.0, 10000.0),
        "SOLUSDT": (10.0, 5000.0), "AVAXUSDT": (10.0, 2000.0), "XRPUSDT": (0.1, 100.0),
        "ADAUSDT": (0.1, 50.0), "DOGEUSDT": (0.01, 20.0), "PEPEUSDT": (0.000001, 0.01),
        "LINKUSDT": (5.0, 1000.0), "XLMUSDT": (0.05, 5.0), "DOTUSDT": (2.0, 500.0),
        "OPUSDT": (0.01, 200.0), "TRXUSDT": (0.05, 10.0)
    }
    
    @classmethod
    def validate_price(cls, symbol, price, action="trade"):
        if symbol not in cls.SYMBOL_PRICE_RANGES:
            return True
        min_price, max_price = cls.SYMBOL_PRICE_RANGES[symbol]
        if price < min_price or price > max_price:
            logger.warning(f"🚨 SUSPICIOUS PRICE: {symbol} at {price} for {action}")
            return False
        return True

# ✅ ENHANCED BINANCE CLIENT - ONLY REAL DATA
client = None

def initialize_binance_client():
    """Initialize Binance client with REAL testnet connection"""
    global client
    
    if not BINANCE_AVAILABLE:
        logger.error("❌ Binance library not available - CANNOT TRADE WITHOUT IT")
        return False
    
    if not API_KEY or not API_SECRET:
        logger.error("❌ API keys missing - CANNOT TRADE WITHOUT THEM")
        return False
    
    try:
        # Test internet connection
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        
        logger.info("🔄 Initializing Binance Testnet Connection...")
        
        if USE_TESTNET:
            # Testnet configuration
            client = Client(
                API_KEY, 
                API_SECRET,
                testnet=True,
                requests_params={"timeout": 30}
            )
            logger.info("✅ Binance Testnet Client Created")
            
            # Test connection with actual API call
            try:
                server_time = client.get_server_time()
                logger.info(f"✅ Binance Testnet Connection SUCCESS - Server Time: {server_time['serverTime']}")
                
                # Get account info to verify
                account = client.get_account()
                logger.info(f"✅ Account Verified - Type: {account['accountType']}")
                logger.info(f"✅ Available Balance: {next((item['free'] for item in account['balances'] if item['asset'] == 'USDT'), '0')} USDT")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Binance Testnet Connection FAILED: {e}")
                client = None
                return False
        else:
            logger.error("❌ MAINNET not supported in this version - Use Testnet only")
            return False
            
    except Exception as e:
        logger.error(f"❌ Binance initialization failed: {e}")
        client = None
        return False

# ✅ ACTUAL BINANCE DATA FUNCTIONS - NO MOCK DATA
@safe_execute(default_return=None)
def get_validated_price(symbol, max_retries=5):
    """Get ACTUAL Binance price with retries - NO MOCK DATA"""
    if client is None:
        logger.error(f"❌ Client not initialized for {symbol}")
        return None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔍 Fetching ACTUAL price for {symbol} (attempt {attempt+1})")
            
            # Get actual price from Binance
            ticker = client.get_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])
            
            logger.info(f"✅ ACTUAL BINANCE PRICE: {symbol} = {price}")
            
            # Validate price
            if not PriceValidator.validate_price(symbol, price, "current"):
                logger.warning(f"Price validation failed for {symbol}: {price}")
                continue
                
            return price
            
        except Exception as e:
            logger.warning(f"Attempt {attempt+1}: Error getting actual price for {symbol}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
    
    logger.error(f"❌ FAILED to get ACTUAL price for {symbol} after {max_retries} attempts")
    return None

@safe_execute(default_return=pd.DataFrame())
def get_klines(symbol, interval='15m', limit=100):
    """Get ACTUAL Binance klines - NO MOCK DATA"""
    if client is None:
        logger.error(f"❌ Client not initialized for {symbol}")
        return pd.DataFrame()
    
    try:
        logger.info(f"📊 Fetching ACTUAL klines for {symbol} ({interval}, limit: {limit})")
        
        # Get actual klines from Binance
        raw_klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        
        if not raw_klines:
            logger.error(f"❌ No data received for {symbol}")
            return pd.DataFrame()
        
        data = []
        for k in raw_klines:
            try:
                data.append({
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6]
                })
            except Exception as e:
                logger.debug(f"Error parsing kline: {e}")
                continue
        
        df = pd.DataFrame(data)
        
        if df.empty:
            logger.error(f"❌ Empty dataframe for {symbol}")
            return pd.DataFrame()
        
        # Clean data
        df.ffill(inplace=True)
        df.fillna(method='bfill', inplace=True)
        
        logger.info(f"✅ Successfully fetched {len(df)} ACTUAL klines for {symbol}")
        logger.info(f"📈 Price Range: {df['low'].min():.4f} - {df['high'].max():.4f}")
        
        return df
        
    except Exception as e:
        logger.error(f"❌ Error fetching ACTUAL klines for {symbol}: {e}")
        return pd.DataFrame()

# ❌ REMOVED ALL MOCK DATA FUNCTIONS
# No generate_mock_data function exists in this version

# Enhanced Orders with Real Data
@safe_execute(default_return=False)
def place_order(side, symbol, qty):
    """Place ACTUAL order on Binance testnet"""
    if DRY_RUN:
        logger.info(f"[DRY-RUN] {side.upper()} {qty:.6f} {symbol}")
        return True
    
    if client is None:
        logger.error(f"❌ Cannot place real order - client not initialized")
        return False
    
    try:
        # Get current price for validation
        current_price = get_validated_price(symbol)
        if current_price is None:
            logger.error(f"❌ Cannot place order - cannot get current price for {symbol}")
            return False
        
        # Calculate order value for logging
        order_value = qty * current_price
        logger.info(f"💸 Placing REAL {side.upper()} order for {symbol}: {qty:.6f} ≈ {order_value:.2f} USDT")
        
        # Place actual order
        order_side = "BUY" if side.lower() in ("buy", "long") else "SELL"
        
        result = client.create_order(
            symbol=symbol,
            side=order_side,
            type="MARKET",
            quantity=round(qty, 6)
        )
        
        logger.info(f"✅ REAL ORDER EXECUTED: {order_side} {qty:.6f} {symbol}")
        logger.info(f"📋 Order ID: {result['orderId']}, Status: {result['status']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ REAL ORDER FAILED for {symbol}: {e}")
        return False

# Rest of the trading functions (same as before but with real data)
def calculate_quantity(price):
    """Calculate quantity based on trade amount"""
    if price <= 0:
        return 0
    quantity = TRADE_USDT / price
    logger.debug(f"Calculated quantity: {quantity:.6f} for price {price}")
    return quantity

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
        return pd.Series([50.0] * len(series))

def check_trading_signal(df, symbol, current_price):
    """Trading strategy with REAL data"""
    try:
        if df.empty or len(df) < 50:
            logger.debug(f"Insufficient REAL data for {symbol}")
            return "HOLD"
        
        # Calculate indicators with REAL data
        ema_fast = df['close'].ewm(span=EMA_FAST).mean()
        ema_slow = df['close'].ewm(span=EMA_SLOW).mean()
        ema_mid = df['close'].ewm(span=EMA_MID).mean()
        
        rsi_val = rsi(df['close'])
        
        # Get current values
        ema_fast_current = ema_fast.iloc[-1]
        ema_slow_current = ema_slow.iloc[-1]
        ema_mid_current = ema_mid.iloc[-1]
        rsi_current = rsi_val.iloc[-1]
        
        # Previous values for crossover detection
        ema_fast_previous = ema_fast.iloc[-2] if len(ema_fast) > 1 else ema_fast_current
        ema_slow_previous = ema_slow.iloc[-2] if len(ema_slow) > 1 else ema_slow_current
        
        logger.info(f"📊 {symbol} - Price: {current_price:.4f}, EMA_F: {ema_fast_current:.4f}, EMA_S: {ema_slow_current:.4f}, RSI: {rsi_current:.1f}")
        
        # BUY Signal: Fast EMA crosses above Slow EMA, above Mid EMA, RSI > 51
        if (ema_fast_previous <= ema_slow_previous and 
            ema_fast_current > ema_slow_current and
            ema_slow_current > ema_mid_current and
            rsi_current > RSI_LONG):
            logger.info(f"🎯 FRESH BUY SIGNAL for {symbol} with REAL DATA")
            return "BUY"
        
        # SELL Signal: Fast EMA crosses below Slow EMA, below Mid EMA, RSI < 48
        elif (ema_fast_previous >= ema_slow_previous and 
              ema_fast_current < ema_slow_current and
              ema_slow_current < ema_mid_current and
              rsi_current < RSI_SHORT):
            logger.info(f"🎯 FRESH SELL SIGNAL for {symbol} with REAL DATA")
            return "SELL"
        
        return "HOLD"
        
    except Exception as e:
        logger.error(f"Error in check_trading_signal for {symbol}: {e}")
        return "HOLD"

# Strategy loop with REAL data only
def strategy_loop(symbol):
    """Trading loop with ONLY REAL Binance data"""
    logger.info(f"🚀 Starting REAL DATA strategy for {symbol}")
    
    consecutive_count = 0
    last_trade_time = None
    
    while True:
        try:
            current_time = time.time()
            
            # Cooldown check
            if last_trade_time and (current_time - last_trade_time) < TRADE_COOLDOWN:
                time.sleep(CHECK_INTERVAL)
                continue
            
            # ✅ GET ONLY REAL BINANCE DATA
            df = get_klines(symbol, '15m', 100)
            if df.empty or len(df) < 50:
                logger.warning(f"❌ Insufficient REAL data for {symbol}, skipping...")
                time.sleep(CHECK_INTERVAL)
                continue
            
            # ✅ GET ONLY REAL VALIDATED PRICE
            current_price = get_validated_price(symbol)
            if current_price is None:
                logger.warning(f"❌ Could not get REAL price for {symbol}, skipping...")
                time.sleep(CHECK_INTERVAL)
                continue            
            
            logger.info(f"💰 {symbol} REAL Price: {current_price:.4f}")
            
            # Get trading signal
            signal = check_trading_signal(df, symbol, current_price)
            
            # Check for new entry
            state = load_state()
            open_trades = state.get("open_trades", {})
            
            if symbol not in open_trades:
                if signal != "HOLD":
                    consecutive_count += 1
                    logger.info(f"✅ Signal confirmation {consecutive_count}/{CONFIRMATION_REQUIRED} for {symbol}")
                else:
                    consecutive_count = 0
                
                if consecutive_count >= CONFIRMATION_REQUIRED and signal != "HOLD":
                    # Calculate position size with REAL price
                    total_quantity = calculate_quantity(current_price)
                    if total_quantity > 0:
                        logger.info(f"🎯 ENTERING {signal} trade for {symbol} with REAL DATA")
                        
                        # Execute trade with REAL data
                        if execute_trade_with_validation(signal.lower(), symbol, total_quantity, current_price):
                            trade_num = log_open(symbol, signal.lower(), current_price, total_quantity)
                            logger.info(f"✅ Trade #{trade_num} executed for {symbol} at {current_price:.4f}")
                            
                            # Reset and set cooldown
                            consecutive_count = 0
                            last_trade_time = current_time
                            logger.info(f"⏳ Cooldown period started for {symbol}")
            
            logger.debug(f"🔍 {symbol} - Signal: {signal}, Confirmations: {consecutive_count}/{CONFIRMATION_REQUIRED}")
                
        except Exception as e:
            logger.error(f"❌ Error in strategy_loop for {symbol}: {e}")
            traceback.print_exc()
        
        time.sleep(CHECK_INTERVAL)

# File operations (same as before)
@safe_execute(default_return=pd.DataFrame())
def safe_read_trades():
    with _state_lock:
        try:
            if os.path.exists(TRADES_FILE):
                df = pd.read_csv(TRADES_FILE, dtype=str)
                return df
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error reading trades file: {e}")
            return pd.DataFrame()

@safe_execute(default_return=False)
def append_trade_row(row: dict):
    with _state_lock:
        try:
            df = safe_read_trades()
            new_df = pd.DataFrame([row])
            df = pd.concat([df, new_df], ignore_index=True)
            df.to_csv(TRADES_FILE, index=False)
            return True
        except Exception as e:
            logger.error(f"Failed to append trade row: {e}")
            return False

@safe_execute(default_return={})
def load_state():
    with _state_lock:
        try:
            if not os.path.exists(STATE_FILE):
                return {}
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as e:
            logger.error(f"Error loading state file: {e}")
            return {}

@safe_execute(default_return=False)
def save_state(st):
    with _state_lock:
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(st, f, indent=2, cls=SafeJSONEncoder)
            return True
        except Exception as e:
            logger.error(f"Error saving state file: {e}")
            return False

def execute_trade_with_validation(side, symbol, quantity, price=None):
    """Execute trade with REAL price validation"""
    try:
        if price is None:
            price = get_validated_price(symbol)
            if price is None:
                return False
        
        logger.info(f"✅ Executing {side.upper()} trade for {symbol} at REAL price: {price:.4f}")
        
        if place_order(side, symbol, quantity):
            logger.info(f"✅ Successfully executed {side.upper()} trade for {symbol}")
            return True
        return False
            
    except Exception as e:
        logger.error(f"❌ Error executing trade for {symbol}: {e}")
        return False

@safe_execute(default_return=1)
def log_open(symbol, side, price, qty):
    try:
        df = safe_read_trades()
        trade_num = len(df) + 1 if not df.empty else 1
        
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
            logger.info(f"📝 Logged OPEN trade #{trade_num} for {symbol} {side} at {price:.4f}")
        return trade_num
    except Exception as e:
        logger.error(f"Error in log_open for {symbol}: {e}")
        return 1

# Simple Dashboard
if FASTAPI_AVAILABLE:
    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>🤖 Trading Bot - REAL DATA</title>
            <style>
                body { font-family: Arial; margin: 40px; background: #0f0f23; color: #00ff00; }
                .container { max-width: 1000px; margin: 0 auto; }
                .header { text-align: center; padding: 20px; border-bottom: 2px solid #00ff00; }
                .status { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 30px 0; }
                .card { background: #1a1a2e; padding: 20px; border-radius: 10px; border: 1px solid #333; }
                .btn { background: #00ff00; color: black; padding: 10px 20px; border: none; margin: 5px; cursor: pointer; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Trading Bot Dashboard</h1>
                    <p><b>REAL BINANCE TESTNET DATA ONLY</b> - No Mock Data</p>
                </div>
                
                <div class="status">
                    <div class="card">
                        <h3>🔧 System Status</h3>
                        <p>Binance: <span id="binance-status">Checking...</span></p>
                        <p>Mode: <b>TESTNET</b></p>
                        <p>Dry Run: <b>""" + ("YES" if DRY_RUN else "NO") + """</b></p>
                    </div>
                    
                    <div class="card">
                        <h3>📊 Trading Stats</h3>
                        <p>Total Trades: <span id="total-trades">0</span></p>
                        <p>Open Trades: <span id="open-trades">0</span></p>
                        <p>Symbols: <b>""" + str(len(SYMBOLS)) + """</b></p>
                    </div>
                    
                    <div class="card">
                        <h3>⚡ Controls</h3>
                        <button class="btn" onclick="refreshData()">🔄 Refresh</button>
                        <button class="btn" onclick="testConnection()">🔗 Test Binance</button>
                    </div>
                </div>
                
                <div class="card">
                    <h3>📈 Real-time Prices</h3>
                    <div id="prices">Loading real Binance prices...</div>
                </div>
                
                <div class="card">
                    <h3>📋 Recent Trades</h3>
                    <div id="trades-history">Loading trade history...</div>
                </div>
            </div>

            <script>
                async function refreshData() {
                    try {
                        const [stats, prices] = await Promise.all([
                            fetch('/api/stats').then(r => r.json()),
                            fetch('/api/prices').then(r => r.json())
                        ]);
                        
                        document.getElementById('binance-status').textContent = stats.binance_connected ? '✅ Connected' : '❌ Disconnected';
                        document.getElementById('total-trades').textContent = stats.total_trades;
                        document.getElementById('open-trades').textContent = stats.open_trades;
                        
                        // Update prices
                        if (prices.prices) {
                            document.getElementById('prices').innerHTML = prices.prices.map(p => 
                                `<div>${p.symbol}: <b>${p.price}</b> (${p.time})</div>`
                            ).join('');
                        }
                        
                    } catch (error) {
                        console.error('Error:', error);
                    }
                }
                
                async function testConnection() {
                    try {
                        const response = await fetch('/api/test-connection');
                        const result = await response.json();
                        alert(result.message);
                    } catch (error) {
                        alert('Connection test failed');
                    }
                }
                
                // Refresh every 30 seconds
                setInterval(refreshData, 30000);
                refreshData();
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    @app.get("/api/stats")
    async def get_stats():
        state = load_state()
        return {
            "binance_connected": client is not None,
            "total_trades": len(safe_read_trades()),
            "open_trades": len(state.get("open_trades", {})),
            "symbols_count": len(SYMBOLS),
            "dry_run": DRY_RUN
        }

    @app.get("/api/prices")
    async def get_prices():
        prices = []
        for symbol in SYMBOLS[:5]:  # First 5 symbols
            price = get_validated_price(symbol)
            if price:
                prices.append({
                    "symbol": symbol,
                    "price": f"{price:.4f}",
                    "time": datetime.now().strftime("%H:%M:%S")
                })
        return {"prices": prices}

    @app.get("/api/test-connection")
    async def test_connection():
        if client is None:
            return {"message": "❌ Binance client not initialized"}
        try:
            client.get_server_time()
            return {"message": "✅ Binance Testnet Connection Successful"}
        except Exception as e:
            return {"message": f"❌ Connection Failed: {str(e)}"}

# Main execution
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Trading Bot - REAL DATA ONLY")
        parser.add_argument("--symbol", type=str, help="Run for single symbol")
        parser.add_argument("--all", action="store_true", help="Run for all symbols")
        parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
        args = parser.parse_args()

        logger.info("🚀 STARTING TRADING BOT - REAL BINANCE DATA ONLY")
        logger.info("==============================================")

        # Initialize Binance with REAL connection
        binance_connected = initialize_binance_client()
        
        if not binance_connected:
            logger.error("💥 CRITICAL: Cannot connect to Binance Testnet")
            logger.error("💥 Please check: 1) Internet 2) API Keys 3) Testnet Access")
            exit(1)

        # Symbol selection
        symbols_to_run = SYMBOLS if args.all else [args.symbol] if args.symbol else SYMBOLS[:4]
        
        logger.info("✅ BINANCE TESTNET CONNECTED SUCCESSFULLY")
        logger.info(f"📊 Trading Symbols: {len(symbols_to_run)}")
        logger.info(f"🔧 Dry Run Mode: {DRY_RUN}")
        logger.info(f"🌐 Dashboard: http://localhost:{PORT}")
        logger.info("🎯 Bot is using ONLY REAL BINANCE DATA - NO MOCK DATA")

        # Start trading threads
        threads = []
        for symbol in symbols_to_run:
            t = threading.Thread(target=strategy_loop, args=(symbol,), daemon=True)
            t.start()
            threads.append(t)
            logger.info(f"✅ Started REAL DATA bot for {symbol}")
            time.sleep(1)

        # Start dashboard
        if FASTAPI_AVAILABLE:
            logger.info(f"🌐 Dashboard running on port {PORT}")
            uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="error")
        else:
            logger.info("⏳ Running in console mode...")
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}")
        traceback.print_exc()