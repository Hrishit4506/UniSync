#!/bin/bash

echo "========================================"
echo "   UniSync Smart Campus System"
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
echo "Starting ngrok tunnel..."
echo

# Start ngrok tunnel
python3 ngrok_config.py start 5000 &
NGROK_PID=$!

echo
echo "========================================"
echo "    System is starting up..."
echo "========================================"
echo
echo "Flask App: http://localhost:5000"
echo "Ngrok Status: http://localhost:4040"
echo

# Function to cleanup on exit
cleanup() {
    echo
    echo "Shutting down UniSync system..."
    kill $FLASK_PID 2>/dev/null
    kill $NGROK_PID 2>/dev/null
    echo "System stopped."
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

echo "System is running! Press Ctrl+C to stop."
echo

# Wait for user to stop
wait
