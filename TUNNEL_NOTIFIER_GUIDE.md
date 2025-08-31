# UniSync Tunnel Notifier Guide

This guide explains how to use the Tunnel Notifier to automatically connect your local UniSync app to Render web services.

## How It Works

The Tunnel Notifier creates a **reverse connection** where your local app tells Render services about your cloudflared tunnel:

```
Local App → Tunnel Notifier → Render Service IPs → Render Proxy → Your App
```

**Traditional Approach (Previous):**

- Render proxy tries to connect to a hardcoded cloudflared URL
- If the URL changes, you need to manually update Render

**New Approach (Tunnel Notifier):**

- Your local app automatically notifies Render about the current tunnel URL
- Render services dynamically update their tunnel configuration
- No manual intervention needed when tunnel URLs change

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Local App    │    │  Tunnel Notifier │    │ Render Services │
│   (app.py)     │───▶│                  │───▶│ (13.228.225.19) │
│                │    │                  │    │ (18.142.128.26) │
└─────────────────┘    └──────────────────┘    │ (54.254.162.138)│
                                                └─────────────────┘
         │                                                │
         │                                                ▼
         │                                        ┌─────────────────┐
         │                                        │ Render Proxy    │
         │                                        │ (render_proxy.py)│
         │                                        └─────────────────┘
         │                                                │
         └────────────────────────────────────────────────┘
                                    ▲
                                    │
                            ┌─────────────────┐
                            │ Cloudflared     │
                            │ Tunnel          │
                            └─────────────────┘
```

## Quick Start

### 1. **Automatic Setup (Recommended)**

**Windows:**

```bash
start_with_tunnel_notifier.bat
```

**Linux/Mac:**

```bash
chmod +x start_with_tunnel_notifier.sh
./start_with_tunnel_notifier.sh
```

This will automatically:

1. Start your Flask app
2. Start cloudflared tunnel
3. Start the tunnel notifier
4. Notify Render services about your tunnel

### 2. **Manual Setup**

If you prefer to start components manually:

```bash
# Terminal 1: Start Flask app
python app.py

# Terminal 2: Start cloudflared tunnel
python cloudflared_config.py start 5000

# Terminal 3: Start tunnel notifier
python tunnel_notifier.py
```

## Configuration

### Render Service IPs

The tunnel notifier is configured to notify these Render service IPs:

```python
RENDER_IPS = [
    "13.228.225.19",
    "18.142.128.26",
    "54.254.162.138"
]
```

### Notification Settings

```python
RENDER_SERVICE_PORT = 10000        # Port your Render service runs on
NOTIFICATION_INTERVAL = 30         # Seconds between notifications
MAX_RETRIES = 3                    # Maximum retry attempts
```

## How the Tunnel Notifier Works

### 1. **Tunnel Detection**

- Monitors if cloudflared is running
- Prompts for tunnel URL if not detected
- Stores the URL for future use

### 2. **Notification Process**

- Sends POST requests to `/tunnel_update` endpoint on each Render IP
- Includes tunnel URL, timestamp, and source information
- Tracks successful notifications

### 3. **Continuous Monitoring**

- Runs in background monitoring tunnel status
- Automatically re-notifies Render services at intervals
- Handles connection errors gracefully

## Render Proxy Updates

The `render_proxy.py` now includes:

### New Endpoint: `/tunnel_update`

```http
POST /tunnel_update
Content-Type: application/json

