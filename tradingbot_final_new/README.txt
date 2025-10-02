Final Trading Bot Setup - Instructions

1. Extract this folder: C:\Users\umrani\tradingbot
2. Open CMD and navigate:
   cd C:\Users\umrani\tradingbot
3. Run installer:
   install.bat
4. In a new CMD, run signal generator:
   venv\Scripts\activate
   python signal_generator.py
5. Logs will show signals and orders.
6. Set DRY_RUN=False in .env to execute real trades.
