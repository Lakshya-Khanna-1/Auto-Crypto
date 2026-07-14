@echo off
echo ==============================================================
echo Auto Crypto Trader - Continuous 30-Day Loop Startup
echo ==============================================================

rem Check if virtual environment exists
if not exist .venv\Scripts\activate.bat (
    echo Error: .venv virtual environment not found in this folder.
    pause
    exit /b 1
)

rem Activate virtual environment
call .venv\Scripts\activate.bat

rem Run continuous supervisor script
echo Starting continuous supervisor script...
python scripts/run_continuous.py --cycle-days 30

pause
