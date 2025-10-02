# create_fake_trades.py
import pandas as pd
import datetime

# Fake trades data with profit column
data = [
    {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
     "symbol": "BTCUSDT", "side": "BUY", "price": 45000, "quantity": 0.01, "profit": 0},
    {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
     "symbol": "BTCUSDT", "side": "SELL", "price": 46000, "quantity": 0.01, "profit": 10}
]

df = pd.DataFrame(data)
df.to_csv("trades.csv", index=False)
print("✅ trades.csv created with profit column")
