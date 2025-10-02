import requests
import time

BOT_URL = "http://127.0.0.1:8000"  # Bot API
SYMBOL = "BTCUSDT"
QUANTITY = 0.001

# List of simulated actions
actions = ["buy", "sell", "buy", "sell"]

for action in actions:
    try:
        print(f"Sending {action.upper()} order...")
        response = requests.get(f"{BOT_URL}/{action}", params={"symbol": SYMBOL, "quantity": QUANTITY})
        print(response.json())
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(2)  # 2-second gap between orders

print("Test sequence complete! Check trades.csv and dashboard.")
