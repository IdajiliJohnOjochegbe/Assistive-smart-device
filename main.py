import cv2
from ultralytics import YOLO
import RPi.GPIO as GPIO
import time
import os
import subprocess
import threading

# === GPIO Setup for Ultrasonic Sensor ===
TRIG = 4
ECHO = 23

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

# === Helper Functions ===

def measure_distance():
    GPIO.output(TRIG, False)
    time.sleep(0.05)

    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    pulse_start = time.time()
    timeout = pulse_start + 0.04

    while GPIO.input(ECHO) == 0 and time.time() < timeout:
        pulse_start = time.time()

    pulse_end = pulse_start
    while GPIO.input(ECHO) == 1 and time.time() < timeout:
        pulse_end = time.time()
    try:
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        return round(distance, 2)
    except Exception as e:
        print("Distance measurement error:", e)
        return -1

def speak(text):
    print(f"Speaking: {text}")
    safe_text = ''.join(c for c in text if c.isalnum() or c.isspace())
    subprocess.run(['espeak', safe_text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def beep(pattern='slow'):
    beep_path = '/home/pi/my_project/venv/censor-beep-1-372459.wav'
    if not os.path.exists(beep_path):
        print("Beep file not found.")
        return

    if pattern == 'slow':
        os.system(f'aplay {beep_path}')
        time.sleep(0.5)
    elif pattern == 'very_fast':
        for _ in range(6):
            os.system(f'aplay {beep_path}')
            time.sleep(0.05)

# === YOLO Model Setup ===
model_path = '/home/pi/my_project/venv/yolov5nu.pt'
model = YOLO(model_path)

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

# === Thread Control ===
speech_lock = threading.Lock()
running = True

# === Beep Thread: Runs separately for distances < 30cm ===
def beep_thread():
    while running:
        distance = measure_distance()
        if distance != -1 and distance <= 30:
            if not speech_lock.locked():
                with speech_lock:
                    beep('very_fast')
        time.sleep(0.2)

# === Object Detection + Distance Speaking Thread ===
def announce_thread():
    last_announcement_time = 0
    min_interval = 2  # seconds

    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        results = model(frame)
        annotated_frame = results[0].plot()
        boxes = results[0].boxes

        distance = measure_distance()
        object_labels = []
        object_detected = False

        if len(boxes) > 0:
            confs = boxes.conf.cpu().numpy()
            sorted_indices = confs.argsort()[::-1][:3]

            for idx in sorted_indices:
                conf = float(confs[idx])
                if conf < 0.5:
                    continue
                cls_id = int(boxes.cls[idx])
                label = model.names[cls_id]
                if label not in object_labels:
                    object_labels.append(label)
                    object_detected = True

        current_time = time.time()
        if current_time - last_announcement_time >= min_interval:
            if object_detected:
                with speech_lock:
                    speak("I see " + ", ".join(object_labels))
                    if 30 < distance <= 100:
                        speak(f"It is {int(distance)} centimeters away")
            elif 30 < distance <= 100:
                with speech_lock:
                    speak(f"The object is {int(distance)} centimeters away")

            last_announcement_time = current_time

        cv2.imshow("Smart Vision", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# === Start Threads ===
beep_t = threading.Thread(target=beep_thread)
announce_t = threading.Thread(target=announce_thread)

beep_t.daemon = True
announce_t.daemon = True

beep_t.start()
announce_t.start()

# === Startup Announcement ===
print("Starting smart vision system. Press 'q' to quit.")
speak("Smart vision system started")

# === Wait for User Exit ===
try:
    while running:
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Interrupted by user.")
finally:
    running = False
    beep_t.join(timeout=1)
    announce_t.join(timeout=1)
    GPIO.cleanup()
    speak("Smart vision system stopped")
    print("Resources released.")
