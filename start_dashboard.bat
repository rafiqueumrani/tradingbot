@echo off
cd /d C:\Users\Rafique\tradingbot
call venv\Scripts\activate
python bot_dashboard.py
start http://127.0.0.1:8001
pause
