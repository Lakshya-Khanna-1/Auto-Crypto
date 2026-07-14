@echo off
title Auto Crypto Trader Background Starter
echo ==============================================================
echo Auto Crypto Trader - Starting in Background Mode
echo ==============================================================
echo.
echo Launching the trading platform and 30-day continuous supervisor
echo in hidden background mode (no command window will remain open).
echo.
wscript //nologo start_invisible.vbs
echo.
echo Launch successful! The platform is now running in the background.
echo You can safely CLOSE this window.
echo The dashboard remains accessible at: http://localhost:9090
echo To stop the platform at any time, run: stop_platform.bat
echo.
pause
