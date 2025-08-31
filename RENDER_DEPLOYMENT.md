# UniSync Render + Cloudflared Deployment Guide

This guide explains how to deploy your UniSync app using a Render proxy server that connects to your local cloudflared tunnel.

## Architecture Overview

```
Internet Users → Render Server → Cloudflared Tunnel → Local UniSync App (app.py)
```

**Benefits:**

- **Professional URL**: Get a persistent `.onrender.com` URL
- **Reliability**: Render handles uptime and scaling
- **Security**: HTTPS by default on Render
- **Local Development**: Keep your app running locally with cloudflared

## Prerequisites

1. **Local Setup Complete**: Your UniSync app (app.py) should be working locally
2. **Cloudflared Working**: Cloudflared tunnel should be functional
3. **Render Account**: Sign up at [render.com](https://render.com)

## Quick Setup

### 1. Run the Setup Script

```bash
python setup_render_tunnel.py
```

This script will:

- Start your cloudflared tunnel
- Test connectivity
- Generate Render configuration
- Save settings to `render_config.txt`

### 2. Deploy to Render

#### Option A: Manual Deployment

1. **Create New Web Service** on Render
2. **Connect your GitHub repository** (or upload files manually)
3. **Configure the service:**

   - **Build Command**: `pip install -r requirements_render.txt`
   - **Start Command**: `./start_render_proxy.sh`
   - **Port**: `10000`

4. **Set Environment Variables:**
   - `CLOUDFLARED_TUNNEL_URL`: Your cloudflared tunnel URL (e.g., `https://abc123.trycloudflare.com`)

#### Option B: Using render.yaml (if you have a Git repo)

```yaml
services:
  - type: web
    name: unisync-proxy
    env: python
    plan: free
    buildCommand: pip install -r requirements_render.txt
    startCommand: ./start_render_proxy.sh
    envVars:
      - key: CLOUDFLARED_TUNNEL_URL
        value: YOUR_CLOUDFLARED_URL_HERE
      - key: PORT
        value: 10000
    healthCheckPath: /health
```

## File Structure for Render

Upload these files to your Render service:

```
render_proxy.py          # Main proxy server
requirements_render.txt   # Python dependencies
start_render_proxy.sh    # Startup script
```

## How It Works

### 1. **User Request Flow**

```
User → https://your-app.onrender.com/login
     ↓
Render Proxy → https://abc123.trycloudflare.com/login
     ↓
Cloudflared → http://localhost:5000/login
     ↓
Your Flask App (app.py)
```

### 2. **Response Flow**

```
Your Flask App → Cloudflared → Render Proxy → User
```

## Configuration

### Environment Variables

| Variable                 | Description                    | Example                            |
| ------------------------ | ------------------------------ | ---------------------------------- |
| `CLOUDFLARED_TUNNEL_URL` | Your cloudflared tunnel URL    | `https://abc123.trycloudflare.com` |
| `PORT`                   | Render port (usually auto-set) | `10000`                            |

### Health Checks

The proxy includes health check endpoints:

- **`/health`**: Render health check (returns 200 if tunnel is accessible)
- **`/status`**: Proxy status and configuration info

## Testing Your Deployment

### 1. **Test Local Tunnel**

```bash
# Start your local app
python app.py

# In another terminal, start cloudflared
python cloudflared_config.py start 5000
```

### 2. **Test Render Proxy**

```bash
# Test the health endpoint
curl https://your-app.onrender.com/health

# Test the status endpoint
curl https://your-app.onrender.com/status
```

### 3. **Test Full Flow**

Visit `https://your-app.onrender.com` in your browser. You should see your UniSync app!

## Troubleshooting

### Common Issues

#### 1. **Tunnel Not Accessible (503 Error)**

- Ensure your local Flask app is running (`python app.py`)
- Check that cloudflared tunnel is active
- Verify the `CLOUDFLARED_TUNNEL_URL` environment variable is correct

#### 2. **Render Build Fails**

- Check that all required files are uploaded
- Ensure `start_render_proxy.sh` has execute permissions
- Verify Python version compatibility

#### 3. **Proxy Timeout (504 Error)**

- Your local app might be slow to respond
- Check local app performance
- Consider increasing timeout in `render_proxy.py`

#### 4. **Health Check Fails**

- Render will mark your service as unhealthy
- Check the `/health` endpoint manually
- Verify tunnel connectivity

### Debug Commands

```bash
# Check cloudflared status
python cloudflared_config.py status

# Test tunnel locally
curl http://localhost:5000

# Check Render logs
# (View in Render dashboard)
```

## Advanced Configuration

### Custom Headers

Modify `render_proxy.py` to add custom headers:

```python
@app.route('/<path:path>')
def proxy(path):
    # Add custom headers
    headers = {
        'X-Proxy-Server': 'Render',
        'X-Tunnel-URL': CLOUDFLARED_TUNNEL_URL
    }

    # ... rest of proxy logic
```

### Load Balancing

For production use, consider:

- Multiple cloudflared tunnels
- Load balancer configuration
- Health check improvements

### Security

- **HTTPS**: Render provides this automatically
- **Rate Limiting**: Add to `render_proxy.py` if needed
- **Authentication**: Implement at proxy level if required

## Monitoring

### Render Dashboard

- View logs in real-time
- Monitor service health
- Check deployment status

### Custom Monitoring

```bash
# Check proxy status
curl https://your-app.onrender.com/status

# Monitor health
curl https://your-app.onrender.com/health
```

## Cost Considerations

- **Free Tier**: 750 hours/month (usually sufficient for development)
- **Paid Plans**: Start at $7/month for always-on service
- **Bandwidth**: Included in all plans

## Support

### Render Support

- [Render Documentation](https://render.com/docs)
- [Render Community](https://community.render.com)

### Local Issues

- Check cloudflared console for tunnel errors
- Verify Flask app is running and accessible
- Test tunnel connectivity manually

## Next Steps

1. **Deploy to Render** using the guide above
2. **Test the full flow** end-to-end
3. **Monitor performance** and adjust timeouts if needed
4. **Share your Render URL** with users
5. **Keep your local app running** for the tunnel to work

Your UniSync app will now be accessible via a professional Render URL while running locally through cloudflared! 🎉
