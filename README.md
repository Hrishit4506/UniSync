# UniSync - Smart Attendance Management System

A comprehensive Flask-based attendance management system with facial recognition, RFID integration, and role-based access control. Features ESP32-CAM integration for real-time video streaming, Arduino support for RFID attendance marking, and public access through Cloudflare tunnels.

![UniSync](https://img.shields.io/badge/UniSync-v2.0-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)
![Flask](https://img.shields.io/badge/Flask-2.0+-red)
![License](https://img.shields.io/badge/License-MIT-yellow)
![OpenCV](https://img.shields.io/badge/OpenCV-4.8+-orange)
![ESP32](https://img.shields.io/badge/ESP32--CAM-Supported-green)

## ✨ Features

### 🎯 Core Functionality

- **Role-Based Access Control**: Admin, Teacher, and Student roles with distinct permissions
- **Facial Recognition**: Real-time face detection and attendance marking using ESP32-CAM
- **RFID Integration**: Arduino-based RFID card attendance system
- **Manual Attendance**: Teachers can manually mark student attendance
- **Real-time Streaming**: Live video feed from ESP32-CAM with multi-user support
- **Public Access**: Cloudflare tunnel integration for global access

### 🔐 Security & Access Control

- **Admin**: Full system management, user creation, and data access
- **Teacher**: Attendance marking, student management, and reports
- **Student**: Personal attendance records, image upload, and progress tracking

### 📊 Data Management

- **Unified Database**: Single attendance table for all users (facial + manual)
- **Automatic Dataset Creation**: User folders created automatically for training images
- **Image Management**: Secure upload and management of facial recognition training data
- **Data Export**: CSV export functionality for attendance records

### 🌐 Advanced Features

- **Background Streaming**: Continuous ESP32-CAM streaming with frame buffering
- **Multi-User Support**: Multiple users can access video stream simultaneously
- **Performance Optimized**: 30 FPS streaming with <100ms latency
- **Public Hosting**: Cloudflare tunnel integration for internet access
- **Responsive Design**: Modern UI with dark/light theme support

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** with pip
- **ESP32-CAM** (for facial recognition and video streaming)
- **Arduino with RFID module** (for RFID attendance)
- **Git** (for cloning the repository)
- **Internet connection** (for public access features)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/unisync.git
cd unisync
```

### 2. Automated Setup (Recommended)

```bash
python setup.py
```

This script will:

- Create necessary directories
- Install dependencies
- Set up the database
- Create a default admin user
- Generate configuration files
- Optionally set up Render + Cloudflared tunnel integration

### 3. Manual Setup (Alternative)

#### Install Dependencies

```bash
pip install -r requirements.txt
```

#### Configure Environment

```bash
# Copy the example environment file
cp env.example .env

# Edit .env with your configuration
# ESP32_IP=192.168.1.100
# SERIAL_PORT=COM3
# etc.
```

#### Initialize Database

```bash
python -c "from app import app, db; app.app_context().push(); db.create_all()"
```

#### Create Admin User

```bash
python -c "from app import app, db, User; from werkzeug.security import generate_password_hash; app.app_context().push(); db.create_all(); admin = User(username='admin', password_hash=generate_password_hash('admin123'), role='admin'); db.session.add(admin); db.session.commit(); print('Admin user created!')"
```

### 4. Run the Application

#### Option A: Local Development Only

```bash
python app.py
```

#### Option B: Public Access with Cloudflare Tunnel (Recommended)

```bash
# Windows
start_unisync.bat

# Linux/Mac
chmod +x start_unisync.sh
./start_unisync.sh
```

#### Option C: Manual Cloudflare Setup

```bash
# Terminal 1: Start Flask app
python app.py

# Terminal 2: Start Cloudflare tunnel
python cloudflared_config.py
```

### 5. Access the System

- **Local Access**: `http://localhost:5000`
- **Public Access**: Check console for Cloudflare tunnel URL (e.g., `https://abc123.trycloudflare.com`)
- **Default Login**:
  - Username: `admin`
  - Password: `admin123`
  - ⚠️ **Change the default password immediately!**

## 📱 Usage Guide

### 👨‍💼 Admin Functions

- **User Management**: Create, edit, and delete users with role-based permissions
- **System Overview**: Monitor system statistics and user activity
- **Training Image Management**: Upload and manage facial recognition training data
- **Attendance Records**: View and export all attendance data
- **System Configuration**: Manage ESP32-CAM and Arduino settings

### 👩‍🏫 Teacher Functions

- **Manual Attendance**: Mark attendance for individual students or groups
- **Student Management**: View student lists and attendance history
- **Reports**: Generate attendance reports and statistics
- **Quick Actions**: Bulk attendance marking for efficiency

### 👨‍🎓 Student Functions

- **Personal Dashboard**: View attendance statistics and progress
- **Image Upload**: Upload training photos for facial recognition
- **Attendance History**: Track personal attendance records
- **Progress Monitoring**: Weekly and monthly attendance percentages

## 🎥 Video Streaming & Facial Recognition

### How It Works

UniSync features an advanced streaming architecture that supports multiple users simultaneously:

```
ESP32-CAM → Background Thread → Frame Buffer → Multiple Users
    ↓              ↓              ↓            ↓
Continuous    Processes        Stores      Each user gets
Stream        Frames          Latest      Latest frame
              Recognition     Frames      Independently
```

### Key Features

- **Background Streaming**: ESP32-CAM runs continuously in the background
- **Multi-User Support**: Multiple users can view the stream simultaneously
- **Frame Buffering**: Latest frames are cached for smooth playback
- **Real-time Recognition**: Facial recognition runs on each frame
- **Performance Optimized**: 30 FPS streaming with <100ms latency

### Streaming Performance

- **Frame Rate**: Consistent 30 FPS
- **Latency**: Reduced from 500ms+ to <100ms
- **Quality**: Optimized JPEG compression (80% quality)
- **Buffer**: 10-frame buffer prevents frame drops
- **Memory Usage**: ~10MB for frame buffer

### ESP32-CAM Configuration

The system is optimized for ESP32-CAM with these settings:

```cpp
// Optimized settings in CameraWebServer.ino
s->set_framesize(s, FRAMESIZE_VGA);  // 640x480 - good balance
s->set_quality(s, 10);               // Lower quality = faster streaming
s->set_fps(s, 30);                   // 30 FPS for smooth video
```

## 🌐 Public Access with Cloudflare Tunnels

### What is Cloudflare Tunnel?

Cloudflare Tunnel creates secure tunnels to expose your local Flask app to the internet, allowing access from anywhere without configuring routers or firewalls.

### Benefits

- **Global Access**: Access your system from any device with internet
- **Secure**: HTTPS encryption for all connections
- **Real-time**: No need to configure routers or firewalls
- **Free**: No cost for basic tunnel usage
- **Reliable**: Cloudflare's global network infrastructure

### Setup Options

#### Option 1: Automated Setup (Recommended)

```bash
python setup.py
# Choose "y" when asked about tunnel setup
```

#### Option 2: Manual Setup

```bash
# Start Flask app
python app.py

# Start tunnel (separate terminal)
python cloudflared_config.py
```

#### Option 3: Batch Scripts

```bash
# Windows
start_unisync.bat

# Linux/Mac
./start_unisync.sh
```

### Access URLs

- **Local**: `http://localhost:5000`
- **Public**: `https://abc123.trycloudflare.com` (provided by Cloudflare)
- **Status**: Check console output for the public URL

## 🗄️ Database Structure

### User Table

- `id`: Primary key
- `username`: Unique username
- `email`: Unique email address
- `password`: Hashed password (Werkzeug)
- `role`: User role (admin, teacher, student)
- `date_created`: Account creation timestamp

### Unified Attendance Table

All attendance records (facial recognition + manual) are stored in a single `attendance` table:

- `id`: Primary key
- `user_name`: Username of the person
- `date`: Attendance date
- `time_in`: Check-in time
- `time_out`: Check-out time (if applicable)
- `status`: Attendance status (present, absent, late)
- `method`: How attendance was marked (facial, manual, rfid)
- `created_at`: Record creation timestamp

### RFID & Lab Management Tables

- `rfid_card`: RFID card information linked to users
- `computer`: Lab computer management
- `lab_session`: Active lab sessions with passwords

## 🔒 Security Features

- **Role-based access control** with three distinct user roles
- **Password hashing** using Werkzeug's secure password hashing
- **Environment-based configuration** to keep sensitive data out of code
- **Data isolation** with separate tables for each user
- **Input validation** and sanitization
- **CSRF protection** for forms
- **Secure file uploads** with type and size validation
- **Session management** with Flask-Login

## 🛡️ Security Best Practices

### For Production Deployment

1. **Change Default Credentials**: Immediately change the default admin password
2. **Use Environment Variables**: Never commit sensitive data to version control
3. **Enable HTTPS**: Use SSL certificates for production deployments
4. **Regular Updates**: Keep dependencies updated
5. **Database Security**: Use strong database passwords and restrict access
6. **Network Security**: Configure firewalls and network access controls

### Configuration Security

- All sensitive configuration is stored in environment variables
- The `.env` file is gitignored to prevent accidental commits
- Use `env.example` as a template for required environment variables
- Never commit actual API keys, passwords, or IP addresses

## 📁 Project Structure

```
UniSync/
├── app.py                    # Main Flask application
├── config.py                 # Configuration management
├── setup.py                  # Automated setup script
├── run.py                    # Standalone face recognition script
├── requirements.txt          # Python dependencies
├── requirements_render.txt   # Render deployment dependencies
├── env.example              # Environment variables template
├── .gitignore               # Git ignore rules
├── README.md                # This file
├── LICENSE                  # MIT License
├── CONTRIBUTING.md          # Contribution guidelines
│
├── templates/               # HTML templates
│   ├── base.html           # Base template with navigation
│   ├── login.html          # Login page
│   ├── index.html          # Main dashboard
│   ├── admin_dashboard.html # Admin interface
│   ├── teacher_dashboard.html # Teacher interface
│   ├── student_dashboard.html # Student interface
│   ├── admin_user_management.html # User management
│   └── ...                 # Other templates
│
├── static/                  # Static assets
│   ├── css/
│   │   └── theme.css       # Main stylesheet with dark/light themes
│   └── js/
│       └── theme.js        # JavaScript functionality
│
├── instance/               # Database files (gitignored)
│   └── User.db            # SQLite database
│
├── dataset/               # Training images (gitignored)
│   ├── user1/            # User-specific folders
│   ├── user2/
│   └── ...
│
├── Arduino/              # Arduino code
│   └── Arduino.ino       # RFID and display code
│
├── CameraWebServer/      # ESP32-CAM code
│   ├── CameraWebServer.ino
│   └── ...              # ESP32-CAM files
│
├── cloudflared_config.py # Cloudflare tunnel setup
├── tunnel_notifier.py    # Tunnel monitoring
├── render_proxy.py       # Render deployment proxy
├── start_unisync.bat     # Windows startup script
└── start_unisync.sh      # Linux/Mac startup script
```

## 🔌 API Endpoints

### Authentication

- `GET/POST /login` - User login
- `GET /logout` - User logout

### Dashboards

- `GET /` - Main dashboard (redirects based on role)
- `GET /admin/dashboard` - Admin dashboard
- `GET /teacher/dashboard` - Teacher dashboard
- `GET /student/dashboard` - Student dashboard

### User Management (Admin)

- `GET/POST /admin/create_user` - Create new user
- `GET /admin/user_management` - User management interface
- `GET/POST /admin/edit_user/<id>` - Edit user
- `POST /admin/delete_user/<id>` - Delete user
- `POST /admin/reset_user_password/<id>` - Reset user password

### Attendance Management

- `GET/POST /teacher/mark_attendance` - Mark attendance (teacher only)
- `GET /admin/get_user_records/<user_id>` - Get user attendance records
- `GET /admin/export_user_records/<user_id>` - Export user records as CSV
- `POST /admin/add_manual_record` - Add manual attendance record
- `POST /admin/modify_record/<record_id>` - Modify attendance record
- `POST /admin/delete_record/<record_id>` - Delete attendance record

### Facial Recognition

- `GET /video_feed` - Live video stream from ESP32-CAM
- `GET/POST /admin/manage_images/<username>` - Manage training images
- `POST /student/upload_images` - Upload training images (student)

### System Status

- `GET /health` - System health check
- `GET /streaming_status` - Streaming status and performance metrics

## 🛠️ Troubleshooting

### Common Issues

#### 1. Setup Issues

```bash
# Database not created
python setup.py

# Missing dependencies
pip install -r requirements.txt

# Permission errors
# Ensure write permissions to dataset/ and instance/ directories
```

#### 2. ESP32-CAM Connection Issues

```bash
# Check ESP32 IP address in .env file
ESP32_IP=192.168.1.100  # Update with your ESP32's IP

# Test ESP32 connection
curl http://192.168.1.100:81/stream

# Check ESP32-CAM settings
# Ensure it's configured for streaming on port 81
```

#### 3. Streaming Issues

```bash
# Check if background thread is running
# Look for "[Streaming] Background streaming thread started" in logs

# Restart streaming
# Restart the Flask application

# Check frame buffer
# Monitor console for frame processing messages
```

#### 4. Cloudflare Tunnel Issues

```bash
# Tunnel not starting
python cloudflared_config.py

# Check tunnel status
# Look for tunnel URL in console output

# Manual tunnel setup
cloudflared tunnel --url http://localhost:5000
```

#### 5. Database Issues

```bash
# Reset database
rm instance/User.db
python setup.py

# Check database permissions
# Ensure write access to instance/ directory
```

#### 6. Performance Issues

```python
# Reduce frame buffer size in app.py
frame_buffer = queue.Queue(maxsize=5)  # Instead of 10

# Lower frame rate
time.sleep(0.05)  # 20 FPS instead of 30

# Reduce image quality
cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
```

### Debug Information

The system provides detailed logging for troubleshooting:

```
[System] UniSync starting up...
[Database] Database initialized successfully
[Streaming] Background streaming thread started
[ESP32-CAM] Connected to stream at http://192.168.1.100:81/stream
[Face Recognition] Trained 5 faces for 5 people
[System] Facial recognition system is now active and monitoring!
[Cloudflare] Tunnel started: https://abc123.trycloudflare.com
```

### Performance Monitoring

Monitor these metrics for optimal performance:

- **Frame Rate**: Should be consistent 30 FPS
- **Latency**: Should be <100ms
- **Memory Usage**: Frame buffer ~10MB
- **CPU Usage**: Monitor during peak usage
- **Network**: Check ESP32-CAM connection stability

## 🚀 Future Enhancements

### Planned Features

- **WebRTC Support**: Real-time peer-to-peer streaming
- **Multiple Camera Support**: Handle multiple ESP32-CAMs
- **Advanced Analytics**: Detailed attendance analytics and reports
- **Mobile App**: Native mobile application
- **Email Notifications**: Automated attendance notifications
- **Biometric Integration**: Additional biometric authentication methods

### Performance Optimizations

- **GPU Acceleration**: Use GPU for frame processing
- **Advanced Compression**: Better video compression algorithms
- **Load Balancing**: Distribute load across multiple servers
- **Caching**: Implement Redis for session caching

## 📞 Support

If you encounter issues:

1. **Check Logs**: Look for error messages in the console
2. **Verify Configuration**: Ensure all environment variables are set correctly
3. **Test Components**: Verify ESP32-CAM and Arduino connectivity
4. **Check Dependencies**: Ensure all Python packages are installed
5. **Review Documentation**: Check the troubleshooting section above

For additional help:

- **Issues**: Create a GitHub issue with detailed error information
- **Documentation**: See `CLOUDFLARED_SETUP.md` for tunnel-specific help
- **Contributing**: See `CONTRIBUTING.md` for development guidelines

---

**Happy Attendance Tracking! 📊✨**
