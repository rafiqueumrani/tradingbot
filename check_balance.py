import os
from binance.client import Client
from dotenv import load_dotenv

# Load .env file
load_dotenv()

api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")

print("API_KEY Loaded:", api_key)
print("API_SECRET Loaded:", "Yes" if api_secret else "No")

client = Client(api_key, api_secret)

# Spot Testnet Base URL
client.API_URL = 'https://testnet.binance.vision/api'

# Get balances
account = client.get_account()
for b in account['balances']:
    if float(b['free']) > 0:
        print(f"{b['asset']}: Free={b['free']}, Locked={b['locked']}")
