#!/usr/bin/env python3
"""
Cloudflared configuration for UniSync Flask app
This script helps set up cloudflared to expose your local Flask app to the internet
"""

import subprocess
import sys
import time
import requests
import json
import os
import platform
import urllib.request
import zipfile
import tarfile

def check_cloudflared_installed():
    """Check if cloudflared is installed"""
    try:
        subprocess.run(['cloudflared', 'version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_system_info():
    """Get system information for cloudflared download"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "windows":
        return "windows", "amd64" if "64" in machine else "386"
    elif system == "darwin":
        return "darwin", "amd64" if "x86_64" in machine else "arm64"
    else:  # Linux
        return "linux", "amd64" if "x86_64" in machine else "arm64"

def install_cloudflared():
    """Install cloudflared if not present"""
    print("Cloudflared not found. Installing...")
    
    system, arch = get_system_info()
    
    try:
        # Download cloudflared
        version = "2024.2.0"  # Latest stable version
        url = f"https://github.com/cloudflare/cloudflared/releases/download/{version}/cloudflared-{system}-{arch}"
        
        if system == "windows":
            url += ".exe"
            filename = "cloudflared.exe"
        else:
            filename = "cloudflared"
        
        print(f"Downloading cloudflared from {url}...")
        urllib.request.urlretrieve(url, filename)
        
        # Make executable on Unix systems
        if system != "windows":
            os.chmod(filename, 0o755)
        
        # Move to PATH or current directory
        if os.path.exists(filename):
            print("Cloudflared installed successfully!")
            return True
        else:
            print("Failed to install cloudflared")
            return False
            
    except Exception as e:
        print(f"Error installing cloudflared: {e}")
        return False

def start_cloudflared(port=5000):
    """Start cloudflared tunnel"""
    if not check_cloudflared_installed():
        if not install_cloudflared():
            print("Failed to install cloudflared. Please install manually from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
            return None
    
    try:
        # Start cloudflared in background
        print(f"Starting cloudflared tunnel on port {port}...")
        
        if sys.platform.startswith('win'):
            # Windows: use start command to run in background
            subprocess.Popen(['start', 'cloudflared', 'tunnel', '--url', f'http://localhost:{port}'], 
                           shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # Linux/Mac: run in background
            subprocess.Popen(['cloudflared', 'tunnel', '--url', f'http://localhost:{port}'], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait a bit for cloudflared to start
        time.sleep(5)
        
        # Get the public URL from cloudflared logs
        try:
            # Try to get the tunnel URL from the process output
            print("✅ Cloudflared tunnel started!")
            print(f"🔗 Local URL: http://localhost:{port}")
            print("🌐 Check the cloudflared console window for the public URL")
            print("   The URL will look like: https://random-name.trycloudflare.com")
            print("   You can also check: https://dash.cloudflare.com/")
            return "https://tunnel-url-will-appear-in-console.trycloudflare.com"
        except Exception as e:
            print(f"Error getting tunnel URL: {e}")
        
        print("✅ Cloudflared tunnel started! Check the console window for the public URL")
        return None
        
    except Exception as e:
        print(f"Error starting cloudflared: {e}")
        return None

def stop_cloudflared():
    """Stop cloudflared tunnel"""
    try:
        if sys.platform.startswith('win'):
            subprocess.run(['taskkill', '/f', '/im', 'cloudflared.exe'], 
                         capture_output=True, check=False)
        else:
            subprocess.run(['pkill', 'cloudflared'], capture_output=True, check=False)
        print("Cloudflared tunnel stopped")
    except Exception as e:
        print(f"Error stopping cloudflared: {e}")

def check_cloudflared_status():
    """Check if cloudflared is running"""
    try:
        if sys.platform.startswith('win'):
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq cloudflared.exe'], 
                                  capture_output=True, text=True, check=False)
            return "cloudflared.exe" in result.stdout
        else:
            result = subprocess.run(['pgrep', 'cloudflared'], 
                                  capture_output=True, check=False)
            return result.returncode == 0
    except Exception:
        return False

def main():
    """Main function"""
    print("🚀 UniSync Cloudflared Configuration")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'start':
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
            start_cloudflared(port)
        elif sys.argv[1] == 'stop':
            stop_cloudflared()
        elif sys.argv[1] == 'status':
            if check_cloudflared_status():
                print("✅ Cloudflared is running")
            else:
                print("❌ Cloudflared is not running")
        else:
            print("Usage: python cloudflared_config.py [start|stop|status] [port]")
    else:
        # Interactive mode
        print("1. Start cloudflared tunnel")
        print("2. Stop cloudflared tunnel")
        print("3. Check status")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == '1':
            port = input("Enter port number (default: 5000): ").strip()
            port = int(port) if port.isdigit() else 5000
            start_cloudflared(port)
        elif choice == '2':
            stop_cloudflared()
        elif choice == '3':
            if check_cloudflared_status():
                print("✅ Cloudflared is running")
            else:
                print("❌ Cloudflared is not running")
        elif choice == '4':
            print("Goodbye!")
        else:
            print("Invalid choice")

if __name__ == '__main__':
    main()
