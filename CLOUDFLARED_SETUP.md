# UniSync with Cloudflared Setup

This guide explains how to use Cloudflared instead of ngrok to expose your UniSync Flask application to the internet.

## What is Cloudflared?

Cloudflared is Cloudflare's tunneling daemon that allows you to expose your local web server to the internet through Cloudflare's global network. It's free, fast, and more reliable than ngrok.

## Benefits of Cloudflared over ngrok

- **Free**: No rate limits or connection limits
- **Faster**: Uses Cloudflare's global network
- **More reliable**: Better uptime and stability
- **Better security**: HTTPS by default
- **No authentication required**: Works out of the box

## Quick Start

### 1. Automatic Setup (Recommended)

The easiest way to get started is to use the provided startup scripts:

**Windows:**

```bash
start_unisync.bat
```

**Linux/Mac:**

```bash
chmod +x start_unisync.sh
./start_unisync.sh
```

These scripts will:

1. Start your Flask application
2. Automatically download and install cloudflared if needed
3. Start a cloudflared tunnel
4. Open your web browser

### 2. Manual Setup

If you prefer to set up manually:

#### Step 1: Start your Flask app

```bash
python app.py
```

#### Step 2: Start cloudflared tunnel

```bash
python cloudflared_config.py start 5000
```

## How to Use

### Starting the Tunnel

```bash
# Start tunnel on default port (5000)
python cloudflared_config.py start

# Start tunnel on custom port
python cloudflared_config.py start 8080
```

### Stopping the Tunnel

```bash
python cloudflared_config.py stop
```

### Checking Status

```bash
python cloudflared_config.py status
```

### Interactive Mode

```bash
python cloudflared_config.py
```

This will show an interactive menu where you can:

1. Start cloudflared tunnel
2. Stop cloudflared tunnel
3. Check status
4. Exit

## Finding Your Public URL

When you start a cloudflared tunnel, you'll see output like this:

```
✅ Cloudflared tunnel started!
🔗 Local URL: http://localhost:5000
🌐 Check the cloudflared console window for the public URL
   The URL will look like: https://random-name.trycloudflare.com
   You can also check: https://dash.cloudflare.com/
```

The public URL will appear in the cloudflared console window. It will look something like:
`https://abc123-def456-ghi789.trycloudflare.com`

## Troubleshooting

### Cloudflared not found

If you get an error that cloudflared is not found, the script will automatically download and install it for you.

### Port already in use

Make sure your Flask app is running on the specified port before starting the tunnel.

### Tunnel not working

1. Check that your Flask app is running
2. Verify the port number is correct
3. Check the cloudflared console for error messages
4. Try stopping and restarting the tunnel

### Windows-specific issues

On Windows, cloudflared runs in a separate console window. Make sure to keep that window open while using the tunnel.

## Advanced Configuration

### Custom Cloudflared Installation

If you want to install cloudflared manually:

1. Download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
2. Add to your system PATH
3. Run `cloudflared version` to verify installation

### Persistent Tunnels

For production use, you might want to set up a persistent tunnel:

1. Create a tunnel in Cloudflare dashboard
2. Configure it to point to your local server
3. Use the tunnel ID instead of the quick tunnel

## Migration from ngrok

If you were previously using ngrok:

1. Stop any running ngrok processes
2. Use the new startup scripts or cloudflared_config.py
3. Update any bookmarks or links to use the new cloudflared URL

## Security Notes

- Cloudflared tunnels are secure by default (HTTPS)
- The tunnel URL is public, so don't expose sensitive data
- Consider using Cloudflare Access for additional security
- Monitor your tunnel usage in the Cloudflare dashboard

## Support

If you encounter issues:

1. Check the cloudflared console for error messages
2. Verify your Flask app is running correctly
3. Check your internet connection
4. Visit https://developers.cloudflare.com/cloudflare-one/ for official documentation
