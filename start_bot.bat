@echo off
cd /d C:\Users\umrani\tradingbot

:: Virtual env activate karo
call venv\Scripts\activate

echo Starting Trading Bot...
start cmd /k "python -m uvicorn bot:app --reload --host 127.0.0.1 --port 8000"

echo Starting Dashboard...
start cmd /k "python -m uvicorn bot_dashboard:app --reload --host 127.0.0.1 --port 8001"

exit
