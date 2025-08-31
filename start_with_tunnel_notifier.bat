@echo off
title UniSync with Tunnel Notifier
echo ========================================
echo    UniSync with Tunnel Notifier
echo ========================================
echo.

echo Starting Flask application...
echo.

REM Start Flask app in background
start "UniSync Flask App" python app.py

echo Waiting for Flask app to start...
timeout /t 5 /nobreak >nul

echo.
echo Starting cloudflared tunnel...
echo.

REM Start cloudflared tunnel
start "Cloudflared Tunnel" python cloudflared_config.py start 5000

echo Waiting for cloudflared tunnel to start...
timeout /t 10 /nobreak >nul

echo.
echo Starting tunnel notifier for Render services...
echo.

REM Start tunnel notifier
start "Tunnel Notifier" python tunnel_notifier.py

echo.
echo ========================================
echo    System is starting up...
echo ========================================
echo.
echo Flask App: http://localhost:5000
echo Cloudflared: Check the tunnel console window for public URL
echo Tunnel Notifier: Will automatically notify Render services
echo.
echo Press any key to open the web interface...
pause >nul

REM Open web browser
start http://localhost:5000

echo.
echo System is running! 
echo Close this window to keep the system running in background.
echo.
echo IMPORTANT: Keep all console windows open for the system to work properly.
echo.
pause
