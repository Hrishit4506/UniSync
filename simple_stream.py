from flask import Flask, Response, render_template_string
import cv2
import threading

# ESP32 stream URL
ESP32_STREAM_URL = "http://192.168.29.115:81/stream"

app = Flask(__name__)

# Shared frame buffer
frame = None


def capture_frames():
    global frame
    cap = cv2.VideoCapture(ESP32_STREAM_URL)
    while True:
        success, img = cap.read()
        if not success:
            continue
        _, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()


# Start background thread
thread = threading.Thread(target=capture_frames, daemon=True)
thread.start()


# HTML page shown at /
STREAM_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>ESP32-CAM Stream</title>
    <style>
        body { margin:0; padding:0; background:#000; }
        img { display:block; width:100%; height:auto; }
    </style>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
  </head>
<body>
    <img src="/video_feed" alt="ESP32-CAM Stream">
</body>
</html>
"""


def generate_frames():
    global frame
    while True:
        if frame is None:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/')
def index():
    return render_template_string(STREAM_PAGE)


@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


if __name__ == "__main__":
    # host="0.0.0.0" makes it visible on your network (and via ngrok)
    app.run(host="0.0.0.0", port=8000, debug=True)


