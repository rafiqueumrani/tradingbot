@echo off
cd /d C:\Users\Rafique\tradingbot
call venv\Scripts\activate
python bot.py
python bot.py --clear-history

pause
