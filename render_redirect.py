#!/usr/bin/env python3
"""
Render Redirect Server for UniSync
This server runs on Render and redirects users directly to your cloudflared tunnel
"""

import os
import requests
from flask import Flask, request, redirect, jsonify
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
CLOUDFLARED_TUNNEL_URL = os.environ.get('CLOUDFLARED_TUNNEL_URL', 'http://localhost:5000')
RENDER_PORT = int(os.environ.get('PORT', 10000))

# Store for dynamic tunnel updates
current_tunnel_url = CLOUDFLARED_TUNNEL_URL
tunnel_update_time = None

@app.route('/')
def home():
    """Redirect to the cloudflared tunnel"""
    logger.info(f"Redirecting user to: {current_tunnel_url}")
    return redirect(current_tunnel_url, code=302)

@app.route('/<path:path>')
def redirect_all(path):
    """Redirect all other paths to the cloudflared tunnel"""
    target_url = f"{current_tunnel_url.rstrip('/')}/{path}"
    
    # Preserve query parameters
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
    
    logger.info(f"Redirecting {request.method} {request.path} to: {target_url}")
    return redirect(target_url, code=302)

@app.route('/tunnel_update', methods=['POST'])
def tunnel_update():
    """Receive tunnel URL updates from local app"""
    global current_tunnel_url, tunnel_update_time
    
    try:
        data = request.get_json()
        
        if not data or 'tunnel_url' not in data:
            return {"error": "Missing tunnel_url in request"}, 400
        
        new_tunnel_url = data['tunnel_url']
        source = data.get('source', 'unknown')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Update the tunnel URL
        old_url = current_tunnel_url
        current_tunnel_url = new_tunnel_url
        tunnel_update_time = datetime.now()
        
        logger.info(f"Tunnel URL updated from {old_url} to {new_tunnel_url} by {source}")
        
        return {
            "status": "success",
            "message": "Tunnel URL updated successfully",
            "old_url": old_url,
            "new_url": new_tunnel_url,
            "updated_at": tunnel_update_time.isoformat(),
            "source": source
        }, 200
        
    except Exception as e:
        logger.error(f"Error updating tunnel URL: {e}")
        return {"error": f"Failed to update tunnel URL: {str(e)}"}, 500

@app.route('/status')
def status():
    """Status endpoint to check the redirect configuration"""
    return {
        "redirect_status": "running",
        "original_tunnel_url": CLOUDFLARED_TUNNEL_URL,
        "current_tunnel_url": current_tunnel_url,
        "tunnel_updated_at": tunnel_update_time.isoformat() if tunnel_update_time else None,
        "render_port": RENDER_PORT,
        "environment": os.environ.get('FLASK_ENV', 'production'),
        "mode": "redirect"
    }

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Try to connect to the cloudflared tunnel
        response = requests.get(current_tunnel_url, timeout=5)
        if response.status_code == 200:
            return {"status": "healthy", "tunnel": "connected"}, 200
        else:
            return {"status": "unhealthy", "tunnel": "responding_with_error"}, 503
    except:
        return {"status": "unhealthy", "tunnel": "not_accessible"}, 503

if __name__ == '__main__':
    logger.info(f"Starting Render Redirect Server on port {RENDER_PORT}")
    logger.info(f"Redirecting to cloudflared tunnel: {CLOUDFLARED_TUNNEL_URL}")
    app.run(host='0.0.0.0', port=RENDER_PORT, debug=False)
