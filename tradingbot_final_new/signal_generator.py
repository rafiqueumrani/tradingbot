import time
import requests
import pandas as pd
from binance.client import Client
from dotenv import load_dotenv
import os

# Load .env variables
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
USE_TESTNET = os.getenv("USE_TESTNET", "True") == "True"
DRY_RUN = os.getenv("DRY_RUN", "True") == "True"
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
QUANTITY = float(os.getenv("QUANTITY", 0.001))
BOT_URL = "http://127.0.0.1:8000"

# Initialize Binance client (Testnet)
client = Client(API_KEY, API_SECRET, testnet=USE_TESTNET)

# Indicator settings
EMA_SHORT = 9
EMA_LONG = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
INTERVAL = 60  # seconds

# Store close prices
price_data = []

def fetch_price():
    """Fetch last 100 candle close prices from Binance testnet"""
    klines = client.get_klines(symbol=SYMBOL, interval=Client.KLINE_INTERVAL_1MINUTE, limit=100)
    closes = [float(k[4]) for k in klines]  # Close prices
    return closes

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]

def calculate_rsi(prices, period):
    delta = pd.Series(prices).diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def check_signal():
    if len(price_data) < EMA_LONG:
        return None
    ema_short = calculate_ema(price_data, EMA_SHORT)
    ema_long = calculate_ema(price_data, EMA_LONG)
    rsi = calculate_rsi(price_data, RSI_PERIOD)

    if ema_short > ema_long and rsi < RSI_OVERSOLD:
        return "BUY"
    elif ema_short < ema_long and rsi > RSI_OVERBOUGHT:
        return "SELL"
    return None

def send_order(action):
    if DRY_RUN:
        print(f"[DRY RUN] {action} order simulated.")
        return
    try:
        response = requests.get(f"{BOT_URL}/{action.lower()}", params={"symbol": SYMBOL, "quantity": QUANTITY})
        print(f"{action} order response: {response.json()}")
    except Exception as e:
        print(f"Error sending order: {e}")

if __name__ == "__main__":
    while True:
        price_data = fetch_price()
        signal = check_signal()
        if signal:
            print(f"Signal detected: {signal} | Latest Price: {price_data[-1]}")
            send_order(signal)
        time.sleep(INTERVAL)
