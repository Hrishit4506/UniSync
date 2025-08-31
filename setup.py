#!/usr/bin/env python3
"""
UniSync Setup Script
This script helps set up the UniSync application for first-time users.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def create_env_file():
    """Create .env file from template if it doesn't exist"""
    env_file = Path('.env')
    env_example = Path('env.example')
    
    if not env_file.exists() and env_example.exists():
        print("Creating .env file from template...")
        shutil.copy(env_example, env_file)
        print("✅ .env file created. Please edit it with your configuration.")
        return True
    elif env_file.exists():
        print("✅ .env file already exists.")
        return True
    else:
        print("❌ env.example file not found. Please create it first.")
        return False

def create_directories():
    """Create necessary directories"""
    directories = ['instance', 'dataset', 'logs']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Directory '{directory}' created/verified.")

def install_dependencies():
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        print("✅ Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies. Please install them manually:")
        print("   pip install -r requirements.txt")
        return False

def setup_database():
    """Initialize the database"""
    print("Setting up database...")
    try:
        from app import app, db
        with app.app_context():
            db.create_all()
            print("✅ Database initialized successfully.")
            return True
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False

def create_admin_user():
    """Create default admin user"""
    print("Creating default admin user...")
    try:
        from app import app, db, User
        from werkzeug.security import generate_password_hash
        
        with app.app_context():
            # Check if admin user already exists
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    role='admin'
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Default admin user created (username: admin, password: admin123)")
                print("   ⚠️  Please change the default password after first login!")
            else:
                print("✅ Admin user already exists.")
            return True
    except Exception as e:
        print(f"❌ Failed to create admin user: {e}")
        return False

def setup_render_tunnel():
    """Optional: Set up Render + Cloudflared tunnel integration"""
    print("\n🌐 Optional: Render + Cloudflared Tunnel Setup")
    print("-" * 50)
    
    setup_tunnel = input("Do you want to set up Render + Cloudflared tunnel integration? (y/N): ").strip().lower()
    
    if setup_tunnel in ['y', 'yes']:
        try:
            # Check if cloudflared_config.py exists
            if not Path('cloudflared_config.py').exists():
                print("❌ cloudflared_config.py not found. Skipping tunnel setup.")
                return False
            
            # Import cloudflared config
            from cloudflared_config import start_cloudflared
            import requests
            
            print("🚀 Starting cloudflared tunnel...")
            tunnel_url = start_cloudflared(5000)
            
            if tunnel_url:
                print(f"✅ Cloudflared tunnel started!")
                print(f"🌐 Public URL: {tunnel_url}")
                
                # Test connectivity
                print("🔍 Testing tunnel connectivity...")
                try:
                    response = requests.get(tunnel_url, timeout=10)
                    if response.status_code == 200:
                        print("✅ Tunnel is accessible!")
                        
                        # Generate Render config
                        config_content = f"""# Render Environment Variables
CLOUDFLARED_TUNNEL_URL={tunnel_url}

# Render Service Configuration
- Type: Web Service
- Build Command: pip install -r requirements_render.txt
- Start Command: ./start_render_proxy.sh
- Port: 10000
- Health Check Path: /health

# Files to upload to Render:
- render_proxy.py
- requirements_render.txt  
- start_render_proxy.sh
"""
                        
                        with open('render_config.txt', 'w') as f:
                            f.write(config_content)
                        
                        print("✅ Render configuration saved to 'render_config.txt'")
                        print("\n📝 Next steps for Render deployment:")
                        print("1. Deploy the proxy files to Render")
                        print("2. Set CLOUDFLARED_TUNNEL_URL environment variable")
                        print("3. See RENDER_DEPLOYMENT.md for detailed instructions")
                        
                        return True
                    else:
                        print(f"⚠️  Tunnel responded with status: {response.status_code}")
                        return False
                except requests.exceptions.RequestException as e:
                    print(f"❌ Tunnel is not accessible: {e}")
                    print("Please ensure your Flask app is running on port 5000")
                    return False
            else:
                print("⚠️  Cloudflared tunnel started but URL not captured")
                return False
                
        except ImportError:
            print("❌ cloudflared_config.py not found. Skipping tunnel setup.")
            return False
        except Exception as e:
            print(f"❌ Error setting up tunnel: {e}")
            return False
    else:
        print("⏭️  Skipping tunnel setup.")
        return True

def main():
    """Main setup function"""
    print("🚀 UniSync Setup Script")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path('app.py').exists():
        print("❌ app.py not found. Please run this script from the UniSync root directory.")
        sys.exit(1)
    
    success = True
    
    # Create .env file
    if not create_env_file():
        success = False
    
    # Create directories
    create_directories()
    
    # Install dependencies
    if not install_dependencies():
        success = False
    
    # Setup database
    if not setup_database():
        success = False
    
    # Create admin user
    if not create_admin_user():
        success = False
    
    # Optional: Setup Render tunnel
    if success:
        setup_render_tunnel()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Setup completed successfully!")
        print("\nNext steps:")
        print("1. Edit .env file with your configuration (ESP32 IP, Arduino port, etc.)")
        print("2. Run the application: python app.py")
        print("3. Login with admin/admin123 and change the password")
        print("4. Add your ESP32-CAM and Arduino devices")
        print("\n📖 For deployment options, see:")
        print("   - CLOUDFLARED_SETUP.md (for direct cloudflared)")
        print("   - RENDER_DEPLOYMENT.md (for Render + cloudflared)")
    else:
        print("❌ Setup completed with errors. Please check the messages above.")
        sys.exit(1)

if __name__ == '__main__':
    main()
