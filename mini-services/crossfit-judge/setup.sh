#!/bin/bash
# Setup script for CrossFit Judge — run this once before first start.
set -e

echo "========================================="
echo "  CrossFit Judge — Setup"
echo "========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Install it from https://python.org"
    exit 1
fi
echo "✓ Python: $(python3 --version)"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "ERROR: pip3 is not installed."
    exit 1
fi
echo "✓ pip: $(pip3 --version)"
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Download MediaPipe pose model
MODEL_DIR="data/models"
MODEL_FILE="$MODEL_DIR/pose_landmarker.task"
if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading MediaPipe pose model..."
    mkdir -p "$MODEL_DIR"
    curl -sL "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task" -o "$MODEL_FILE"
    echo "✓ Model downloaded"
else
    echo "✓ Model already exists"
fi
echo ""

# Create data directories
mkdir -p data/uploads data/results/_jobs data/workouts
echo "✓ Data directories created"
echo ""

echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "To start the server:"
echo "  python3 main.py"
echo ""
echo "The server runs on http://localhost:8001"
echo ""
echo "Then start the Next.js frontend (in the project root):"
echo "  bun run dev   (or: npm run dev)"
echo ""
echo "Open http://localhost:3000 in your browser."
