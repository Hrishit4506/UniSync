#!/usr/bin/env python3
"""
ESP32-CAM IP Finder
This script helps find your ESP32-CAM on the network
"""

import requests
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def scan_port(ip, port, timeout=1):
    """Scan a specific IP and port"""
    try:
        response = requests.get(f"http://{ip}:{port}/", timeout=timeout)
        if response.status_code == 200:
            return ip, port, True
    except:
        pass
    return ip, port, False

def scan_network(base_ip, start_port=80, end_port=82):
    """Scan network for ESP32-CAM"""
    print(f"🔍 Scanning network {base_ip} for ESP32-CAM...")
    print("This may take a few minutes...")
    
    found_devices = []
    
    # Generate IP range (last octet 1-254)
    base_parts = base_ip.split('.')
    if len(base_parts) != 4:
        print("❌ Invalid IP format. Please use format: 192.168.1.1")
        return []
    
    base_network = '.'.join(base_parts[:-1])
    
    # Scan IPs
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        
        for last_octet in range(1, 255):
            ip = f"{base_network}.{last_octet}"
            for port in range(start_port, end_port + 1):
                futures.append(executor.submit(scan_port, ip, port))
        
        # Process results
        for future in as_completed(futures):
            ip, port, success = future.result()
            if success:
                found_devices.append((ip, port))
                print(f"✅ Found device at {ip}:{port}")
    
    return found_devices

def test_esp32_connection(ip, port):
    """Test if the found device is actually an ESP32-CAM"""
    try:
        # Test basic endpoints
        endpoints = ['/', '/stream', '/capture', '/status']
        
        for endpoint in endpoints:
            try:
                url = f"http://{ip}:{port}{endpoint}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    print(f"✅ ESP32-CAM confirmed at {ip}:{port}{endpoint}")
                    return True
            except:
                continue
        
        return False
    except Exception as e:
        print(f"❌ Error testing {ip}:{port}: {e}")
        return False

def main():
    print("🚀 ESP32-CAM IP Finder")
    print("=" * 40)
    
    # Get network base from user
    print("\nEnter your network base IP (e.g., 192.168.1.1):")
    print("Note: Use the IP of your computer's gateway/router")
    
    # Try to auto-detect
    try:
        # Get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        base_parts = local_ip.split('.')
        suggested_base = f"{base_parts[0]}.{base_parts[1]}.{base_parts[2]}.1"
        
        print(f"Suggested network: {suggested_base}")
        print(f"Your local IP: {local_ip}")
        
    except:
        suggested_base = "192.168.1.1"
        print(f"Using default: {suggested_base}")
    
    # Get user input
    user_input = input(f"\nEnter network base (or press Enter for {suggested_base}): ").strip()
    
    if not user_input:
        base_ip = suggested_base
    else:
        base_ip = user_input
    
    print(f"\n🔍 Scanning network: {base_ip}")
    print("Scanning ports 80-82 (common ESP32-CAM ports)...")
    
    # Scan network
    found_devices = scan_network(base_ip, 80, 82)
    
    if not found_devices:
        print("\n❌ No devices found on the network.")
        print("Possible reasons:")
        print("1. ESP32-CAM is not powered on")
        print("2. ESP32-CAM is not connected to WiFi")
        print("3. ESP32-CAM is on a different network")
        print("4. Firewall is blocking connections")
        return
    
    print(f"\n✅ Found {len(found_devices)} device(s):")
    for ip, port in found_devices:
        print(f"   {ip}:{port}")
    
    # Test if they're ESP32-CAMs
    print("\n🔍 Testing if devices are ESP32-CAMs...")
    esp32_devices = []
    
    for ip, port in found_devices:
        if test_esp32_connection(ip, port):
            esp32_devices.append((ip, port))
    
    if esp32_devices:
        print(f"\n🎉 Found {len(esp32_devices)} ESP32-CAM device(s):")
        for ip, port in esp32_devices:
            print(f"   ESP32-CAM: {ip}:{port}")
            print(f"   Stream URL: http://{ip}:{port}/stream")
            print(f"   Web Interface: http://{ip}:{port}/")
        
        print(f"\n📝 Update your app.py with:")
        print(f"ESP32_IP = \"{esp32_devices[0][0]}\"")
        print(f"STREAM_URL = f\"http://{{ESP32_IP}}:{esp32_devices[0][1]}/stream\"")
        
    else:
        print("\n❌ No ESP32-CAM devices found.")
        print("The devices found might be other network devices.")

if __name__ == '__main__':
    main()
