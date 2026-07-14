@echo off
title Auto Crypto Trader - Stop Services
echo ==============================================================
echo Auto Crypto Trader - Terminating Background Services
echo ==============================================================
echo.
echo Searching for tradecore and run_continuous.py processes...
powershell -Command "Stop-Process -Id (Get-CimInstance Win32_Process -Filter 'Name = ''python.exe'' and (CommandLine like ''%%run_continuous.py%%'' or CommandLine like ''%%tradecore%%'')').ProcessId -Force -ErrorAction SilentlyContinue"
echo.
echo All background continuous trader services stopped successfully.
echo.
pause
