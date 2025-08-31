#!/bin/bash

echo "========================================"
echo "   UniSync with Tunnel Notifier"
echo "========================================"
echo

echo "Starting Flask application..."
echo

# Start Flask app in background
python3 app.py &
FLASK_PID=$!

echo "Waiting for Flask app to start..."
sleep 5

echo
echo "Starting cloudflared tunnel..."
echo

# Start cloudflared tunnel
python3 cloudflared_config.py start 5000 &
CLOUDFLARED_PID=$!

echo "Waiting for cloudflared tunnel to start..."
sleep 10

echo
echo "Starting tunnel notifier for Render services..."
echo

# Start tunnel notifier
python3 tunnel_notifier.py &
NOTIFIER_PID=$!

echo
echo "========================================"
echo "    System is starting up..."
echo "========================================"
echo
echo "Flask App: http://localhost:5000"
echo "Cloudflared: Check the tunnel console for public URL"
echo "Tunnel Notifier: Will automatically notify Render services"
echo

# Function to cleanup on exit
cleanup() {
    echo
    echo "Shutting down UniSync system..."
    kill $FLASK_PID 2>/dev/null
    kill $CLOUDFLARED_PID 2>/dev/null
    kill $NOTIFIER_PID 2>/dev/null
    echo "System stopped."
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

echo "System is running! Press Ctrl+C to stop."
echo "IMPORTANT: Keep this terminal open for the system to work properly."
echo

# Wait for user to stop
wait
