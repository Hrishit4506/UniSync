@echo off
title UniSync Smart Campus System
echo ========================================
echo    UniSync Smart Campus System
echo ========================================
echo.

echo Starting Flask application...
echo.

REM Start Flask app in background
start "UniSync Flask App" python app.py

echo Waiting for Flask app to start...
timeout /t 5 /nobreak >nul

echo.
echo Starting ngrok tunnel...
echo.

REM Start ngrok tunnel
start "Ngrok Tunnel" python ngrok_config.py start 5000

echo.
echo ========================================
echo    System is starting up...
echo ========================================
echo.
echo Flask App: http://localhost:5000
echo Ngrok Status: http://localhost:4040
echo.
echo Press any key to open the web interface...
pause >nul

REM Open web browser
start http://localhost:5000

echo.
echo System is running! 
echo Close this window to keep the system running in background.
echo.
pause
