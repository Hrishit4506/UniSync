from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import sqlite3
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import pickle
import requests
import time
import threading
import queue
from collections import deque
from typing import Optional
import calendar
import serial
import json
import itertools
from config import config

# Get configuration based on environment
config_name = os.environ.get('FLASK_ENV', 'development')
app = Flask(__name__)
app.config.from_object(config[config_name])

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# ESP32-CAM Configuration
ESP32_IP = app.config['ESP32_IP']
STREAM_URL = app.config['STREAM_URL']
ESP32_STREAM_URL = app.config['ESP32_STREAM_URL']
DATASET_DIR = app.config['DATASET_DIR']
FACE_SIZE = app.config['FACE_SIZE']
BUFFER_DURATION_SEC = app.config['BUFFER_DURATION_SEC']
CONFIDENCE_THRESHOLD = app.config['CONFIDENCE_THRESHOLD']

# Arduino Configuration
SERIAL_PORT = app.config['SERIAL_PORT']
SERIAL_BAUD = app.config['SERIAL_BAUD']

# Global variables for face recognition (from run.py)
face_recognizer = None
label_map = {}
pred_buffer = deque()
time_buffer = deque()
display_name = "Waiting..."
prev_name_serial = ""
ser = None

# Global variables for improved streaming
frame_buffer = queue.Queue(maxsize=2)  # Minimal buffer to prevent ghosting
streaming_active = False
stream_thread = None
current_frame = None
frame_lock = threading.Lock()
last_frame_time = time.time()  # Track when last frame was processed
frame_timestamp = 0  # Track frame age to prevent ghosting

# Streaming configuration constants
STREAM_FPS = 10  # Very low FPS for maximum stability and responsiveness
STREAM_FRAME_AGE_THRESHOLD = 0.3  # Balanced threshold for responsiveness
STREAM_DELAY = 1.0 / STREAM_FPS  # Delay between frames for smooth streaming

db = SQLAlchemy(app)

# ---------- MINIMAL STREAM (single OpenCV capture, shared JPEG bytes) ----------
basic_frame = None  # raw JPEG bytes
basic_frame_bgr = None  # last decoded BGR frame
basic_frame_lock = threading.Lock()
basic_capture_started = False
recognition_active = False
recognition_thread = None
recognition_recent_names = deque(maxlen=7)
recognition_last_change_time = 0.0
recognition_last_seen_time = 0.0
NAME_WINDOW_MIN_COUNT = 3
NAME_UPDATE_COOLDOWN_SEC = 0.2
UNKNOWN_RESET_TIMEOUT_SEC = 1.0

# ---------- LAB MANAGEMENT: RFID → Student, Computers, Sessions ----------
class RFIDCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(64), unique=True, nullable=False)  # hex string from UNO
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Computer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    is_in_use = db.Column(db.Boolean, default=False)
    current_session_id = db.Column(db.Integer, nullable=True)

class LabSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    computer_id = db.Column(db.Integer, db.ForeignKey('computer.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    password = db.Column(db.String(32), nullable=False)

def _generate_session_password(length: int = 8) -> str:
    import secrets
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def _find_available_computer() -> Optional[Computer]:
    return Computer.query.filter_by(is_in_use=False).order_by(Computer.id.asc()).first()

def _assign_computer_to_user(user_id: int) -> Optional[LabSession]:
    free_pc = _find_available_computer()
    if not free_pc:
        return None
    pwd = _generate_session_password()
    session_row = LabSession(user_id=user_id, computer_id=free_pc.id, password=pwd)
    db.session.add(session_row)
    db.session.flush()
    free_pc.is_in_use = True
    free_pc.current_session_id = session_row.id
    db.session.commit()
    return session_row

def _end_active_session_for_user(user_id: int) -> Optional[LabSession]:
    active = LabSession.query.filter_by(user_id=user_id, end_time=None).order_by(LabSession.start_time.desc()).first()
    if not active:
        return None
    active.end_time = datetime.utcnow()
    pc = Computer.query.get(active.computer_id)
    if pc:
        pc.is_in_use = False
        pc.current_session_id = None
    db.session.commit()
    return active

def _capture_basic_frames():
    global basic_frame
    print(f"[BasicStream] Opening {ESP32_STREAM_URL}...")
    cap = cv2.VideoCapture(ESP32_STREAM_URL)
    while True:
        ok, img = cap.read()
        if not ok or img is None:
            time.sleep(0.05)
            continue
        ok, buf = cv2.imencode('.jpg', img)
        if not ok:
            continue
        with basic_frame_lock:
            basic_frame = buf.tobytes()
            # store decoded frame for recognition thread
            global basic_frame_bgr
            basic_frame_bgr = img

def _ensure_basic_capture_started():
    global basic_capture_started
    if not basic_capture_started:
        t = threading.Thread(target=_capture_basic_frames, daemon=True)
        t.start()
        basic_capture_started = True
        _ensure_recognition_started()

def _ensure_recognition_started():
    global recognition_active, recognition_thread
    if recognition_active:
        return
    recognition_active = True
    recognition_thread = threading.Thread(target=_recognition_loop, daemon=True)
    recognition_thread.start()

def _recognition_loop():
    # Initialize cascade once
    try:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:
        face_cascade = None
    while recognition_active:
        # Snapshot the latest frame
        with basic_frame_lock:
            frame_bgr = None if basic_frame_bgr is None else basic_frame_bgr.copy()
        if frame_bgr is not None and frame_bgr.size > 0 and face_cascade is not None:
            try:
                # Run recognition updates (overlays not required for stream)
                _ = process_frame_for_recognition(frame_bgr, face_cascade)
            except Exception as e:
                # Keep going even if recognition fails
                pass
        time.sleep(0.1)

# ---------- FAST MJPEG CAPTURE (single upstream, multi-client) ----------
fast_capture_active = False
fast_capture_thread = None
fast_capture_frame = None  # raw JPEG bytes
fast_capture_lock = threading.Lock()
fast_capture_url = None
fast_capture_timestamp = 0.0

def _probe_url(url: str, timeout: float = 2.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout, stream=True)
        ok = r.status_code == 200
        try:
            r.close()
        except:
            pass
        return ok
    except Exception:
        return False

def _select_stream_url(preferred: Optional[str] = None) -> str:
    candidates = []
    if preferred:
        candidates.append(preferred)
    # try port 81 first, then default
    candidates.extend([
        f"http://{ESP32_IP}:81/stream",
        f"http://{ESP32_IP}/stream",
    ])
    seen = []
    for u in candidates:
        if u in seen:
            continue
        seen.append(u)
        if _probe_url(u):
            print(f"[FastCapture] Selected stream URL: {u}")
            return u
    # fallback to first
    fallback = candidates[0]
    print(f"[FastCapture] Probing failed, using fallback: {fallback}")
    return fallback

def start_fast_capture(url: Optional[str] = None):
    """Start a single OpenCV capture on ESP32 MJPEG stream and share frames."""
    global fast_capture_active, fast_capture_thread, fast_capture_url
    fast_capture_url = _select_stream_url(url)
    if fast_capture_active:
        return
    fast_capture_active = True
    fast_capture_thread = threading.Thread(target=_fast_capture_loop, daemon=True)
    fast_capture_thread.start()
    print(f"[FastCapture] Started for {fast_capture_url}")

def stop_fast_capture():
    global fast_capture_active, fast_capture_thread
    fast_capture_active = False
    if fast_capture_thread and fast_capture_thread.is_alive():
        fast_capture_thread.join(timeout=2)
        print("[FastCapture] Stopped")

def _fast_capture_loop():
    global fast_capture_frame
    cap = None
    while fast_capture_active:
        try:
            if cap is None or not cap.isOpened():
                print(f"[FastCapture] Opening {fast_capture_url}...")
                # Prefer FFMPEG backend for HTTP MJPEG
                try:
                    cap = cv2.VideoCapture(fast_capture_url, cv2.CAP_FFMPEG)
                except Exception:
                    cap = cv2.VideoCapture(fast_capture_url)
                if not cap.isOpened():
                    print("[FastCapture] Failed to open stream, retrying in 2s")
                    time.sleep(2)
                    continue

            ok, img = cap.read()
            if not ok or img is None:
                # transient error; try to reopen
                print("[FastCapture] Read failed, reopening...")
                try:
                    cap.release()
                except:
                    pass
                cap = None
                time.sleep(0.2)
                continue

            # Encode once to JPEG and store bytes
            ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ok:
                continue
            with fast_capture_lock:
                fast_capture_frame = buf.tobytes()
                global fast_capture_timestamp
                fast_capture_timestamp = time.time()

        except Exception as e:
            print(f"[FastCapture] Error: {e}")
            time.sleep(0.5)
    # Cleanup
    try:
        if cap is not None:
            cap.release()
    except:
        pass

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

# ---------- MODELS ----------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    role = db.Column(db.String(20), default='student')  # admin, teacher, student
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def is_admin(self):
        return self.role == 'admin'
    
    def is_teacher(self):
        return self.role == 'teacher'
    
    def is_student(self):
        return self.role == 'student'

# Dynamic table creation for each user's attendance
def create_user_attendance_table(username):
    """Create a separate attendance table for a specific user"""
    table_name = f"attendance_{username.lower().replace(' ', '_')}"
    
    # Create table if it doesn't exist
    with db.engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                time_in DATETIME,
                time_out DATETIME,
                status VARCHAR(20) DEFAULT 'absent',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()

def get_user_attendance_table(username):
    """Get the attendance table name for a user"""
    return f"attendance_{username.lower().replace(' ', '_')}"

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_dataset_folder(username):
    """Create dataset folder for new user"""
    try:
        dataset_path = os.path.join('dataset', username)
        
        if not os.path.exists(dataset_path):
            os.makedirs(dataset_path)
            print(f"Created dataset folder for user: {username}")
            
        return True
    except Exception as e:
        print(f"Error creating dataset folder: {e}")
        return False

# ---------- FACE RECOGNITION FUNCTIONS ----------
def prepare_training_data(dataset_path):
    """Prepare training data for face recognition"""
    global face_recognizer, label_map
    
    try:
        faces = []
        labels = []
        label_id = 0
        label_map = {}
        
        # Walk through dataset directory
        for root, dirs, files in os.walk(dataset_path):
            for dir_name in dirs:
                label_map[label_id] = dir_name
                dir_path = os.path.join(root, dir_name)
                
                # Process images in user directory
                for filename in os.listdir(dir_path):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        img_path = os.path.join(dir_path, filename)
                        img = cv2.imread(img_path)
                        if img is not None:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            faces.append(gray)
                            labels.append(label_id)
                
                label_id += 1
        
        if len(faces) > 0:
            # Train the face recognizer
            face_recognizer = cv2.face.LBPHFaceRecognizer_create()
            face_recognizer.train(faces, np.array(labels))
            print(f"Trained {len(faces)} images for {len(label_map)} people")
            return True
        else:
            print("No training images found")
            return False
            
    except Exception as e:
        print(f"Error preparing training data: {e}")
        return False

def get_facial_recognition_attendance(username):
    """Get attendance data for a user from facial recognition system"""
    try:
        conn = sqlite3.connect(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        # Get attendance records for the user
        cursor.execute('''
            SELECT date, time_in, time_out, status 
            FROM attendance 
            WHERE user_name = ? 
            ORDER BY date DESC
        ''', (username,))
        
        results = cursor.fetchall()
        conn.close()
        
        attendance_data = []
        for row in results:
            attendance_data.append({
                'date': row[0],
                'time_in': row[1],
                'time_out': row[2],
                'status': row[3]
            })
        
        return attendance_data
        
    except Exception as e:
        print(f"Error getting attendance data: {e}")
        return []

# ---------- STREAMING FUNCTIONS ----------
def start_streaming_thread():
    """Start the background streaming thread"""
    global streaming_active, stream_thread, STREAM_URL, ESP32_IP
    
    # Ensure required variables are defined
    if 'STREAM_URL' not in globals() or 'ESP32_IP' not in globals():
        print("[Streaming Error] Required variables not defined, initializing...")
        ESP32_IP = app.config.get('ESP32_IP', '192.168.1.100')
        STREAM_URL = f"http://{ESP32_IP}/stream"
    
    if not streaming_active:
        streaming_active = True
        stream_thread = threading.Thread(target=stream_esp32_frames, daemon=True)
        stream_thread.start()
        print("[Streaming] Background streaming thread started")

def stop_streaming_thread():
    """Stop the background streaming thread"""
    global streaming_active, stream_thread
    
    streaming_active = False
    if stream_thread and stream_thread.is_alive():
        stream_thread.join(timeout=2)
        print("[Streaming] Background streaming thread stopped")

def stream_esp32_frames():
    """Background thread for continuous ESP32-CAM streaming and processing"""
    global current_frame, frame_timestamp, last_frame_time, STREAM_URL
    
    print("[Streaming] Background streaming thread started")
    frame_count = 0
    start_time = time.time()
    
    # Ensure STREAM_URL is defined
    if 'STREAM_URL' not in globals():
        print("[Streaming Error] STREAM_URL not defined, initializing...")
        global ESP32_IP
        STREAM_URL = f"http://{ESP32_IP}/stream"
    
    while streaming_active:
        try:
            # Use a session for persistent connection
            session = requests.Session()
            print(f"[Streaming] Attempting to connect to ESP32-CAM at {STREAM_URL}...")
            
            # Test connection first
            try:
                test_response = session.get(f"http://{ESP32_IP}/", timeout=5)
                print(f"[Streaming] ESP32-CAM main page status: {test_response.status_code}")
            except Exception as e:
                print(f"[Streaming] ESP32-CAM main page test failed: {e}")
            
            stream = session.get(STREAM_URL, stream=True, timeout=10)
            
            if stream.status_code != 200:
                print(f"[Streaming Error] ESP32 stream returned status {stream.status_code}")
                print(f"[Streaming] Trying alternative stream URLs...")
                
                # Try alternative stream URLs (prioritizing high quality)
                alternative_urls = [
                    f"http://{ESP32_IP}:81/stream",  # Port 81 often has better quality
                    f"http://{ESP32_IP}/cam-hi.jpg",  # High quality single images
                    f"http://{ESP32_IP}/cam-lo.jpg",  # Low quality fallback
                    f"http://{ESP32_IP}/stream",      # Original stream as fallback
                    f"http://{ESP32_IP}:81/cam-hi.jpg" # Port 81 high quality images
                ]
                
                for alt_url in alternative_urls:
                    try:
                        print(f"[Streaming] Trying: {alt_url}")
                        alt_stream = session.get(alt_url, stream=True, timeout=5)
                        if alt_stream.status_code == 200:
                            print(f"[Streaming] Alternative URL works: {alt_url}")
                            stream = alt_stream
                            STREAM_URL = alt_url  # Update the global URL
                            break
                    except Exception as e:
                        print(f"[Streaming] Alternative URL failed: {alt_url} - {e}")
                else:
                    print(f"[Streaming] All stream URLs failed, retrying in 15 seconds...")
                    time.sleep(15)
                    continue
            
            print(f"[Streaming] Successfully connected to ESP32-CAM!")
            bytes_buffer = b''
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            
            for chunk in stream.iter_content(chunk_size=1024):
                if not streaming_active:
                    break
                    
                bytes_buffer += chunk
                a = bytes_buffer.find(b'\xff\xd8')
                b = bytes_buffer.find(b'\xff\xd9')
                
                if a != -1 and b != -1:
                    jpg = bytes_buffer[a:b+2]
                    bytes_buffer = bytes_buffer[b+2:]
                    
                    if len(jpg) < 100:
                        continue

                    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    if img is None or img.size == 0:
                        print("[Streaming] Invalid image decoded, skipping frame")
                        continue
                    
                    # Additional validation
                    if img.shape[0] < 10 or img.shape[1] < 10:
                        print("[Streaming] Image too small, skipping frame")
                        continue

                    # Process frame for face recognition with error handling
                    try:
                        if img is not None and img.size > 0:
                            print(f"[Streaming] Processing frame: {img.shape}, size: {img.size}")
                            processed_img = process_frame_for_recognition(img, face_cascade)
                            if processed_img is None:
                                print("[Streaming] Face recognition failed, using original frame")
                                processed_img = img
                        else:
                            print("[Streaming] Invalid image, skipping processing")
                            processed_img = img
                    except Exception as e:
                        print(f"[Streaming] Face recognition error: {e}, using original frame")
                        processed_img = img
                    
                    # Store the latest frame efficiently
                    with frame_lock:
                        current_frame = processed_img
                        frame_timestamp = time.time()  # Update timestamp
                        if frame_count % 200 == 0:  # Log much less frequently
                            print(f"[Streaming] Frame {frame_count} stored: {processed_img.shape}")
                    
                    # Add frame to buffer without clearing (let it manage itself)
                    try:
                        if frame_buffer.full():
                            frame_buffer.get_nowait()  # Remove oldest frame only if full
                        frame_buffer.put_nowait(processed_img)
                    except queue.Full:
                        pass  # Should not happen with proper management
                    
                    # Optimized delay for smooth streaming without ghosting
                    time.sleep(STREAM_DELAY)  # Using configurable delay for stable streaming
                    
                    # Performance monitoring (reduced frequency)
                    frame_count += 1
                    if frame_count % 500 == 0:  # Log every 500 frames
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed
                        print(f"[Streaming] Performance: {fps:.1f} FPS, {frame_count} frames processed")
                    
                    # Update heartbeat
                    global last_frame_time
                    last_frame_time = time.time()
                    
        except requests.exceptions.ConnectTimeout:
            print(f"[Streaming] Connection timeout - ESP32-CAM not responding. Retrying in 30 seconds...")
            time.sleep(30)
        except requests.exceptions.ConnectionError:
            print(f"[Streaming] Connection refused - ESP32-CAM not accessible. Retrying in 30 seconds...")
            time.sleep(30)
        except Exception as e:
            print(f"[Streaming Error] {e}. Retrying in 30 seconds...")
            time.sleep(30)
        finally:
            try:
                session.close()
            except:
                pass
    
    print("[Streaming] Background streaming thread ended")

def process_frame_for_recognition(img, face_cascade):
    """Process a frame for face recognition and return the processed frame"""
    global pred_buffer, time_buffer, display_name
    
    # Use a simple counter for logging control
    if not hasattr(process_frame_for_recognition, 'frame_count'):
        process_frame_for_recognition.frame_count = 0
    process_frame_for_recognition.frame_count += 1
    
    # Validate image before processing
    if img is None or img.size == 0:
        print("[Face Detection] Invalid image received, skipping processing")
        return img
    
    # Get image dimensions safely
    try:
        height, width = img.shape[:2]
    except:
        print("[Face Detection] Error getting image dimensions")
        return img
    
    # Enhanced face detection with better parameters for low-quality video
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Use more sensitive parameters for low-quality video
        faces_rects = face_cascade.detectMultiScale(
            gray, 
            scaleFactor=1.05,  # More sensitive scaling
            minNeighbors=3,    # Fewer neighbors required
            minSize=(60, 60),  # Larger minimum face size
            maxSize=(300, 300) # Maximum face size
        )
    except Exception as e:
        print(f"[Face Detection] Error in face detection: {e}")
        faces_rects = []
    
    if len(faces_rects) > 0:
        # Reduced logging for performance
        if process_frame_for_recognition.frame_count % 100 == 0:
            print(f"[Face Detection] Found {len(faces_rects)} face(s) in frame")
        
        for (x, y, w, h) in faces_rects:
            # Always draw rectangle first
            cv2.rectangle(img, (x, y), (x+w, y+h), (255, 0, 0), 2)
            
            # Perform face recognition if model is available
            if face_recognizer is not None:
                try:
                    roi = gray[y:y+h, x:x+w]
                    roi_resized = cv2.resize(roi, FACE_SIZE)
                    label_id, confidence = face_recognizer.predict(roi_resized)
                    name = label_map.get(label_id, "Unknown")
                    
                    # Better confidence handling for low-quality video
                    # Debounce and require short consistency before switching
                    if confidence < CONFIDENCE_THRESHOLD:
                        pred_this_frame = name
                    else:
                        pred_this_frame = "Unknown"
                    
                    # Color coding: Green for recognized, Red for unknown
                    # Stabilize identity decision using short-term window and cooldown
                    decided_name = _stabilize_identity(pred_this_frame)

                    if decided_name != "Unknown":
                        color = (0, 255, 0)
                        cv2.rectangle(img, (x, y), (x+w, y+h), color, 2)
                        cv2.putText(img, f"{decided_name} ({confidence:.1f})", (x, y-5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        if decided_name != display_name:
                            display_name = decided_name
                            mark_attendance_from_recognition(display_name)
                    else:
                        color = (0, 0, 255)
                        cv2.rectangle(img, (x, y), (x+w, y+h), color, 2)
                        cv2.putText(img, f"Unknown ({confidence:.1f})", (x, y-5),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        
                except Exception as e:
                    print(f"[Recognition Error] {e}")
                    cv2.putText(img, "Unknown", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            else:
                cv2.putText(img, "Face Detected", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    else:
        # Reduced logging for performance
        if process_frame_for_recognition.frame_count % 200 == 0:
            print("[Face Detection] No faces detected in frame")
    
    # Add status text overlay
    cv2.putText(img, f"Status: {display_name}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    return img

def _stabilize_identity(candidate_name: str) -> str:
    """Stabilize identity by requiring short agreement window and cooldown."""
    global recognition_recent_names, recognition_last_change_time, recognition_last_seen_time, display_name
    now = time.time()

    # Record latest candidate
    recognition_recent_names.append(candidate_name)
    recognition_last_seen_time = now

    # If the current display_name keeps appearing, keep it unless strong contradiction
    if display_name != "Waiting..." and display_name in recognition_recent_names:
        # Only allow change after cooldown
        if now - recognition_last_change_time < NAME_UPDATE_COOLDOWN_SEC:
            return display_name

    # Require the new candidate to appear at least NAME_WINDOW_MIN_COUNT times in window
    if candidate_name != "Unknown" and recognition_recent_names.count(candidate_name) >= NAME_WINDOW_MIN_COUNT:
        if candidate_name != display_name:
            recognition_last_change_time = now
        return candidate_name

    # If we see mostly unknown for a while, allow reset to Unknown
    if recognition_recent_names.count("Unknown") >= NAME_WINDOW_MIN_COUNT and (now - recognition_last_change_time) > UNKNOWN_RESET_TIMEOUT_SEC:
        if display_name != "Unknown":
            recognition_last_change_time = now
        return "Unknown"

    # Default: keep current name to avoid flicker
    return display_name if display_name else "Unknown"

def mark_attendance_from_recognition(username):
    """Mark attendance when a person is recognized"""
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        today = date.today()
        current_time = datetime.now()
        
        # Check if attendance already marked today
        cursor.execute('''
            SELECT id FROM attendance 
            WHERE user_name = ? AND date = ?
        ''', (username, today))
        
        existing = cursor.fetchone()
        
        if not existing:
            # Mark new attendance
            cursor.execute('''
                INSERT INTO attendance (user_name, date, time_in, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (username, today, current_time, current_time))
            
            conn.commit()
            print(f"[Attendance] Marked attendance for {username} at {current_time}")
            
            # Send serial command to Arduino
            print(f"[Attendance] Marked attendance for {username} at {current_time}")
            
            # Send serial command to Arduino
            send_serial_command(f"ATTENDANCE:{username}")
        
        conn.close()
        
    except Exception as e:
        print(f"[Attendance Error] {e}")

def send_serial_command(command):
    """Send command to Arduino via serial"""
    global ser
    
    if ser is not None and ser.is_open:
        try:
            ser.write(f"{command}\n".encode())
            print(f"[Serial] Sent command: {command}")
        except Exception as e:
            print(f"[Serial Error] Failed to send command: {e}")
    else:
        print(f"[Serial] (not connected) Would send: {command}")

def _readline_nonblocking(port: serial.Serial) -> Optional[str]:
    try:
        if port.in_waiting > 0:
            line = port.readline().decode(errors='ignore').strip()
            return line if line else None
    except Exception:
        return None
    return None

def _handle_rfid_uid(uid_hex: str):
    try:
        card = RFIDCard.query.filter_by(uid=uid_hex).first()
        if not card:
            print(f"[RFID] Unknown card {uid_hex}. Awaiting binding.")
            return
        user = User.query.get(card.user_id)
        if not user:
            print(f"[RFID] Card mapped to missing user_id={card.user_id}")
            return
        # Toggle logic: if user has an active session, end it; else assign one
        active = LabSession.query.filter_by(user_id=user.id, end_time=None).first()
        if active:
            ended = _end_active_session_for_user(user.id)
            if ended:
                uptime = (ended.end_time - ended.start_time).total_seconds()
                print(f"[Lab] Ended session for {user.username} on PC{ended.computer_id} after {uptime:.0f}s")
                # Do not send passwords over serial; optional minimal logout notice
                send_serial_command(f"LOGOUT:{user.username}:PC{ended.computer_id}")
        else:
            session_row = _assign_computer_to_user(user.id)
            if not session_row:
                print("[Lab] No free computers available")
                send_serial_command("NO_FREE_PC")
                return
            pc = Computer.query.get(session_row.computer_id)
            print(f"[Lab] Assigned {user.username} to {pc.name} (password hidden)")
            # Do not send the password over serial; optional minimal login notice without password
            send_serial_command(f"LOGIN:{user.username}:{pc.name}")
    except Exception as e:
        print(f"[RFID Handler Error] {e}")

def start_serial_listener():
    """Background thread: listen for RFID scans over serial.
    Expected UNO messages (one per line): UID:<hex> e.g., UID:DE AD BE EF
    """
    def loop():
        global ser
        print("[SerialListener] Starting...")
        # Ensure application context for DB work inside thread
        with app.app_context():
            while True:
                try:
                    if ser is None or not ser.is_open:
                        try:
                            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
                            time.sleep(2)
                            print(f"[SerialListener] Reconnected {SERIAL_PORT}")
                        except Exception as e:
                            time.sleep(1)
                            continue
                    line = _readline_nonblocking(ser)
                    if not line:
                        time.sleep(0.05)
                        continue
                    if line.startswith('UID:'):
                        uid_raw = line.split(':', 1)[1].strip()
                        uid_hex = uid_raw.replace(' ', '').upper()
                        print(f"[RFID] UID scanned: {uid_hex}")
                        _handle_rfid_uid(uid_hex)
                    else:
                        # other messages can be logged
                        pass
                except Exception:
                    time.sleep(0.2)
                    continue
    t = threading.Thread(target=loop, daemon=True)
    t.start()

# ---------- SERIAL COMMUNICATION ----------
def init_serial():
    """Initialize serial connection with Arduino"""
    global ser
    
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        time.sleep(2)  # Wait for Arduino to reset
        print(f"[Serial] Connected to Arduino on {SERIAL_PORT}")
        return True
    except Exception as e:
        print(f"[Serial Error] Failed to connect to Arduino: {e}")
        return False

# ---------- ROUTES ----------
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        elif current_user.is_teacher():
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    # Redirect unauthenticated users to login
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Registration disabled
    flash('Registration is disabled. Please contact the administrator.', 'warning')
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)

@app.route('/admin/user_management')
@login_required
def admin_user_management():
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    try:
        users = User.query.all()
        print(f"DEBUG: Found {len(users)} users in database")
        for user in users:
            print(f"DEBUG: User - ID: {user.id}, Username: {user.username}, Role: {user.role}")
        
        return render_template('admin_user_management.html', users=users)
    except Exception as e:
        print(f"DEBUG: Error in admin_user_management: {e}")
        flash(f'Error loading users: {str(e)}', 'error')
        return render_template('admin_user_management.html', users=[])

@app.route('/admin/bind_card', methods=['POST'])
@login_required
def bind_card():
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    try:
        data = request.get_json(silent=True) or {}
        uid = (data.get('uid') or request.form.get('uid') or '').replace(' ', '').upper()
        username = (data.get('username') or request.form.get('username') or '').strip()
        if not uid or not username:
            return jsonify({'error': 'uid and username are required'}), 400
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        existing = RFIDCard.query.filter_by(uid=uid).first()
        if existing and existing.user_id != user.id:
            return jsonify({'error': 'Card already bound to another user'}), 409
        if not existing:
            existing = RFIDCard(uid=uid, user_id=user.id)
            db.session.add(existing)
        else:
            existing.user_id = user.id
        db.session.commit()
        # Support form submissions by redirecting back to GUI
        if request.is_json:
            return jsonify({'success': True, 'uid': uid, 'username': username})
        flash('RFID card bound successfully', 'success')
        return redirect(url_for('admin_rfid'))
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/lab_status')
@login_required
def lab_status():
    if not current_user.is_admin() and not current_user.is_teacher():
        return jsonify({'error': 'Access denied'}), 403
    try:
        pcs = Computer.query.order_by(Computer.id.asc()).all()
        response = []
        now = datetime.utcnow()
        for pc in pcs:
            session_id = pc.current_session_id
            session_data = None
            uptime_seconds = 0
            if session_id:
                s = LabSession.query.get(session_id)
                if s:
                    uptime_seconds = int((now - s.start_time).total_seconds())
                    user = User.query.get(s.user_id)
                    session_data = {
                        'session_id': s.id,
                        'user': user.username if user else None,
                        'start_time': s.start_time.isoformat(),
                        'password': s.password
                    }
            response.append({
                'id': pc.id,
                'name': pc.name,
                'is_in_use': pc.is_in_use,
                'uptime_seconds': uptime_seconds,
                'session': session_data
            })
        return jsonify({'computers': response})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/rfid')
@login_required
def admin_rfid():
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    # List users and existing mappings
    users = User.query.order_by(User.username.asc()).all()
    mappings = db.session.query(RFIDCard, User).join(User, RFIDCard.user_id == User.id).order_by(RFIDCard.uid.asc()).all()
    return render_template('admin_rfid.html', users=users, mappings=mappings)

@app.route('/admin/unbind_card', methods=['POST'])
@login_required
def unbind_card():
    if not current_user.is_admin():
        return jsonify({'error': 'Access denied'}), 403
    try:
        data = request.get_json(silent=True) or {}
        uid = (data.get('uid') or request.form.get('uid') or '').replace(' ', '').upper()
        if not uid:
            return jsonify({'error': 'uid is required'}), 400
        card = RFIDCard.query.filter_by(uid=uid).first()
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        db.session.delete(card)
        db.session.commit()
        if request.is_json:
            return jsonify({'success': True, 'uid': uid})
        flash('RFID card unbound', 'success')
        return redirect(url_for('admin_rfid'))
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('create_user.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('create_user.html')
        
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(username=username, email=email, password=hashed_password, role=role)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Create dataset folder for new user
        create_dataset_folder(username)
        
        flash('User created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_user.html')

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        user.role = request.form['role']
        
        if request.form['password']:
            user.password = generate_password_hash(request.form['password'], method='sha256')
        
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_user.html', user=user)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/manage_images/<username>')
@login_required
def admin_manage_images(username):
    """Admin page to manage user images for facial recognition"""
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Get list of images in user's dataset folder
    user_dataset_path = os.path.join(DATASET_DIR, username)
    images = []
    
    if os.path.exists(user_dataset_path):
        for filename in os.listdir(user_dataset_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                images.append(filename)
    
    return render_template('admin_manage_images.html', user=user, images=images)

@app.route('/admin/manage_images/<username>', methods=['POST'])
@login_required
def admin_manage_images_post(username):
    """Handle image uploads for user facial recognition training"""
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if 'images' not in request.files:
        flash('No images selected', 'error')
        return redirect(url_for('admin_manage_images', username=username))
    
    files = request.files.getlist('images')
    uploaded_count = 0
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            # Create user dataset folder if it doesn't exist
            user_dataset_path = os.path.join(DATASET_DIR, username)
            if not os.path.exists(user_dataset_path):
                os.makedirs(user_dataset_path)
            
            # Save the image
            filename = secure_filename(file.filename)
            file_path = os.path.join(user_dataset_path, filename)
            file.save(file_path)
            uploaded_count += 1
    
    if uploaded_count > 0:
        flash(f'{uploaded_count} image(s) uploaded successfully for {username}', 'success')
        # Retrain the facial recognition model
        prepare_training_data(DATASET_DIR)
    else:
        flash('No valid images were uploaded', 'error')
    
    return redirect(url_for('admin_manage_images', username=username))

@app.route('/admin/serve_image/<username>/<filename>')
@login_required
def serve_image(username, filename):
    """Serve uploaded images for display"""
    # Allow admins or the student who owns the images to view
    if not (current_user.is_admin() or (current_user.is_student() and current_user.username == username)):
        return jsonify({'error': 'Access denied'}), 403
    
    user_dataset_path = os.path.join(DATASET_DIR, username)
    file_path = os.path.join(user_dataset_path, filename)
    
    if os.path.exists(file_path) and allowed_file(filename):
        return send_from_directory(user_dataset_path, filename)
    else:
        return jsonify({'error': 'Image not found'}), 404

@app.route('/admin/delete_image/<username>/<filename>', methods=['POST'])
@login_required
def delete_image(username, filename):
    """Delete a training image"""
    # Allow admins or the student who owns the images to delete
    if not (current_user.is_admin() or (current_user.is_student() and current_user.username == username)):
        flash('Access denied', 'error')
        # Redirect to appropriate page based on role
        if current_user.is_admin():
            return redirect(url_for('admin_manage_images', username=username))
        return redirect(url_for('student_dashboard'))
    
    user_dataset_path = os.path.join(DATASET_DIR, username)
    file_path = os.path.join(user_dataset_path, filename)
    
    if os.path.exists(file_path) and allowed_file(filename):
        os.remove(file_path)
        flash(f'Image {filename} deleted successfully', 'success')
        # Retrain the facial recognition model
        prepare_training_data(DATASET_DIR)
    else:
        flash('Image not found or invalid file', 'error')
    
    return redirect(url_for('admin_manage_images', username=username))

@app.route('/student/upload_images', methods=['GET', 'POST'])
@login_required
def student_upload_images():
    """Allow a student to upload and manage their own training images"""
    if not current_user.is_student():
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    username = current_user.username
    user_dataset_path = os.path.join(DATASET_DIR, username)

    if request.method == 'POST':
        if 'images' not in request.files:
            flash('No images selected', 'error')
            return redirect(url_for('student_upload_images'))

        files = request.files.getlist('images')
        uploaded_count = 0

        for file in files:
            if file and file.filename and allowed_file(file.filename):
                if not os.path.exists(user_dataset_path):
                    os.makedirs(user_dataset_path)
                filename = secure_filename(file.filename)
                file_path = os.path.join(user_dataset_path, filename)
                file.save(file_path)
                uploaded_count += 1

        if uploaded_count > 0:
            flash(f'{uploaded_count} image(s) uploaded successfully', 'success')
            try:
                prepare_training_data(DATASET_DIR)
            except Exception as e:
                flash(f'Images uploaded but training failed: {e}', 'warning')
        else:
            flash('No valid images were uploaded', 'error')
        return redirect(url_for('student_upload_images'))

    # GET: list existing images
    images = []
    if os.path.exists(user_dataset_path):
        for filename in os.listdir(user_dataset_path):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                images.append(filename)

    return render_template('student_upload_images.html', images=images)

@app.route('/admin/train_user_faces/<username>')
@login_required
def train_user_faces(username):
    """Train facial recognition model for a specific user"""
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('admin_dashboard'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Retrain the facial recognition model
        if prepare_training_data(DATASET_DIR):
            flash(f'Facial recognition model retrained successfully! {len(label_map)} people trained.', 'success')
        else:
            flash('Failed to train facial recognition model. Check if images are available.', 'error')
    except Exception as e:
        flash(f'Error training model: {str(e)}', 'error')
    
    return redirect(url_for('admin_manage_images', username=username))

@app.route('/admin/streaming_settings', methods=['GET', 'POST'])
@login_required
def admin_streaming_settings():
    """Admin page to configure streaming settings"""
    global STREAM_FPS, STREAM_FRAME_AGE_THRESHOLD, STREAM_DELAY
    
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            new_fps = int(request.form.get('stream_fps', 30))
            new_threshold = float(request.form.get('frame_age_threshold', 0.15))
            
            # Validate inputs
            if 10 <= new_fps <= 60 and 0.05 <= new_threshold <= 0.5:
                STREAM_FPS = new_fps
                STREAM_FRAME_AGE_THRESHOLD = new_threshold
                STREAM_DELAY = 1.0 / STREAM_FPS
                flash('Streaming settings updated successfully!', 'success')
            else:
                flash('Invalid settings. FPS must be 10-60, threshold must be 0.05-0.5', 'error')
        except ValueError:
            flash('Invalid input values', 'error')
    
    return render_template('admin_streaming_settings.html', 
                         stream_fps=STREAM_FPS, 
                         frame_age_threshold=STREAM_FRAME_AGE_THRESHOLD)

@app.route('/admin/holidays', methods=['GET', 'POST'])
@login_required
def admin_holidays():
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()

        # Create holidays table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                name TEXT
            )
        ''')

        if request.method == 'POST':
            date_str = request.form.get('date', '').strip()
            name = request.form.get('name', '').strip()
            try:
                # Validate and normalize date
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
                cursor.execute('INSERT INTO holidays (date, name) VALUES (?, ?)', (dt.isoformat(), name or None))
                conn.commit()
                flash('Holiday added successfully', 'success')
            except ValueError:
                flash('Invalid date. Use YYYY-MM-DD.', 'error')

        # Fetch all holidays
        cursor.execute('SELECT id, date, name FROM holidays ORDER BY date DESC')
        holidays = [
            {'id': row[0], 'date': row[1], 'name': row[2] or ''}
            for row in cursor.fetchall()
        ]
        conn.close()
        return render_template('admin_holidays.html', holidays=holidays)

    except Exception as e:
        try:
            conn.close()
        except:
            pass
        flash(f'Error managing holidays: {e}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/holidays/delete/<int:holiday_id>', methods=['POST'])
@login_required
def delete_holiday(holiday_id: int):
    if not current_user.is_admin():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM holidays WHERE id = ?', (holiday_id,))
        conn.commit()
        conn.close()
        flash('Holiday deleted', 'success')
    except Exception as e:
        flash(f'Failed to delete holiday: {e}', 'error')
    return redirect(url_for('admin_holidays'))

# New Admin Routes for User Records Management
@app.route('/admin/get_user_records/<int:user_id>')
@login_required
def get_user_records(user_id: int):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        # Get user information
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        # Get user's attendance records
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Get all attendance records from the attendance table
        cursor.execute('''
            SELECT id, date, time_in, time_out, status 
            FROM attendance 
            WHERE user_name = ? 
            ORDER BY date DESC
        ''', (user.username,))
        
        all_records = []
        for row in cursor.fetchall():
            # Determine if this was likely a facial recognition entry or manual entry
            # Facial recognition entries typically have time_in but no time_out
            method = 'Facial Recognition' if row[2] and not row[3] else 'Manual Entry'
            timestamp = row[1] + ' ' + (row[2] or '00:00:00')
            
            all_records.append({
                'id': row[0],
                'timestamp': timestamp,
                'method': method,
                'status': row[4] or 'Present'
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'user_info': {
                'id': user.id,
                'username': user.username,
                'role': user.role
            },
            'records': all_records
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/export_user_records/<int:user_id>')
@login_required
def export_user_records(user_id: int):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        # Get user information
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        # Get user's attendance records
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Get all attendance records from the attendance table
        cursor.execute('''
            SELECT date, time_in, time_out, status
            FROM attendance 
            WHERE user_name = ?
            ORDER BY date DESC
        ''', (user.username,))
        
        records = cursor.fetchall()
        conn.close()
        
        # Create CSV content
        csv_content = "Date,Time In,Time Out,Status,Method\n"
        for record in records:
            csv_content += f"{record[0]},{record[1] or ''},{record[2] or ''},{record[3]},{record[4]}\n"
        
        # Create response with CSV headers
        response = Response(csv_content, mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=user_records_{user.username}.csv'
        return response
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/delete_record/<int:record_id>', methods=['DELETE'])
@login_required
def delete_record(record_id: int):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Delete from attendance table
        cursor.execute('DELETE FROM attendance WHERE id = ?', (record_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Record deleted successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/modify_record/<int:record_id>', methods=['POST'])
@login_required
def modify_record(record_id: int):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        data = request.get_json()
        new_date = data.get('date')
        new_time_in = data.get('time_in')
        new_time_out = data.get('time_out')
        new_status = data.get('status')
        
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Update attendance record
        cursor.execute('''
            UPDATE attendance 
            SET date = ?, time_in = ?, time_out = ?, status = ?
            WHERE id = ?
        ''', (new_date, new_time_in, new_time_out, new_status, record_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Record modified successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/add_manual_record', methods=['POST'])
@login_required
def add_manual_record():
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        date = data.get('date')
        time_in = data.get('time_in')
        time_out = data.get('time_out')
        status = data.get('status', 'present')
        
        # Get user information
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Insert new manual attendance record
        cursor.execute('''
            INSERT INTO attendance (user_name, date, time_in, time_out, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user.username, date, time_in, time_out, status))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Manual record added successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/bulk_edit_records', methods=['POST'])
@login_required
def bulk_edit_records():
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        data = request.get_json()
        record_ids = data.get('record_ids', [])
        updates = data.get('updates', {})
        
        if not record_ids:
            return jsonify({'success': False, 'message': 'No records selected'})
        
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Update multiple records
        for record_id in record_ids:
            cursor.execute('''
                UPDATE attendance 
                SET date = ?, time_in = ?, time_out = ?, status = ?
                WHERE id = ?
            ''', (updates.get('date'), updates.get('time_in'), 
                  updates.get('time_out'), updates.get('status'), record_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'{len(record_ids)} records updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/reset_user_password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id: int):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Access denied'})
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        # Reset password to default
        default_password = os.environ.get('DEFAULT_RESET_PASSWORD', 'password123')
        user.password = generate_password_hash(default_password)
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Password reset successfully for {user.username}',
            'new_password': default_password
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if not current_user.is_teacher():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get all students for the teacher dashboard
    students = User.query.filter_by(role='student').all()
    
    return render_template('teacher_dashboard.html', students=students)

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if not current_user.is_student():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get student's attendance data
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()

        # Get recent attendance records for the current student
        cursor.execute('''
            SELECT date, status, time_in, time_out 
            FROM attendance 
            WHERE user_name = ? 
            ORDER BY date DESC 
            LIMIT 10
        ''', (current_user.username,))

        recent_attendance = []
        for row in cursor.fetchall():
            recent_attendance.append({
                'date': row[0],
                'status': row[1],
                'time_in': row[2],
                'time_out': row[3]
            })

        # Compute week and month attendance percentages from real data
        week_percentage, month_percentage = calculate_student_attendance_percentages(cursor, current_user.username)

        conn.close()

    except Exception as e:
        print(f"Error getting student data: {e}")
        recent_attendance = []
        week_percentage = 0.0
        month_percentage = 0.0
    
    # Include active lab session info (if any)
    try:
        active_session = LabSession.query.filter_by(user_id=current_user.id, end_time=None).order_by(LabSession.start_time.desc()).first()
        active_info = None
        if active_session:
            pc = Computer.query.get(active_session.computer_id)
            active_info = {
                'pc_name': pc.name if pc else f"PC{active_session.computer_id}",
                'password': active_session.password,
                'start_time': active_session.start_time
            }
    except Exception:
        active_info = None

    return render_template('student_dashboard.html', 
                         recent_attendance=recent_attendance,
                         week_percentage=week_percentage,
                         month_percentage=month_percentage,
                         active_session=active_info)

@app.route('/student/change_password', methods=['GET', 'POST'])
@login_required
def student_change_password():
    if not current_user.is_student():
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Basic validations
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('change_password.html')
        if not check_password_hash(current_user.password, current_password):
            flash('Current password is incorrect', 'error')
            return render_template('change_password.html')
        if len(new_password) < 8:
            flash('New password must be at least 8 characters', 'error')
            return render_template('change_password.html')
        if new_password != confirm_password:
            flash('New password and confirmation do not match', 'error')
            return render_template('change_password.html')

        # Update password
        try:
            user = User.query.get(current_user.id)
            user.password = generate_password_hash(new_password, method='sha256')
            db.session.commit()
            flash('Password updated successfully', 'success')
            return redirect(url_for('student_dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Failed to update password: {e}', 'error')
            return render_template('change_password.html')

    return render_template('change_password.html')

def _is_present_row(status: Optional[str], time_in_value) -> bool:
    try:
        return status is not None and str(status).strip().lower() == 'present'
    except Exception:
        return False

def _to_date(d) -> date:
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except Exception:
        # Fallback: ignore parse errors by returning today's date (won't match Sunday exclusion much)
        return date.today()

def _count_non_sunday_days(start_date: date, end_date: date) -> int:
    count = 0
    cur = start_date
    while cur <= end_date:
        if cur.weekday() != 6:  # 6 = Sunday
            count += 1
        cur += timedelta(days=1)
    return count

def _get_holidays_between(cursor, start_date: date, end_date: date):
    """Return a set of holiday dates between start and end, inclusive.
    Tries DB table 'holidays' (date TEXT/DATE), and merges with app.config['HOLIDAYS'] if provided.
    """
    holidays = set()
    # Load from DB table if present
    try:
        cursor.execute("SELECT date FROM holidays WHERE date BETWEEN ? AND ?", (start_date, end_date))
        rows = cursor.fetchall()
        for (d,) in rows:
            holidays.add(_to_date(d))
    except Exception:
        pass
    # Merge from static config if provided
    try:
        custom = app.config.get('HOLIDAYS', [])
        for d in custom:
            dd = _to_date(d)
            if start_date <= dd <= end_date:
                holidays.add(dd)
    except Exception:
        pass
    return holidays

def calculate_student_attendance_percentages(cursor, username: str):
    """Return (week_percentage, month_percentage) for the given student.
    - Week: last 7 days with records
    - Month: current calendar month with records
    Percentages are computed over days that have any record for that student.
    """
    today = date.today()
    # WEEK: last 7 calendar days (denominator = 7)
    week_start = today - timedelta(days=6)
    cursor.execute('''
        SELECT date, status, time_in 
        FROM attendance 
        WHERE user_name = ? AND date BETWEEN ? AND ?
    ''', (username, week_start, today))
    rows_week = cursor.fetchall()
    present_week = {_to_date(d) for d, st, tin in rows_week if _is_present_row(st, tin)}
    holidays_week = _get_holidays_between(cursor, week_start, today)
    present_week_non_sunday = sum(1 for d in present_week if d.weekday() != 6 and d not in holidays_week)
    # Denominator excludes Sundays and holidays
    week_den = 0
    cur = week_start
    while cur <= today:
        if cur.weekday() != 6 and cur not in holidays_week:
            week_den += 1
        cur += timedelta(days=1)
    week_pct = round(100.0 * present_week_non_sunday / week_den, 1) if week_den > 0 else 0.0

    # MONTH: full current month (denominator = number of days in month)
    first_day = today.replace(day=1)
    last_day_num = calendar.monthrange(today.year, today.month)[1]
    last_day = today.replace(day=last_day_num)
    cursor.execute('''
        SELECT date, status, time_in 
        FROM attendance 
        WHERE user_name = ? AND date BETWEEN ? AND ?
    ''', (username, first_day, last_day))
    rows_month = cursor.fetchall()
    present_month = {_to_date(d) for d, st, tin in rows_month if _is_present_row(st, tin)}
    holidays_month = _get_holidays_between(cursor, first_day, last_day)
    present_month_non_sunday = sum(1 for d in present_month if d.weekday() != 6 and d not in holidays_month)
    month_den = 0
    cur = first_day
    while cur <= last_day:
        if cur.weekday() != 6 and cur not in holidays_month:
            month_den += 1
        cur += timedelta(days=1)
    month_pct = round(100.0 * present_month_non_sunday / float(month_den), 1) if month_den > 0 else 0.0
    return week_pct, month_pct

@app.route('/facial_recognition')
@login_required
def facial_recognition_page():
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    return render_template('facial_recognition.html')

@app.route('/video_feed')
@login_required
def video_feed():
    """Minimal, smooth MJPEG stream using shared OpenCV capture."""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    _ensure_basic_capture_started()

    def gen():
        boundary = b'--frame\r\n'
        headers = b'Content-Type: image/jpeg\r\n\r\n'
        while True:
            with basic_frame_lock:
                data = basic_frame
            if data:
                yield boundary
                yield headers
                yield data
                yield b'\r\n'
            time.sleep(0.03)

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/video_direct')
@login_required
def video_direct():
    """Low-latency MJPEG using a single OpenCV capture for multiple clients."""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403

    # Prefer ESP32 port 81 if desired; fallback to default STREAM_URL
    start_fast_capture(None)

    def gen():
        boundary = b'--frame\r\n'
        headers = b'Content-Type: image/jpeg\r\n\r\n'
        # simple pacing using configured stream FPS
        delay = 1.0 / max(STREAM_FPS, 1)
        while True:
            with fast_capture_lock:
                data = fast_capture_frame
            if data:
                yield boundary
                yield headers
                yield data
                yield b'\r\n'
            time.sleep(delay)

    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/basic_stream')
@login_required
def basic_stream():
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    _ensure_basic_capture_started()
    html = """
    <!DOCTYPE html>
    <html><head><meta name=viewport content="width=device-width, initial-scale=1" />
    <style>html,body{margin:0;background:#000}img{display:block;width:100vw;height:100vh;object-fit:contain;background:#000}</style>
    <title>Basic Stream</title></head>
    <body><img src="/video_feed" alt="Live" /></body></html>
    """
    return Response(html, mimetype='text/html')

@app.route('/smooth_status')
@login_required
def smooth_status():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    with fast_capture_lock:
        has_frame = fast_capture_frame is not None
        ts = fast_capture_timestamp
    return jsonify({
        'active': fast_capture_active,
        'url': fast_capture_url,
        'has_frame': has_frame,
        'age_ms': int((time.time() - ts) * 1000) if ts else None
    })

def generate_frames():
    """Generate video frames from the buffered stream for multiple users"""
    global current_frame
    print("[Streaming] generate_frames() started - serving frames to browser")
    frame_count = 0
    last_good_frame = None
    last_frame_time = time.time()
    
    while True:
        current_time = time.time()
        
        # Get the latest frame efficiently
        with frame_lock:
            if current_frame is not None and current_frame.size > 0 and frame_timestamp > 0:
                frame_age = current_time - frame_timestamp
                
                # Use frame if it's fresh enough, otherwise use cached frame
                if frame_age <= STREAM_FRAME_AGE_THRESHOLD:
                    frame = current_frame
                    last_good_frame = frame.copy() if frame is not None else None
                    frame_count += 1
                    
                    # Minimal logging for performance
                    if frame_count % 1000 == 0:
                        print(f"[Streaming] Served {frame_count} frames (age: {frame_age:.3f}s)")
                else:
                    # Use cached frame to prevent flickering
                    if last_good_frame is not None:
                        frame = last_good_frame
                        if frame_count % 500 == 0:
                            print(f"[Streaming] Using cached frame (age: {frame_age:.3f}s)")
                    else:
                        # Create minimal placeholder
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        cv2.putText(frame, "Initializing stream...", (50, 240), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            else:
                # Use cached frame while waiting
                if last_good_frame is not None:
                    frame = last_good_frame
                else:
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, "Waiting for ESP32-CAM...", (50, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Strict frame rate limiting to prevent speed up/down
        time_since_last_frame = current_time - last_frame_time
        if time_since_last_frame < STREAM_DELAY:
            time.sleep(STREAM_DELAY - time_since_last_frame)
        
        # Update last frame time
        last_frame_time = time.time()
        
        # Encode and yield frame
        try:
            if frame is not None and frame.size > 0:
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    frame_data = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        except Exception as e:
            if frame_count % 1000 == 0:  # Log errors less frequently
                print(f"[Streaming] Frame encoding error: {e}")

@app.route('/mark_attendance')
@login_required
def mark_attendance_page():
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get all students for manual attendance
    students = User.query.filter_by(role='student').all()
    
    return render_template('mark_attendance.html', students=students)

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        username = data.get('username')
        status = data.get('status', 'present')
        
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        today = date.today()
        current_time = datetime.now()
        
        # First, let's check the table schema to make sure we have the right columns
        cursor.execute("PRAGMA table_info(attendance)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"[Debug] Attendance table columns: {columns}")
        
        # Check if attendance already marked today
        cursor.execute('''
            SELECT id FROM attendance 
            WHERE user_name = ? AND date = ?
        ''', (username, today))
        
        existing = cursor.fetchone()
        
        if existing:
            # Update existing attendance
            if 'status' in columns:
                cursor.execute('''
                    UPDATE attendance 
                    SET status = ?, time_out = ?
                    WHERE user_name = ? AND date = ?
                ''', (status, current_time, username, today))
            else:
                # Fallback if status column doesn't exist
                cursor.execute('''
                    UPDATE attendance 
                    SET time_out = ?
                    WHERE user_name = ? AND date = ?
                ''', (current_time, username, today))
            message = f'Attendance updated for {username} - {status}'
        else:
            # Mark new attendance
            if 'status' in columns:
                cursor.execute('''
                    INSERT INTO attendance (user_name, date, time_in, status, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, today, current_time, status, current_time))
            else:
                # Fallback if status column doesn't exist
                cursor.execute('''
                    INSERT INTO attendance (user_name, date, time_in, timestamp)
                    VALUES (?, ?, ?, ?)
                ''', (username, today, current_time, current_time))
            message = f'Attendance marked for {username} - {status}'
        
        conn.commit()
        conn.close()
        
        print(f"[Manual Attendance] {message}")
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        print(f"[Manual Attendance Error] {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_attendance_data')
@login_required
def get_attendance_data():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        
        # Get all attendance records
        cursor.execute('''
            SELECT user_name, date, time_in, time_out, status, timestamp
            FROM attendance 
            ORDER BY date DESC, timestamp DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        attendance_data = []
        for row in results:
            attendance_data.append({
                'user_name': row[0],
                'date': row[1],
                'time_in': row[2],
                'time_out': row[3],
                'status': row[4],
                'timestamp': row[5]
            })
        
        return jsonify({'attendance_data': attendance_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check_new_attendance')
@login_required
def check_new_attendance():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        last_check = request.args.get('last_check')
        
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        today = date.today()
        
        if last_check:
            # Get attendance records newer than last check, keeping only the latest record per user
            cursor.execute('''
                SELECT user_name, MAX(timestamp) as timestamp FROM attendance 
                WHERE date = ? AND timestamp > ?
                GROUP BY user_name
                ORDER BY timestamp DESC
            ''', (today, last_check))
        else:
            # Get all today's attendance, keeping only the latest record per user
            cursor.execute('''
                SELECT user_name, MAX(timestamp) as timestamp FROM attendance 
                WHERE date = ? 
                GROUP BY user_name
                ORDER BY timestamp DESC
            ''', (today,))
        
        results = cursor.fetchall()
        conn.close()
        
        new_attendance_list = []
        for row in results:
            new_attendance_list.append({
                'user_name': row[0],
                'timestamp': row[1]
            })
        
        return jsonify({
            'new_attendance': new_attendance_list,
            'has_new_records': len(new_attendance_list) > 0,
            'current_time': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_today_attendance')
@login_required
def get_today_attendance():
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        conn = sqlite3.connect('./instance/User.db')
        cursor = conn.cursor()
        today = date.today()
        
        # Get today's attendance from facial recognition, keeping only the latest record per user
        cursor.execute('''
            SELECT user_name, MAX(timestamp) as timestamp FROM attendance 
            WHERE date = ? 
            GROUP BY user_name
            ORDER BY timestamp DESC
        ''', (today,))
        
        results = cursor.fetchall()
        conn.close()
        
        attendance_list = []
        for row in results:
            attendance_list.append({
                'user_name': row[0],
                'timestamp': row[1]
            })
        
        return jsonify({'attendance_data': attendance_list})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stream_health')
@login_required
def stream_health():
    """Check streaming system health"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    global streaming_active, last_frame_time, current_frame, STREAM_FPS, STREAM_FRAME_AGE_THRESHOLD
    
    current_time = time.time()
    time_since_last_frame = current_time - last_frame_time
    frame_age = time_since_last_frame
    
    health_status = {
        'streaming_active': streaming_active,
        'last_frame_age_seconds': round(frame_age, 2),
        'current_frame_exists': current_frame is not None and current_frame.size > 0,
        'buffer_size': frame_buffer.qsize(),
        'system_time': current_time,
        'stream_fps': STREAM_FPS,
        'frame_age_threshold': STREAM_FRAME_AGE_THRESHOLD,
        'status': 'healthy' if frame_age < 5.0 else 'degraded' if frame_age < 10.0 else 'unhealthy'
    }
    
    return jsonify(health_status)

@app.route('/debug_frame')
@login_required
def debug_frame():
    """Debug: Get current frame info"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    global current_frame, frame_buffer, frame_timestamp
    
    current_time = time.time()
    frame_age = current_time - frame_timestamp if frame_timestamp > 0 else 0
    
    frame_info = {
        'current_frame_exists': current_frame is not None,
        'current_frame_size': current_frame.size if current_frame is not None else 0,
        'current_frame_shape': str(current_frame.shape) if current_frame is not None else 'None',
        'frame_age_seconds': round(frame_age, 3),
        'frame_fresh': frame_age < 0.1,  # Updated threshold to match generate_frames
        'buffer_size': frame_buffer.qsize(),
        'streaming_active': streaming_active,
        'current_time': current_time,
        'frame_timestamp': frame_timestamp,
        'status': 'Ready' if frame_age < 0.1 else 'Stale' if frame_age < 0.2 else 'Too Old'
    }
    
    return jsonify(frame_info)

@app.route('/test_esp32_connection')
@login_required
def test_esp32_connection():
    """Test ESP32-CAM connectivity and quality settings"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Test both port 80 and port 81
        test_results = {}
        
        # Test main page on port 80
        try:
            main_response = requests.get(f"http://{ESP32_IP}/", timeout=5)
            test_results['main_page_port80'] = {
                'url': f"http://{ESP32_IP}/",
                'status': main_response.status_code,
                'success': main_response.status_code == 200
            }
        except Exception as e:
            test_results['main_page_port80'] = {
                'url': f"http://{ESP32_IP}/",
                'status': 'error',
                'success': False,
                'error': str(e)
            }
        
        # Test stream on port 80
        try:
            stream_response = requests.get(f"http://{ESP32_IP}/stream", timeout=5)
            test_results['stream_port80'] = {
                'url': f"http://{ESP32_IP}/stream",
                'status': stream_response.status_code,
                'success': stream_response.status_code == 200
            }
        except Exception as e:
            test_results['stream_port80'] = {
                'url': f"http://{ESP32_IP}/stream",
                'status': 'error',
                'success': False,
                'error': str(e)
            }
        
        # Test stream on port 81
        try:
            stream_response_81 = requests.get(f"http://{ESP32_IP}:81/stream", timeout=5)
            test_results['stream_port81'] = {
                'url': f"http://{ESP32_IP}:81/stream",
                'status': stream_response_81.status_code,
                'success': stream_response_81.status_code == 200
            }
        except Exception as e:
            test_results['stream_port81'] = {
                'url': f"http://{ESP32_IP}:81/stream",
                'status': 'error',
                'success': False,
                'error': str(e)
            }
        
        # Test alternative endpoints
        alt_endpoints = [
            f"http://{ESP32_IP}/cam-hi.jpg",
            f"http://{ESP32_IP}/cam-lo.jpg",
            f"http://{ESP32_IP}:81/cam-hi.jpg",
            f"http://{ESP32_IP}:81/cam-lo.jpg"
        ]
        
        for i, url in enumerate(alt_endpoints):
            try:
                resp = requests.get(url, timeout=5)
                test_results[f'alt_endpoint_{i+1}'] = {
                    'url': url,
                    'status': resp.status_code,
                    'success': resp.status_code == 200
                }
            except Exception as e:
                test_results[f'alt_endpoint_{i+1}'] = {
                    'url': url,
                    'status': 'error',
                    'success': False,
                    'error': str(e)
                }
        
        connection_info = {
            'esp32_ip': ESP32_IP,
            'current_stream_url': STREAM_URL,
            'test_results': test_results,
            'recommendation': get_connection_recommendation(test_results),
            'timestamp': time.time()
        }
        
        return jsonify(connection_info)
        
    except Exception as e:
        return jsonify({'error': f'Connection test failed: {str(e)}'}), 500

def get_connection_recommendation(test_results):
    """Get connection recommendation based on test results"""
    working_urls = []
    
    for key, result in test_results.items():
        if result.get('success', False):
            working_urls.append(result['url'])
    
    if not working_urls:
        return "No working endpoints found. Check ESP32-CAM power and WiFi connection."
    
    # Prioritize stream endpoints
    stream_urls = [url for url in working_urls if 'stream' in url]
    if stream_urls:
        return f"Use stream endpoint: {stream_urls[0]}"
    
    # Fallback to image endpoints
    image_urls = [url for url in working_urls if any(x in url for x in ['cam-hi.jpg', 'cam-lo.jpg'])]
    if image_urls:
        return f"Use image endpoint: {image_urls[0]} (will need to modify code for single images)"
    
    return f"Use working endpoint: {working_urls[0]}"

@app.route('/get_recognition_status')
@login_required
def get_recognition_status():
    """Get current recognition status"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        # Get current recognition info using ESP32-CAM variables
        current_person = display_name
        total_faces = len(label_map) if label_map else 0
        
        return jsonify({
            'current_person': current_person,
            'total_faces_trained': total_faces,
            'status': 'active'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_attendance_data/<username>')
@login_required
def get_attendance_data_by_username(username):
    """Get attendance data for a user from facial recognition system"""
    if not (current_user.is_admin() or current_user.is_teacher() or 
            (current_user.is_student() and current_user.username == username)):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        attendance_data = get_facial_recognition_attendance(username)
        return jsonify({'attendance_data': attendance_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- ADMIN: Add initial admin user using shell ----------
# from app import db, User
# from werkzeug.security import generate_password_hash
# db.create_all()
# admin = User(username='admin', email='admin@example.com', password=generate_password_hash('admin123', method='sha256'), role='admin')
# db.session.add(admin)
# db.session.commit()

# ---------- RUN ----------
if __name__ == '__main__':
    try:
        with app.app_context():
            print("[System] Initializing UniSync Card Smart Campus Automation...")
            try:
                db.create_all()
                print("[System] Database initialized successfully")
                
                # Create attendance table if it doesn't exist
                try:
                    conn = sqlite3.connect(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
                    cursor = conn.cursor()
                    
                    # Check if table exists and has correct schema
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attendance'")
                    table_exists = cursor.fetchone()
                    
                    if table_exists:
                        # Check if required columns exist
                        cursor.execute("PRAGMA table_info(attendance)")
                        columns = [column[1] for column in cursor.fetchall()]
                        print(f"[System] Existing attendance table columns: {columns}")
                        
                        # Add missing columns if they don't exist
                        if 'time_in' not in columns:
                            cursor.execute('ALTER TABLE attendance ADD COLUMN time_in DATETIME')
                            print("[System] Added time_in column")
                        if 'time_out' not in columns:
                            cursor.execute('ALTER TABLE attendance ADD COLUMN time_out DATETIME')
                            print("[System] Added time_out column")
                        if 'status' not in columns:
                            cursor.execute('ALTER TABLE attendance ADD COLUMN status VARCHAR(20) DEFAULT "present"')
                            print("[System] Added status column")
                        if 'timestamp' not in columns:
                            cursor.execute('ALTER TABLE attendance ADD COLUMN timestamp DATETIME DEFAULT CURRENT_TIMESTAMP')
                            print("[System] Added timestamp column")
                    else:
                        # Create new table with correct schema
                        cursor.execute('''
                            CREATE TABLE attendance (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_name VARCHAR(150) NOT NULL,
                                date DATE NOT NULL,
                                time_in DATETIME,
                                time_out DATETIME,
                                status VARCHAR(20) DEFAULT 'present',
                                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                            )
                        ''')
                        print("[System] Created new attendance table with correct schema")
                    
                    conn.commit()
                    print("[System] Attendance table schema verified successfully")
                except Exception as e:
                    print(f"[System] Attendance table creation failed: {e}")
                finally:
                    if conn:
                        conn.close()
                        
            except Exception as e:
                print(f"[System] Database initialization failed: {e}")
                print("[System] Continuing without database...")
            
            try:
                init_serial()
                print("[System] Serial connection initialized")
            except Exception as e:
                print(f"[System] Serial initialization failed: {e}")
            
            try:
                print("[System] Auto-training facial recognition model...")
                if prepare_training_data(DATASET_DIR):
                    print(f"[System] Facial recognition ready! Trained {len(label_map)} people")
                else:
                    print("[System] No training data found. Please upload images first.")
                print("[System] Facial recognition system is now active and monitoring!")
            except Exception as e:
                print(f"[System] Facial recognition initialization failed: {e}")
            
            # Do not start legacy background streaming; minimal capture will start on-demand
            try:
                # Initialize lab computers if missing
                existing = Computer.query.count()
                if existing == 0:
                    for i in range(1, 11):
                        db.session.add(Computer(name=f"PC{i}"))
                    db.session.commit()
                    print("[System] Initialized 10 lab computers (PC1..PC10)")
                else:
                    print(f"[System] Lab computers present: {existing}")
            except Exception as e:
                print(f"[System] Failed to init lab computers: {e}")

            try:
                start_serial_listener()
                print("[System] Serial listener started")
            except Exception as e:
                print(f"[System] Serial listener failed to start: {e}")

        # Run Flask app with host='0.0.0.0' to allow external connections
        app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
    except KeyboardInterrupt:
        print("\n[System] Shutting down...")
        stop_streaming_thread()
        if ser is not None and ser.is_open:
            ser.close()
            print("[Serial] Arduino serial connection closed.")
        print("[System] Shutdown complete.")
    except Exception as e:
        print(f"[System] Critical error: {e}")
        print("[System] Shutting down...")
