#!/bin/bash

# Exit on any error
set -e

echo "=== Object Identification & Interaction Tracking Setup ==="

# Step 1: Verify Python installation
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed. Please install Python 3.9+."
    exit 1
fi

# Step 2: Create Python Virtual Environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment '.venv'..."
    python3 -m venv .venv
else
    echo "Virtual environment '.venv' already exists."
fi

# Step 3: Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Step 4: Upgrade pip & install dependencies
echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing project dependencies from requirements.txt..."
pip install -r requirements.txt

# Step 5: Ensure directories exist
echo "Setting up application folders..."
mkdir -p app/static/uploads
mkdir -p app/static/tasks
mkdir -p app/templates
mkdir -p app/static/css
mkdir -p app/static/js

# Step 6: Pre-cache YOLO weights to avoid download delays on first run
echo "Pre-downloading YOLO models (yolov8s-worldv2.pt, yolov8n-pose.pt)..."
python3 -c "
from ultralytics import YOLO
print('Loading yolov8s-worldv2 (open-vocabulary object detector)...')
YOLO('yolov8s-worldv2.pt')
print('Loading yolov8n-pose (human joint estimator)...')
YOLO('yolov8n-pose.pt')
print('Models successfully cached!')
"

echo "=== Setup Complete! ==="
echo "Starting uvicorn server on http://127.0.0.1:8000 ..."
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
