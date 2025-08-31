#!/usr/bin/env python3
"""
Tunnel Notifier for UniSync
This script notifies Render web services about the cloudflared tunnel URL
"""

import requests
import time
import json
import os
import subprocess
import sys
from datetime import datetime

# Render service URL (use your actual Render service URL)
RENDER_SERVICE_URL = os.environ.get('RENDER_SERVICE_URL', 'https://your-render-app.onrender.com')

# Configuration
NOTIFICATION_INTERVAL = 30  # Seconds between notifications
MAX_RETRIES = 3

class TunnelNotifier:
    def __init__(self):
        self.tunnel_url = None
        self.last_notification = None
        self.notification_count = 0
        
    def get_cloudflared_tunnel_url(self):
        """Get the current cloudflared tunnel URL"""
        try:
            # Try to get from cloudflared status
            if sys.platform.startswith('win'):
                result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq cloudflared.exe'], 
                                      capture_output=True, text=True, check=False)
                if "cloudflared.exe" not in result.stdout:
                    return None
            else:
                result = subprocess.run(['pgrep', 'cloudflared'], 
                                      capture_output=True, check=False)
                if result.returncode != 0:
                    return None
            
            # For now, we'll need to manually provide the URL
            # In a real implementation, you'd parse cloudflared logs
            if not self.tunnel_url:
                self.tunnel_url = input("Enter your cloudflared tunnel URL (e.g., https://abc123.trycloudflare.com): ").strip()
                if not self.tunnel_url:
                    return None
                    
            return self.tunnel_url
            
        except Exception as e:
            print(f"Error getting tunnel URL: {e}")
            return None
    
    def notify_render_service(self, tunnel_url):
        """Send tunnel URL to Render service"""
        try:
            url = f"{RENDER_SERVICE_URL}/tunnel_update"
            
            payload = {
                "tunnel_url": tunnel_url,
                "timestamp": datetime.now().isoformat(),
                "source": "local_unisync",
                "status": "active"
            }
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "UniSync-Tunnel-Notifier/1.0"
            }
            
            print(f"🔔 Notifying Render service at {RENDER_SERVICE_URL}...")
            
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ Successfully notified Render service")
                return True
            else:
                print(f"⚠️  Render service responded with status: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            print(f"❌ Could not connect to {RENDER_SERVICE_URL}")
            return False
        except requests.exceptions.Timeout:
            print(f"⏰ Timeout connecting to Render service")
            return False
        except Exception as e:
            print(f"❌ Error notifying Render service: {e}")
            return False
    
    def notify_all_render_services(self, tunnel_url):
        """Notify Render service about the tunnel"""
        print(f"\n🌐 Notifying Render service about tunnel: {tunnel_url}")
        print("=" * 60)
        
        successful_notifications = 0
        
        if self.notify_render_service(tunnel_url):
            successful_notifications += 1
        
        print(f"\n📊 Notification Results: {successful_notifications}/1 successful")
        
        if successful_notifications > 0:
            self.last_notification = datetime.now()
            self.notification_count += 1
            print(f"✅ Last notification: {self.last_notification}")
            print(f"📈 Total notifications sent: {self.notification_count}")
        
        return successful_notifications > 0
    
    def start_monitoring(self):
        """Start monitoring and notifying Render services"""
        print("🚀 Starting Tunnel Notifier for Render Services")
        print("=" * 60)
        print(f"Target Render Service: {RENDER_SERVICE_URL}")
        print(f"Notification interval: {NOTIFICATION_INTERVAL} seconds")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                # Get current tunnel URL
                tunnel_url = self.get_cloudflared_tunnel_url()
                
                if tunnel_url:
                    # Check if we need to notify (first time or after interval)
                    should_notify = (
                        self.last_notification is None or
                        (datetime.now() - self.last_notification).seconds >= NOTIFICATION_INTERVAL
                    )
                    
                    if should_notify:
                        print(f"\n🔄 Checking tunnel status...")
                        self.notify_all_render_services(tunnel_url)
                    else:
                        remaining = NOTIFICATION_INTERVAL - (datetime.now() - self.last_notification).seconds
                        print(f"⏳ Next notification in {remaining} seconds...")
                else:
                    print("❌ No cloudflared tunnel detected")
                    print("Please start cloudflared tunnel first")
                
                # Wait before next check
                time.sleep(10)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Tunnel Notifier stopped by user")
            print("Thank you for using UniSync Tunnel Notifier!")

def main():
    """Main function"""
    print("🔄 UniSync Tunnel Notifier for Render Services")
    print("=" * 60)
    
    notifier = TunnelNotifier()
    
    # Check if cloudflared is running
    tunnel_url = notifier.get_cloudflared_tunnel_url()
    
    if not tunnel_url:
        print("❌ No cloudflared tunnel detected")
        print("Please start your cloudflared tunnel first:")
        print("   python cloudflared_config.py start 5000")
        return
    
    print(f"✅ Cloudflared tunnel detected: {tunnel_url}")
    
    # Ask user what they want to do
    print("\nChoose an option:")
    print("1. Send one-time notification to all Render services")
    print("2. Start continuous monitoring and notifications")
    print("3. Test connection to Render service")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        print("\n📤 Sending one-time notification...")
        notifier.notify_all_render_services(tunnel_url)
        
    elif choice == "2":
        print("\n🔄 Starting continuous monitoring...")
        notifier.start_monitoring()
        
    elif choice == "3":
        print("\n🧪 Testing connection...")
        print(f"Testing connection to: {RENDER_SERVICE_URL}")
        notifier.notify_render_service(tunnel_url)
            
    else:
        print("❌ Invalid choice")

if __name__ == '__main__':
    main()
