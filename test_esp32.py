#!/usr/bin/env python3
"""
Test ESP32-CAM Connection
Simple script to test if your ESP32-CAM is accessible
"""

import requests
import time

def test_esp32_connection(ip, port=81):
    """Test connection to ESP32-CAM"""
    print(f"🔍 Testing connection to {ip}:{port}")
    
    # Test basic connectivity
    try:
        print(f"   Testing basic connection...")
        response = requests.get(f"http://{ip}:{port}/", timeout=5)
        print(f"   ✅ Basic connection successful (Status: {response.status_code})")
    except requests.exceptions.ConnectTimeout:
        print(f"   ❌ Connection timeout - ESP32-CAM not responding")
        return False
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Connection refused - ESP32-CAM not accessible")
        return False
    except Exception as e:
        print(f"   ❌ Connection error: {e}")
        return False
    
    # Test stream endpoint
    try:
        print(f"   Testing stream endpoint...")
        response = requests.get(f"http://{ip}:{port}/stream", timeout=5)
        print(f"   ✅ Stream endpoint accessible (Status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ Stream endpoint error: {e}")
        return False
    
    # Test capture endpoint
    try:
        print(f"   Testing capture endpoint...")
        response = requests.get(f"http://{ip}:{port}/capture", timeout=5)
        print(f"   ✅ Capture endpoint accessible (Status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ Capture endpoint error: {e}")
        return False
    
    print(f"🎉 ESP32-CAM at {ip}:{port} is fully accessible!")
    return True

def main():
    print("🚀 ESP32-CAM Connection Tester")
    print("=" * 40)
    
    # Test current IP from app.py
    current_ip = "192.168.29.115"
    current_port = 81
    
    print(f"Testing current configuration: {current_ip}:{current_port}")
    print()
    
    if test_esp32_connection(current_ip, current_port):
        print(f"\n✅ Your ESP32-CAM is working at {current_ip}:{port}")
        print("The issue might be in the Flask app configuration.")
    else:
        print(f"\n❌ ESP32-CAM is not accessible at {current_ip}:{port}")
        print("\nPossible solutions:")
        print("1. Check if ESP32-CAM is powered on")
        print("2. Check if ESP32-CAM is connected to WiFi")
        print("3. Check if ESP32-CAM has a different IP address")
        print("4. Run 'python find_esp32.py' to find the correct IP")
        
        # Try common alternative ports
        print(f"\n🔍 Trying alternative ports for {current_ip}...")
        for port in [80, 82, 8080]:
            if port != current_port:
                print(f"   Trying port {port}...")
                if test_esp32_connection(current_ip, port):
                    print(f"\n🎉 Found ESP32-CAM at {current_ip}:{port}!")
                    print(f"Update your app.py with: ESP32_IP = \"{current_ip}\"")
                    print(f"And change the port in the ESP32-CAM code to {port}")
                    break

if __name__ == '__main__':
    main()