{
    "tunnel_url": "https://abc123.trycloudflare.com",
    "timestamp": "2024-01-15T10:30:00",
    "source": "local_unisync",
    "status": "active"
}
```

### Enhanced Status Endpoint: `/status`

```json
{
  "proxy_status": "running",
  "original_tunnel_url": "http://localhost:5000",
  "current_tunnel_url": "https://abc123.trycloudflare.com",
  "tunnel_updated_at": "2024-01-15T10:30:00",
  "render_port": 10000,
  "environment": "production"
}
```

## Usage Scenarios

### Scenario 1: Initial Setup

1. Deploy `render_proxy.py` to Render
2. Start your local system with tunnel notifier
3. Tunnel notifier automatically finds Render services
4. Render services connect to your tunnel

### Scenario 2: Tunnel URL Changes

1. Cloudflared generates new tunnel URL
2. Tunnel notifier detects the change
3. Automatically notifies all Render services
4. Render services update their configuration

### Scenario 3: Render Service Restart

1. Render service restarts
2. Tunnel notifier continues monitoring
3. Next notification cycle updates the restarted service
4. Service reconnects to your tunnel

## Testing

### Test Local Setup

```bash
python test_proxy_setup.py
```

### Test Tunnel Notifier

```bash
python tunnel_notifier.py
```

Choose option 3 to test connection to a specific Render IP.

### Test Render Proxy

```bash
# Test the new tunnel update endpoint
curl -X POST http://localhost:10000/tunnel_update \
  -H "Content-Type: application/json" \
  -d '{"tunnel_url": "https://test.trycloudflare.com"}'

# Check status
curl http://localhost:10000/status
```

## Troubleshooting

### Common Issues

#### 1. **Tunnel Notifier Can't Connect to Render**

- Check if Render service is running
- Verify the IP addresses are correct
- Ensure port 10000 is accessible

#### 2. **Render Service Not Receiving Updates**

- Check Render service logs
- Verify `/tunnel_update` endpoint exists
- Test endpoint manually

#### 3. **Tunnel URL Not Updating**

- Check tunnel notifier logs
- Verify cloudflared is running
- Test notification manually

### Debug Commands

```bash
# Check if cloudflared is running
python cloudflared_config.py status

# Test tunnel notifier manually
python tunnel_notifier.py

# Check Render proxy status
curl http://localhost:10000/status

# Test tunnel update endpoint
curl -X POST http://localhost:10000/tunnel_update \
  -H "Content-Type: application/json" \
  -d '{"tunnel_url": "YOUR_TUNNEL_URL"}'
```

## Advanced Configuration

### Custom Notification Intervals

Modify `tunnel_notifier.py`:

```python
NOTIFICATION_INTERVAL = 60  # Change to 60 seconds
```

### Add More Render IPs

```python
RENDER_IPS = [
    "13.228.225.19",
    "18.142.128.26",
    "54.254.162.138",
    "YOUR_NEW_IP_HERE"
]
```

### Custom Notification Payload

```python
payload = {
    "tunnel_url": tunnel_url,
    "timestamp": datetime.now().isoformat(),
    "source": "local_unisync",
    "status": "active",
    "custom_field": "custom_value"  # Add custom fields
}
```

## Security Considerations

### Network Security

- Tunnel notifier sends data to specific Render IPs
- Uses HTTP (not HTTPS) for internal communication
- Consider firewall rules for outbound connections

### Authentication (Optional)

Add authentication to the `/tunnel_update` endpoint:

```python
@app.route('/tunnel_update', methods=['POST'])
def tunnel_update():
    # Check authentication token
    auth_token = request.headers.get('Authorization')
    if auth_token != os.environ.get('AUTH_TOKEN'):
        return {"error": "Unauthorized"}, 401

    # ... rest of the function
```

## Monitoring

### Local Monitoring

- Tunnel notifier provides real-time status
- Check notification counts and timestamps
- Monitor connection success rates

### Render Monitoring

- Use `/status` endpoint to check configuration
- Monitor tunnel update timestamps
- Check health endpoint for overall status

## Next Steps

1. **Deploy the updated `render_proxy.py`** to Render
2. **Use the new startup scripts** for automatic setup
3. **Monitor the tunnel notifier** for successful connections
4. **Test the full flow** end-to-end

Your UniSync app will now automatically connect to Render services and keep them updated about your cloudflared tunnel! 🎉

## Support

If you encounter issues:

1. Check the tunnel notifier console for error messages
2. Verify Render service is accessible
3. Test individual components manually
4. Check the troubleshooting section above
