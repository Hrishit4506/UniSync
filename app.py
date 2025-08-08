from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os
import sqlite3
import json
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import requests
import time
import serial
from collections import deque, Counter

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///User.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
app.config['UPLOAD_FOLDER'] = 'dataset'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# ESP32-CAM Configuration (from run.py)
ESP32_IP = "192.168.29.115"
STREAM_URL = f"http://{ESP32_IP}:81/stream"
DATASET_DIR = "dataset"
FACE_SIZE = (100, 100)
BUFFER_DURATION_SEC = 1.0
CONFIDENCE_THRESHOLD = 120  # Lowered from 120 to make recognition more lenient

SERIAL_PORT = 'COM4'  # Arduino port
SERIAL_BAUD = 9600

# Global variables for face recognition (from run.py)
face_recognizer = None
label_map = {}
pred_buffer = deque()
time_buffer = deque()
display_name = "Waiting..."
prev_name_serial = ""
ser = None

db = SQLAlchemy(app)

# Temporary or persistent storage for camera stream URL
esp_stream_url = None


# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
        print(f"Error creating dataset folder for {username}: {e}")
        return False

def get_user_images(username):
    """Get list of training images for a user"""
    try:
        user_folder = os.path.join('dataset', username)
        if not os.path.exists(user_folder):
            return []
        
        images = []
        for filename in os.listdir(user_folder):
            if allowed_file(filename):
                images.append(filename)
        return images
    except Exception as e:
        print(f"Error getting images for {username}: {e}")
        return []

# ESP32-CAM Functions (from run.py)
def init_serial():
    """Initialize serial connection to Arduino"""
    global ser
    print(f"[Serial Debug] Attempting to initialize serial on {SERIAL_PORT} at {SERIAL_BAUD} baud")
    
    # If serial is already connected, don't try to reconnect
    if ser is not None and ser.is_open:
        print("[Serial Debug] Serial connection already exists and is open")
        return True
    
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        time.sleep(2)
        ser.flush()
        print("[Serial] Arduino serial opened successfully.")
        return True
    except Exception as e:
        print(f"[Serial Error] {e}")
        print(f"[Serial Debug] Failed to initialize serial connection")
        return False

def prepare_training_data(data_folder_path, face_size=FACE_SIZE):
    """Prepare training data from dataset folder (from run.py)"""
    global face_recognizer, label_map
    faces, labels = [], []
    current_label = 0
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    
    for name in os.listdir(data_folder_path):
        person_path = os.path.join(data_folder_path, name)
        if not os.path.isdir(person_path): 
            continue
        label_map[current_label] = name
        for img_name in os.listdir(person_path):
            img_path = os.path.join(person_path, img_name)
            img = cv2.imread(img_path)
            if img is None: 
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces_rects = face_cascade.detectMultiScale(gray, 1.2, 5)
            for (x, y, w, h) in faces_rects:
                if w*h < 1200: 
                    continue
                roi = gray[y:y+h, x:x+w]
                roi = cv2.resize(roi, face_size)
                faces.append(roi)
                labels.append(current_label)
                break
        current_label += 1
    
    if faces:
        face_recognizer = cv2.face.LBPHFaceRecognizer_create()
        face_recognizer.train(faces, np.array(labels))
        print(f"[Face Recognition] Trained {len(faces)} faces for {len(label_map)} people")
        return True
    else:
        print("[Face Recognition] No valid faces found for training")
        return False

def mark_attendance_for_recognized_person(name):
    """Mark attendance for recognized person (from run.py)"""
    if name == "Unknown":
        return
    
    try:
        conn = sqlite3.connect('instance/User.db')
        cursor = conn.cursor()
        today = date.today()
        
        # Create attendance table if it doesn't exist
        cursor.execute('''CREATE TABLE IF NOT EXISTS attendance 
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_name TEXT NOT NULL,
                          date DATE NOT NULL,
                          timestamp DATETIME NOT NULL)''')
        
        # Check if already logged today
        cursor.execute('''SELECT COUNT(*) FROM attendance WHERE user_name=? AND date=?''', (name, today))
        already_logged = cursor.fetchone()[0]
        
        if already_logged == 0:
            cursor.execute('''INSERT INTO attendance (user_name, date, timestamp) VALUES (?, ?, ?)''', 
                         (name, today, datetime.now()))
            conn.commit()
            print(f"[Attendance] Logged for {name} on {today}")
        
        conn.close()
    except Exception as e:
        print(f"[SQLite Attendance Error] {e}")

