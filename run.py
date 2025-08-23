# face_stream_serial.py
import os
import cv2
import numpy as np
import requests
import time
import serial
from collections import deque, Counter
import sqlite3
from datetime import datetime, date

# --- CONFIGURATION ---
ESP32_IP = "192.168.29.115"
STREAM_URL = f"http://{ESP32_IP}:81/stream"
DATASET_DIR = "dataset"
FACE_SIZE = (100, 100)
BUFFER_DURATION_SEC = 1.0
CONFIDENCE_THRESHOLD = 120

SERIAL_PORT = 'COM4'  # <- Make sure this is the Arduino port
SERIAL_BAUD = 9600

# --- SQLite CONFIGURATION ---
DB_PATH = "instance/User.db"  # Using the same database as the Flask app

# --- SQLite Connection ---
def init_database():
    """Initialize SQLite database and create tables if they don't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create attendance table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                date DATE NOT NULL,
                timestamp DATETIME NOT NULL,
                UNIQUE(user_name, date)
            )
        ''')
        
        conn.commit()
        print('[SQLite] Database initialized successfully.')
        return conn, cursor
    except Exception as e:
        print(f'[SQLite Error] {e}')
        return None, None

db_conn, db_cursor = init_database()

# --- Initialize Serial ---
ser = None
try:
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
    time.sleep(2)
    ser.flush()
    print("[Serial] Arduino serial opened.")
except Exception as e:
    print(f"[Serial Error] {e}")

# --- Training ---
def prepare_training_data(data_folder_path, face_size=FACE_SIZE):
    faces, labels, label_map = [], [], {}
    current_label = 0
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    for name in os.listdir(data_folder_path):
        person_path = os.path.join(data_folder_path, name)
        if not os.path.isdir(person_path): continue
        label_map[current_label] = name
        for img_name in os.listdir(person_path):
            img_path = os.path.join(person_path, img_name)
            img = cv2.imread(img_path)
            if img is None: continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces_rects = face_cascade.detectMultiScale(gray, 1.2, 5)
            for (x, y, w, h) in faces_rects:
                if w*h < 1200: continue
                roi = gray[y:y+h, x:x+w]
                roi = cv2.resize(roi, face_size)
                faces.append(roi)
                labels.append(current_label)
                break
        current_label += 1
    return faces, labels, label_map

print("Preparing training data...")
faces, labels, label_map = prepare_training_data(DATASET_DIR)
print(f"  [INFO] {len(faces)} faces, {len(label_map)} people loaded.")

face_recognizer = cv2.face.LBPHFaceRecognizer_create()
face_recognizer.train(faces, np.array(labels))
print("  [INFO] Model trained.")

# --- Streaming ---
try:
    stream = requests.get(STREAM_URL, stream=True, timeout=10)
except Exception as e:
    print(f"Stream error: {e}")
    exit(1)

bytes_buffer = b''
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
pred_buffer = deque()
time_buffer = deque()
display_name = "Waiting..."
prev_name_serial = ""

print("Starting stream...")

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
            try:
                label_id, confidence = face_recognizer.predict(roi_resized)
            except:
                label_id, confidence = -1, 999
            name = label_map.get(label_id, "Unknown")
            print(f"[Debug] Detected: {name} (confidence: {confidence:.2f})")
            pred_this_frame = name if confidence < CONFIDENCE_THRESHOLD else "Unknown"
            cv2.rectangle(img, (x, y), (x+w, y+h), (0,255,0), 2)
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

        # --- Attendance Logging ---
        if db_conn and display_name != 'Unknown':
            today = date.today()
            try:
                db_cursor.execute('''SELECT COUNT(*) FROM attendance WHERE user_name=? AND date=?''', (display_name, today))
                already_logged = db_cursor.fetchone()[0]
                if already_logged == 0:
                    db_cursor.execute('''INSERT INTO attendance (user_name, date, timestamp) VALUES (?, ?, ?)''', (display_name, today, datetime.now()))
                    db_conn.commit()
                    print(f"[Attendance] Logged for {display_name} on {today}")
            except Exception as e:
                print(f"[SQLite Attendance Error] {e}")

        # Serial sending
        if ser is not None:
            try:
                message = (display_name.strip() or "Unknown") + "\n"
                if message != prev_name_serial:
                    ser.write(message.encode('utf-8'))
                    ser.flush()
                    print(f"[Serial] Sent to Arduino: {message.strip()}")
                    prev_name_serial = message
            except Exception as e:
                print(f"[Serial Error] {e}")
                ser = None

        cv2.putText(img, display_name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (0, 255, 0) if display_name != "Unknown" else (0, 0, 255), 2)
        cv2.imshow("Face Recognition", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
if ser:
    ser.write(("Stopped\n").encode('utf-8'))
    ser.close()

# Close database connection
if db_conn:
    db_conn.close()
