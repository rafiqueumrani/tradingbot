@echo off
setlocal enabledelayedexpansion
echo ==================================================
echo  Trading Bot Installer (Fully Automated) - Windows
echo ==================================================
REM Ensure we're running from the script directory
cd /d "%~dp0"

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists.
)

REM Activate virtual environment
call venv\Scripts\activate

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
python -m pip install -r requirements.txt

echo.
echo ✅ Installation complete.
echo Starting the bot with uvicorn (press CTRL+C to stop)...
echo.

REM Start uvicorn (serves bot:app). Use start to keep the window open.
python -m uvicorn bot:app --reload --host 127.0.0.1 --port 8000

pause
