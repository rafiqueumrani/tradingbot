import time
import requests
import pandas as pd
import numpy as np

# Bot API URL
BOT_URL = "http://127.0.0.1:8000"  # local bot

# Symbol & interval
SYMBOL = "BTCUSDT"
INTERVAL = 60  # seconds per candle, example 1 min

# Indicator settings
EMA_SHORT = 9
EMA_LONG = 21
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Dummy price data (replace with real Binance fetch or CSV)
price_data = []

def fetch_price():
    # Replace with real Binance API or CSV fetch
    # For test, we simulate random price
    import random
    price = 50000 + random.uniform(-500, 500)
    price_data.append(price)
    if len(price_data) > EMA_LONG:
        price_data.pop(0)
    return price

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

    # Buy Signal
    if ema_short > ema_long and rsi < RSI_OVERSOLD:
        return "BUY"
    # Sell Signal
    elif ema_short < ema_long and rsi > RSI_OVERBOUGHT:
        return "SELL"
    return None

def send_order(action, quantity=0.001):
    try:
        response = requests.get(f"{BOT_URL}/{action.lower()}", params={"symbol": SYMBOL, "quantity": quantity})
        print(f"{action} order response: {response.json()}")
    except Exception as e:
        print(f"Error sending order: {e}")

if __name__ == "__main__":
    while True:
        price = fetch_price()
        signal = check_signal()
        if signal:
            print(f"Signal detected: {signal} at price {price}")
            send_order(signal)
        time.sleep(INTERVAL)
