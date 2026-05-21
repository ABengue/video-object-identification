import os
from pathlib import Path

# Base workspace directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Application Directory
APP_DIR = BASE_DIR / "app"

# Data Storage Directories
STATIC_DIR = APP_DIR / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
TASK_DIR = STATIC_DIR / "tasks"

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TASK_DIR.mkdir(parents=True, exist_ok=True)

# Database Configuration
DATABASE_URL = "sqlite:///./app/tasks.db"

# Core Pipeline Parameters (Hyperparameters for algorithms)
# 1. Motion Classification constants
VELOCITY_THRESHOLD = 6.0       # Min pixel/frame displacement to classify an object as moving
VELOCITY_WINDOW = 5            # Sliding window size in frames for velocity smoothing
MOTION_SMOOTHING_LEN = 5       # Minimum frames to form a continuous state (majority filter)

# 2. Human & Interaction Detection constants
POSE_CONF_THRESHOLD = 0.5      # Confidence threshold for human joint keypoints (wrists)
DETECTION_CONF_THRESHOLD = 0.3 # YOLO detection score minimum
WRIST_PROXIMITY_THRESHOLD = 70.0 # Max pixel distance from wrist to box border to count as interaction
INTERACTION_GAP_BRIDGE = 10    # Number of frames allowed to bridge brief wrist-tracking dropouts

# 3. Stable Object & Class Filtering (Noise Reduction)
MIN_TRACK_FRAMES = 8          # Require an object to be tracked for at least 8 frames to display
CUSTOM_CLASSES = ["spectrophotometer", "cable", "port"]
EXCLUDE_CLASSES = set()

# Standard YOLO models
DETECTION_MODEL_NAME = "yolov8s-worldv2.pt"
POSE_MODEL_NAME = "yolov8n-pose.pt"
