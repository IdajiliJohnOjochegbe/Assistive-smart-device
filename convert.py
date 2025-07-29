from ultralytics import YOLO

# Load your model
model = YOLO("/home/pi/my_project/venv/yolov5nu.pt")

# Export to TFLite (non-quantized or default quantization)
model.export(format="tflite", int8=False)
