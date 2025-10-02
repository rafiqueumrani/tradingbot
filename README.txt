Final Trading Bot Package (Automated Installer)
==============================================

Files in this package:
- .env                -> your API keys and settings (pre-filled with provided testnet keys)
- install.bat         -> fully automated installer: creates venv, installs deps, starts bot
- requirements.txt    -> python dependencies
- bot.py              -> FastAPI bot with /, /balance, /buy, /sell and /webhook endpoints
- README.txt          -> this file

How to use:
1. Extract all files into your existing tradingbot folder (where you run the bot).
2. Double-click install.bat to run. It will create a virtual environment (if missing), install packages, and start the bot.
3. Open http://127.0.0.1:8000 in your browser to verify the bot is running.
4. To use TradingView webhooks, run ngrok: ngrok http 8000 and put the https ngrok URL + /webhook in TradingView alert webhook URL.
   Example TradingView message (JSON):
   {
     "secret": "mysecret",
     "action": "BUY",
     "symbol": "BTCUSDT",
     "quantity": 0.001
   }

Safety notes:
- USE_TESTNET=True and DRY_RUN=True are set by default so no real orders are placed.
- When ready to go live: set USE_TESTNET=False and DRY_RUN=False and update BINANCE_API_KEY / BINANCE_API_SECRET with your live keys.
- Keep withdrawal permission OFF on API key unless necessary.

If anything still errors, paste the exact CMD error text here and I will fix it immediately.
cd C:\Users\umrani\tradingbot

# 1. Create virtual environment
python -m venv venv

# 2. Activate virtual environment
venv\Scripts\activate

# 3. Upgrade pip
python -m pip install --upgrade pip

# 4. Install required packages
pip install fastapi uvicorn python-dotenv pandas binance
tradingbot/
├─ bot_dashboard.py       <-- Paste the final dashboard + bot code here
├─ trades.csv             <-- optional, empty file is fine
├─ .env                   <-- Binance keys + settings
├─ static/                <-- optional, FastAPI will create if not exists
└─ venv/
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
USE_TESTNET=True
DRY_RUN=True
WEBHOOK_SECRET=mysecret
# Make sure virtual environment is activated
venv\Scripts\activate

# Run the server (dashboard + bot API)
uvicorn bot_dashboard:app --reload --host 127.0.0.1 --port 8000

