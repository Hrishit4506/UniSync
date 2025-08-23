#!/usr/bin/env python3
"""
Ngrok configuration for UniSync Flask app
This script helps set up ngrok to expose your local Flask app to the internet
"""

import subprocess
import sys
import time
import requests
import json
import os

def check_ngrok_installed():
    """Check if ngrok is installed"""
    try:
        subprocess.run(['ngrok', 'version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_ngrok():
    """Install ngrok if not present"""
    print("Ngrok not found. Installing...")
    
    if sys.platform.startswith('win'):
        # Windows installation
        try:
            # Download ngrok
            import urllib.request
            url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
            filename = "ngrok.zip"
            
            print(f"Downloading ngrok from {url}...")
            urllib.request.urlretrieve(url, filename)
            
            # Extract and install
            import zipfile
            with zipfile.ZipFile(filename, 'r') as zip_ref:
                zip_ref.extractall(".")
            
            # Move to PATH or current directory
            if os.path.exists("ngrok.exe"):
                print("Ngrok installed successfully!")
                os.remove(filename)  # Clean up zip file
                return True
            else:
                print("Failed to install ngrok")
                return False
                
        except Exception as e:
            print(f"Error installing ngrok: {e}")
            return False
    else:
        # Linux/Mac installation
        try:
            subprocess.run(['curl', '-s', 'https://ngrok-agent.s3.amazonaws.com/ngrok.asc'], 
                         capture_output=True, check=True)
            subprocess.run(['sudo', 'tee', '/etc/apt/trusted.gpg.d/ngrok.asc'], 
                         input=subprocess.run(['curl', '-s', 'https://ngrok-agent.s3.amazonaws.com/ngrok.asc'], 
                                            capture_output=True).stdout, check=True)
            subprocess.run(['echo', '"deb https://ngrok-agent.s3.amazonaws.com buster main"', '|', 'sudo', 'tee', '/etc/apt/sources.list.d/ngrok.list'], 
                         shell=True, check=True)
            subprocess.run(['sudo', 'apt', 'update'], check=True)
            subprocess.run(['sudo', 'apt', 'install', 'ngrok'], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error installing ngrok: {e}")
            return False

def start_ngrok(port=5000):
    """Start ngrok tunnel"""
    if not check_ngrok_installed():
        if not install_ngrok():
            print("Failed to install ngrok. Please install manually from https://ngrok.com/")
            return None
    
    try:
        # Start ngrok in background
        print(f"Starting ngrok tunnel on port {port}...")
        
        if sys.platform.startswith('win'):
            # Windows: use start command to run in background
            subprocess.Popen(['start', 'ngrok', 'http', str(port)], 
                           shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # Linux/Mac: run in background
            subprocess.Popen(['ngrok', 'http', str(port)], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait a bit for ngrok to start
        time.sleep(3)
        
        # Get the public URL
        try:
            response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
            if response.status_code == 200:
                tunnels = response.json()['tunnels']
                if tunnels:
                    public_url = tunnels[0]['public_url']
                    print(f"✅ Ngrok tunnel started successfully!")
                    print(f"🌐 Public URL: {public_url}")
                    print(f"🔗 Local URL: http://localhost:{port}")
                    return public_url
        except requests.exceptions.RequestException:
            pass
        
        print("✅ Ngrok tunnel started! Check http://localhost:4040 for the public URL")
        return None
        
    except Exception as e:
        print(f"Error starting ngrok: {e}")
        return None

def stop_ngrok():
    """Stop ngrok tunnel"""
    try:
        if sys.platform.startswith('win'):
            subprocess.run(['taskkill', '/f', '/im', 'ngrok.exe'], 
                         capture_output=True, check=False)
        else:
            subprocess.run(['pkill', 'ngrok'], capture_output=True, check=False)
        print("Ngrok tunnel stopped")
    except Exception as e:
        print(f"Error stopping ngrok: {e}")

def main():
    """Main function"""
    print("🚀 UniSync Ngrok Configuration")
    print("=" * 40)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'start':
            port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
            start_ngrok(port)
        elif sys.argv[1] == 'stop':
            stop_ngrok()
        elif sys.argv[1] == 'status':
            try:
                response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
                if response.status_code == 200:
                    tunnels = response.json()['tunnels']
                    if tunnels:
                        print("✅ Ngrok is running")
                        for tunnel in tunnels:
                            print(f"   {tunnel['name']}: {tunnel['public_url']}")
                    else:
                        print("❌ No active tunnels")
                else:
                    print("❌ Ngrok is not running")
            except:
                print("❌ Ngrok is not running")
        else:
            print("Usage: python ngrok_config.py [start|stop|status] [port]")
    else:
        # Interactive mode
        print("1. Start ngrok tunnel")
        print("2. Stop ngrok tunnel")
        print("3. Check status")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ")
        
        if choice == '1':
            port = input("Enter port number (default: 5000): ").strip()
            port = int(port) if port.isdigit() else 5000
            start_ngrok(port)
        elif choice == '2':
            stop_ngrok()
        elif choice == '3':
            try:
                response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
                if response.status_code == 200:
                    tunnels = response.json()['tunnels']
                    if tunnels:
                        print("✅ Ngrok is running")
                        for tunnel in tunnels:
                            print(f"   {tunnel['name']}: {tunnel['public_url']}")
                    else:
                        print("❌ No active tunnels")
                else:
                    print("❌ Ngrok is not running")
            except:
                print("❌ Ngrok is not running")
        elif choice == '4':
            print("Goodbye!")
        else:
            print("Invalid choice")

if __name__ == '__main__':
    main()
