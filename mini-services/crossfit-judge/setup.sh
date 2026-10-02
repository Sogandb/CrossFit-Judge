#!/usr/bin/env bash
# CrossFit Judge V2 engine — environment setup
# Requires: python3.10+, ffmpeg, ffprobe (apt: sudo apt install -y ffmpeg libgl1)
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt
mkdir -p data/models data/uploads data/wods
python - <<'PY'
from config.settings import MODELS_DIR
import sys
sys.path.insert(0, ".")
try:
    from core.pose_detector import ensure_model
    print("model:", ensure_model())
except Exception as e:
    print("model download failed (offline?):", e)
PY
echo "setup done — start with: bun run dev   (or: source venv/bin/activate && python -m uvicorn main:app --port 8001)"
