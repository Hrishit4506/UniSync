#!/usr/bin/env python3
"""
Render Proxy Server for UniSync
This server runs on Render and forwards requests to your local cloudflared tunnel
"""

import os
import requests
from flask import Flask, request, Response, redirect, url_for
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

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def proxy(path):
    """Proxy all requests to the cloudflared tunnel"""
    try:
        # Construct the full URL for the cloudflared tunnel
        target_url = f"{current_tunnel_url.rstrip('/')}/{path}"
        
        # Get query parameters
        query_string = request.query_string.decode('utf-8')
        if query_string:
            target_url += f"?{query_string}"
        
        logger.info(f"Proxying request: {request.method} {request.path} -> {target_url}")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Data length: {len(request.get_data()) if request.get_data() else 0}")
        
        # Forward the request to the cloudflared tunnel
        # Prepare headers (remove problematic ones)
        headers = dict(request.headers)
        headers_to_remove = ['Host', 'Content-Length', 'Transfer-Encoding']
        for header in headers_to_remove:
            if header in headers:
                del headers[header]
        
        # Forward the request with proper data handling
        if request.method == 'GET':
            response = requests.get(target_url, headers=headers, timeout=30)
        elif request.method == 'POST':
            # Handle different content types properly
            if request.content_type and 'application/json' in request.content_type:
                # JSON data
                response = requests.post(target_url, json=request.get_json(), headers=headers, timeout=30)
            elif request.content_type and 'multipart/form-data' in request.content_type:
                # Form data with files
                response = requests.post(target_url, data=request.form, files=request.files, headers=headers, timeout=30)
            else:
                # Regular form data or raw data
                response = requests.post(target_url, data=request.get_data(), headers=headers, timeout=30)
        elif request.method == 'PUT':
            response = requests.put(target_url, data=request.get_data(), headers=headers, timeout=30)
        elif request.method == 'DELETE':
            response = requests.delete(target_url, headers=headers, timeout=30)
        else:
            # For other methods, try to forward with data
            response = requests.request(
                method=request.method,
                url=target_url,
                data=request.get_data(),
                headers=headers,
                timeout=30
            )
        
        # Create response with the same status code and headers
        proxy_response = Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
        
        # Remove problematic headers that might cause issues
        if 'Transfer-Encoding' in proxy_response.headers:
            del proxy_response.headers['Transfer-Encoding']
        if 'Content-Encoding' in proxy_response.headers:
            del proxy_response.headers['Content-Encoding']
            
        return proxy_response
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error to cloudflared tunnel: {CLOUDFLARED_TUNNEL_URL}")
        return Response(
            f"Cloudflared tunnel is not accessible at {current_tunnel_url}. Please ensure your local app is running and cloudflared tunnel is active.",
            status=503,
            content_type='text/plain'
        )
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error to cloudflared tunnel: {CLOUDFLARED_TUNNEL_URL}")
        return Response(
            f"Request timeout. The cloudflared tunnel at {current_tunnel_url} is taking too long to respond.",
            status=504,
            content_type='text/plain'
        )
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}")
        return Response(
            f"Proxy error: {str(e)}",
            status=500,
            content_type='text/plain'
        )

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Try to connect to the cloudflared tunnel
        response = requests.get(CLOUDFLARED_TUNNEL_URL, timeout=5)
        if response.status_code == 200:
            return {"status": "healthy", "tunnel": "connected"}, 200
        else:
            return {"status": "unhealthy", "tunnel": "responding_with_error"}, 503
    except:
        return {"status": "unhealthy", "tunnel": "not_accessible"}, 503

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
    """Status endpoint to check the proxy configuration"""
    return {
        "proxy_status": "running",
        "original_tunnel_url": CLOUDFLARED_TUNNEL_URL,
        "current_tunnel_url": current_tunnel_url,
        "tunnel_updated_at": tunnel_update_time.isoformat() if tunnel_update_time else None,
        "render_port": RENDER_PORT,
        "environment": os.environ.get('FLASK_ENV', 'production')
    }

if __name__ == '__main__':
    logger.info(f"Starting Render Proxy Server on port {RENDER_PORT}")
    logger.info(f"Proxying to cloudflared tunnel: {CLOUDFLARED_TUNNEL_URL}")
    app.run(host='0.0.0.0', port=RENDER_PORT, debug=False)