def send_to_arduino(name):
    """Send recognized name to Arduino via serial (from run.py)"""
    global ser, prev_name_serial
    print(f"[Serial Debug] Attempting to send '{name}' to Arduino")
    print(f"[Serial Debug] Serial connection status: {ser is not None}")
    
    if ser is not None:
        try:
            message = (name.strip() or "Unknown") + "\n"
            if message != prev_name_serial:
                ser.write(message.encode('utf-8'))
                ser.flush()
                print(f"[Serial] Sent to Arduino: {message.strip()}")
                prev_name_serial = message
            else:
                print(f"[Serial Debug] Message '{message.strip()}' already sent, skipping")
        except Exception as e:
            print(f"[Serial Error] {e}")
            ser = None
    else:
        print("[Serial Debug] Serial connection is None - trying to reinitialize...")
        init_serial()

def get_facial_recognition_attendance(username):
    """Get attendance data from facial recognition system (from run.py)"""
    try:
        conn = sqlite3.connect('instance/User.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date, timestamp FROM attendance 
            WHERE user_name = ? 
            ORDER BY date DESC
        ''', (username,))
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"Error getting facial recognition attendance: {e}")
        return []

def get_user_attendance_data(username, start_date=None, end_date=None):
    """Get attendance data for a specific user from their table"""
    table_name = get_user_attendance_table(username)
    
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            query = f"SELECT * FROM {table_name}"
            params = []
            
            if start_date and end_date:
                query += " WHERE date BETWEEN :start_date AND :end_date"
                params = {"start_date": start_date, "end_date": end_date}
            elif start_date:
                query += " WHERE date >= :start_date"
                params = {"start_date": start_date}
            
            query += " ORDER BY date DESC"
            
            result = conn.execute(text(query), params)
            rows = []
            for row in result:
                rows.append(dict(row._mapping))
            return rows
    except Exception as e:
        print(f"Error getting attendance data for {username}: {e}")
        return []

def mark_attendance_for_user(username, date, status='present', time_in=None, time_out=None):
    """Mark attendance for a specific user in their table"""
    table_name = get_user_attendance_table(username)
    
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            
            # Check if attendance already exists for this date
            existing = conn.execute(
                text(f"SELECT id FROM {table_name} WHERE date = :date"),
                {"date": date}
            ).fetchone()
            
            if existing:
                # Update existing record
                conn.execute(text(f"""
                    UPDATE {table_name} 
                    SET status = :status, time_in = :time_in, time_out = :time_out
                    WHERE date = :date
                """), {"status": status, "time_in": time_in, "time_out": time_out, "date": date})
            else:
                # Insert new record
                conn.execute(text(f"""
                    INSERT INTO {table_name} (date, status, time_in, time_out)
                    VALUES (:date, :status, :time_in, :time_out)
                """), {"date": date, "status": status, "time_in": time_in, "time_out": time_out})
            
            conn.commit()
            return True
    except Exception as e:
        print(f"Error marking attendance for {username}: {e}")
        return False

# ---------- ROUTES ----------

@app.route('/')
@login_required
def index():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    elif current_user.is_teacher():
        return redirect(url_for('teacher_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)

@app.route('/teacher/dashboard')
@login_required
def teacher_dashboard():
    if not current_user.is_teacher():
        flash('Access denied. Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    students = User.query.filter_by(role='student').all()
    return render_template('teacher_dashboard.html', students=students)

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if not current_user.is_student():
        flash('Access denied. Student privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Get attendance statistics for the current student
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Get attendance data from user's table
    week_attendance = get_user_attendance_data(current_user.username, week_start, today)
    month_attendance = get_user_attendance_data(current_user.username, month_start, today)
    
    # Calculate statistics
    week_present = len([a for a in week_attendance if a['status'] == 'present'])
    week_total = len(week_attendance) if week_attendance else 1
    week_percentage = (week_present / week_total) * 100
    
    month_present = len([a for a in month_attendance if a['status'] == 'present'])
    month_total = len(month_attendance) if month_attendance else 1
    month_percentage = (month_present / month_total) * 100
    
    # Get recent attendance records
    recent_attendance = get_user_attendance_data(current_user.username)[:10]
    
    return render_template('student_dashboard.html', 
                         week_percentage=week_percentage,
                         month_percentage=month_percentage,
                         recent_attendance=recent_attendance)

@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'student')
        
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'error')
            return render_template('create_user.html')
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Email already registered!', 'error')
            return render_template('create_user.html')
        
        # Create new user
        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(username=username, email=email, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()
        
        # Create attendance table for the user
        create_user_attendance_table(username)
        
        # Create dataset folder for the user
        create_dataset_folder(username)
        
        flash(f'User {username} created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_user.html')

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        password = request.form.get('password')
        
        # Check if username is being changed and if it already exists
        if username != user.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Username already exists!', 'error')
                return render_template('edit_user.html', user=user)
        
        # Check if email is being changed and if it already exists
        if email != user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already registered!', 'error')
                return render_template('edit_user.html', user=user)
        
        # Update user
        user.username = username
        user.email = email
        user.role = role
        
        # Update password if provided
        if password:
            user.password = generate_password_hash(password, method='sha256')
        
        db.session.commit()
        
        flash(f'User {username} updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('edit_user.html', user=user)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Prevent deleting the last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('Cannot delete the last admin user!', 'error')
            return redirect(url_for('admin_dashboard'))
    
    username = user.username
    
    try:
        # Delete user's dataset folder
        import shutil
        import os
        dataset_folder = os.path.join(DATASET_DIR, username)
        if os.path.exists(dataset_folder):
            shutil.rmtree(dataset_folder)
            print(f"[Delete User] Removed dataset folder: {dataset_folder}")
        
        # Delete user's attendance data from all tables
        conn = sqlite3.connect('instance/User.db')
        cursor = conn.cursor()
        
        # Delete from facial recognition attendance table
        cursor.execute('DELETE FROM attendance WHERE user_name = ?', (username,))
        facial_records_deleted = cursor.rowcount
        print(f"[Delete User] Deleted {facial_records_deleted} facial recognition attendance records")
        
        # Delete from user's specific attendance table
        user_attendance_table = f'attendance_{username}'
        cursor.execute(f"DROP TABLE IF EXISTS {user_attendance_table}")
        print(f"[Delete User] Dropped attendance table: {user_attendance_table}")
        
        # Note: The attendance table only has user_name column, not username column
        # So we don't need to delete from a general attendance table
        general_records_deleted = 0
        
        conn.commit()
        conn.close()
        
        # Delete user from database
        db.session.delete(user)
        db.session.commit()
        
        # Retrain facial recognition model if needed
        if os.path.exists(DATASET_DIR) and any(os.listdir(DATASET_DIR)):
            print(f"[Delete User] Retraining facial recognition model...")
            prepare_training_data(DATASET_DIR)
        
        flash(f'User {username} and all associated data deleted successfully! (Removed {facial_records_deleted + general_records_deleted} attendance records)', 'success')
        
    except Exception as e:
        print(f"[Delete User Error] {e}")
        flash(f'Error deleting user {username}: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('admin_dashboard'))

@app.route('/teacher/mark_attendance', methods=['GET', 'POST'])
@login_required
def mark_attendance():
    if not current_user.is_teacher():
        flash('Access denied. Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Handle quick marking
        quick_students = request.form.getlist('quick_students')
        if quick_students:
            date = request.form.get('date')
            status = request.form.get('status', 'present')
            
            success_count = 0
            for student_username in quick_students:
                success = mark_attendance_for_user(student_username, date, status)
                if success:
                    success_count += 1
            
            flash(f'Attendance marked for {success_count} students on {date}', 'success')
            return redirect(url_for('mark_attendance'))
        
        # Handle single student marking
        student_username = request.form.get('student_username')
        date = request.form.get('date')
        status = request.form.get('status', 'present')
        time_in = request.form.get('time_in')
        time_out = request.form.get('time_out')
        
        # Validate student exists
        student = User.query.filter_by(username=student_username, role='student').first()
        if not student:
            flash('Student not found!', 'error')
            return redirect(url_for('mark_attendance'))
        
        # Mark attendance
        success = mark_attendance_for_user(student_username, date, status, time_in, time_out)
        
        if success:
            flash(f'Attendance marked for {student_username} on {date}', 'success')
        else:
            flash('Error marking attendance', 'error')
        
        return redirect(url_for('mark_attendance'))
    
    students = User.query.filter_by(role='student').all()
    today = datetime.now().date().isoformat()
    return render_template('mark_attendance.html', students=students, today=today)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/student/upload_images', methods=['GET', 'POST'])
@login_required
def student_upload_images():
    """Allow students to upload their training images"""
    if not current_user.is_student():
        flash('Access denied. Student privileges required.', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if 'images' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('images')
        if not files or files[0].filename == '':
            flash('No files selected', 'error')
            return redirect(request.url)
        
        uploaded_count = 0
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to avoid filename conflicts
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{name}_{timestamp}{ext}"
                
                user_folder = os.path.join(app.config['UPLOAD_FOLDER'], current_user.username)
                if not os.path.exists(user_folder):
                    os.makedirs(user_folder)
                
                file_path = os.path.join(user_folder, filename)
                file.save(file_path)
                uploaded_count += 1
        
        flash(f'Successfully uploaded {uploaded_count} images!', 'success')
        return redirect(url_for('student_upload_images'))
    
    # Get existing images
    images = get_user_images(current_user.username)
    return render_template('student_upload_images.html', images=images)

@app.route('/admin/manage_images/<username>', methods=['GET', 'POST'])
@login_required
def admin_manage_images(username):
    """Allow admins to manage training images for any user"""
    if not current_user.is_admin():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    user = User.query.filter_by(username=username).first()
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        if 'images' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('images')
        if not files or files[0].filename == '':
            flash('No files selected', 'error')
            return redirect(request.url)
        
        uploaded_count = 0
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to avoid filename conflicts
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{name}_{timestamp}{ext}"
                
                user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
                if not os.path.exists(user_folder):
                    os.makedirs(user_folder)
                
                file_path = os.path.join(user_folder, filename)
                file.save(file_path)
                uploaded_count += 1
        
        flash(f'Successfully uploaded {uploaded_count} images for {username}!', 'success')
        return redirect(url_for('admin_manage_images', username=username))
    
    # Get existing images
    images = get_user_images(username)
    return render_template('admin_manage_images.html', user=user, images=images)

@app.route('/delete_image/<username>/<filename>', methods=['POST'])
@login_required
def delete_image(username, filename):
    """Delete a training image"""
    if not (current_user.is_admin() or (current_user.is_student() and current_user.username == username)):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], username, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'Image {filename} deleted successfully!', 'success')
        else:
            flash('Image not found', 'error')
    except Exception as e:
        flash(f'Error deleting image: {e}', 'error')
    
    if current_user.is_admin():
        return redirect(url_for('admin_manage_images', username=username))
    else:
        return redirect(url_for('student_upload_images'))

@app.route('/dataset/<username>/<filename>')
@login_required
def serve_image(username, filename):
    """Serve training images"""
    if not (current_user.is_admin() or (current_user.is_student() and current_user.username == username)):
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], username, filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            flash('Image not found', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error serving image: {e}', 'error')
        return redirect(url_for('index'))

# ---------- FACIAL RECOGNITION ROUTES ----------

@app.route('/facial_recognition')
@login_required
def facial_recognition_page():
    """Main facial recognition page"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied. Admin or Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    # Initialize serial connection
    init_serial()
    
    # Auto-train the model if not already trained
    global face_recognizer
    if face_recognizer is None:
        print("[Face Recognition] Auto-training model...")
        if prepare_training_data(DATASET_DIR):
            flash('Face recognition model trained successfully!', 'success')
        else:
            flash('No training data found. Please upload images first.', 'error')
    
    return render_template('facial_recognition.html')

@app.route('/train_faces')
@login_required
def train_faces():
    """Train the facial recognition model"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied. Admin or Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Train faces using ESP32-CAM method
        success = prepare_training_data(DATASET_DIR)
        if success:
            flash('Facial recognition model trained successfully!', 'success')
        else:
            flash('No valid faces found for training. Please ensure users have uploaded images.', 'error')
    except Exception as e:
        flash(f'Error training model: {e}', 'error')
    
    return redirect(url_for('facial_recognition_page'))

@app.route('/train_user_faces/<username>')
@login_required
def train_user_faces(username):
    """Train faces for a specific user"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied. Admin or Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        # Train all faces (ESP32-CAM method trains all at once)
        success = prepare_training_data(DATASET_DIR)
        if success:
            flash(f'Faces trained successfully for {username}!', 'success')
        else:
            flash(f'No valid faces found for {username}. Please ensure they have uploaded images.', 'error')
    except Exception as e:
        flash(f'Error training faces for {username}: {e}', 'error')
    
    return redirect(url_for('admin_manage_images', username=username))

def generate_frames():
    """Generate video frames from ESP32-CAM stream for facial recognition (from run.py)"""
    global pred_buffer, time_buffer, display_name
    
    try:
        stream = requests.get(STREAM_URL, stream=True, timeout=10)
        print(f"[ESP32-CAM] Connected to stream at {STREAM_URL}")
    except Exception as e:
        print(f"[ESP32-CAM Error] {e}")
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + 
               b'<html><body><h1>ESP32-CAM Connection Error</h1><p>' + str(e).encode() + b'</p></body></html>' + 
               b'\r\n')
        return
    
    bytes_buffer = b''
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    
    for chunk in stream.iter_content(chunk_size=1024):
        bytes_buffer += chunk
        a = bytes_buffer.find(b'\xff\xd8')
        b = bytes_buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg = bytes_buffer[a:b+2]
            bytes_buffer = bytes_buffer[b+2:]
            
            if len(jpg) < 100:
                continue

            img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces_rects = face_cascade.detectMultiScale(gray, 1.1, 4)

            pred_this_frame = "Unknown"
            for (x, y, w, h) in faces_rects:
                if w * h < 1500:
                    continue
                roi = gray[y:y+h, x:x+w]
                roi_resized = cv2.resize(roi, FACE_SIZE)
                
                if face_recognizer is not None:
                    try:
                        label_id, confidence = face_recognizer.predict(roi_resized)
                        name = label_map.get(label_id, "Unknown")
                        pred_this_frame = name if confidence < CONFIDENCE_THRESHOLD else "Unknown"
                        cv2.rectangle(img, (x, y), (x+w, y+h), (0,255,0), 2)
                        # Add confidence info for debugging
                        cv2.putText(img, f"Conf: {confidence:.1f}", (x, y-10), 
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                    except Exception as e:
                        print(f"[Recognition Error] {e}")
                        pred_this_frame = "Unknown"
                else:
                    print("[Debug] Face recognizer is None - model not trained")
                break

            # Buffer prediction
            now = time.time()
            pred_buffer.append(pred_this_frame)
            time_buffer.append(now)
            while time_buffer and now - time_buffer[0] > BUFFER_DURATION_SEC:
                pred_buffer.popleft()
                time_buffer.popleft()
            
            if pred_buffer:
                most_common, count = Counter(pred_buffer).most_common(1)[0]
                if (count / len(pred_buffer) > 0.6) or display_name == "Unknown":
                    display_name = most_common

            # Mark attendance and send to Arduino
            if display_name != 'Unknown':
                mark_attendance_for_recognized_person(display_name)
                send_to_arduino(display_name)

            # Draw recognition result on frame
            cv2.putText(img, display_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                        (0, 255, 0) if display_name != "Unknown" else (0, 0, 255), 2)
            
            # Convert frame to JPEG for streaming
            ret, buffer = cv2.imencode('.jpg', img)
            if not ret:
                continue
            
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
@login_required
def video_feed():
    """Video streaming route for facial recognition"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        flash('Access denied. Admin or Teacher privileges required.', 'error')
        return redirect(url_for('index'))
    
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

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
def get_attendance_data(username):
    """Get attendance data for a user from facial recognition system"""
    if not (current_user.is_admin() or current_user.is_teacher() or 
            (current_user.is_student() and current_user.username == username)):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        attendance_data = get_facial_recognition_attendance(username)
        return jsonify({'attendance_data': attendance_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_today_attendance')
@login_required
def get_today_attendance():
    """Get today's attendance data from facial recognition system"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        conn = sqlite3.connect('instance/User.db')
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
        
        return jsonify({
            'today_attendance': attendance_list,
            'total_present': len(attendance_list),
            'date': today.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/check_new_attendance')
@login_required
def check_new_attendance():
    """Check for new attendance records since last check"""
    if not (current_user.is_admin() or current_user.is_teacher()):
        return jsonify({'error': 'Access denied'}), 403
    
    try:
        last_check = request.args.get('last_check', '')
        conn = sqlite3.connect('instance/User.db')
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

@app.route('/api/esp32/mark_attendance', methods=['POST'])
def esp32_mark_attendance():
    try:
        data = request.get_json()
        student_id = data.get('id')   # Must match the username in your DB
        name = data.get('name')       # For reference/logging
        device = data.get('device', 'esp32-cam')

        if not student_id or not name:
            return jsonify({"status": "error", "message": "Missing ID or name"}), 400

        db_path = os.path.join('instance', 'User.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Check that table exists
        table_name = f"attendance_{student_id}"
        c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not c.fetchone():
            conn.close()
            return jsonify({"status": "error", "message": f"No attendance table for {student_id}"}), 404

        now = datetime.now()
        date_today = now.date().isoformat()
        time_now = now.strftime("%H:%M:%S")

        # Prevent duplicate within 5 minutes
        c.execute(f"SELECT MAX(created_at) FROM {table_name}")
        last_time = c.fetchone()[0]
        if last_time:
            last_dt = datetime.fromisoformat(last_time)
            if (now - last_dt).seconds < 300:
                conn.close()
                return jsonify({"status": "ok", "message": "Duplicate entry ignored"})

        # Insert attendance record
        c.execute(f"""
            INSERT INTO {table_name} (date, time_in, status, created_at)
            VALUES (?, ?, ?, ?)
        """, (date_today, time_now, 'present', now.isoformat()))

        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "message": "Attendance marked for " + name})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ---------- ADMIN: Add initial admin user using shell ----------
# from app import db, User
# from werkzeug.security import generate_password_hash
# db.create_all()
# admin = User(username='admin', email='admin@example.com', password=generate_password_hash('admin123', method='sha256'), role='admin')
# db.session.add(admin)
# db.session.commit()

# ---------- RUN ----------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Auto-initialize facial recognition system on startup
        print("[System] Initializing UniSync Card Smart Campus Automation...")
        init_serial()
        print("[System] Auto-training facial recognition model...")
        if prepare_training_data(DATASET_DIR):
            print(f"[System] Facial recognition ready! Trained {len(label_map)} people")
        else:
            print("[System] No training data found. Please upload images first.")
        print("[System] Facial recognition system is now active and monitoring!")
    
    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        print("\n[System] Shutting down...")
        if ser is not None and ser.is_open:
            ser.close()
            print("[Serial] Arduino serial connection closed.")
        print("[System] Shutdown complete.")
