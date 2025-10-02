import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

print("🔍 Checking .env values...\n")

print("BINANCE_API_KEY:", os.getenv("BINANCE_API_KEY"))
print("BINANCE_API_SECRET:", os.getenv("BINANCE_API_SECRET"))
print("USE_TESTNET:", os.getenv("USE_TESTNET"))
print("DRY_RUN:", os.getenv("DRY_RUN"))
print("WEBHOOK_SECRET:", os.getenv("WEBHOOK_SECRET"))
print("GMAIL_USER:", os.getenv("GMAIL_USER"))
print("GMAIL_APP_PASSWORD:", os.getenv("GMAIL_APP_PASSWORD"))
print("TRADE_QTY:", os.getenv("TRADE_QTY"))
print("CHECK_INTERVAL:", os.getenv("CHECK_INTERVAL"))
