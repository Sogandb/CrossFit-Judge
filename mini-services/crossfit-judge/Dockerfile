# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# CrossFit Judge — ENGINE image (FastAPI + MediaPipe + ffmpeg)
# Build context: mini-services/crossfit-judge
# ---------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    JUDGE_STATE_DIR=/state JUDGE_PORT=8001

# ffmpeg/ffprobe : decoding, validation, review-video encoding
# libgl1/libegl1/libgles2/libglib2.0-0 : MediaPipe/OpenCV runtime
# fonts-dejavu-core : clock/rep text drawn on the review video
# curl : container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgl1 libegl1 libgles2 libglib2.0-0 fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --system --uid 10001 --create-home judge \
    && mkdir -p /state && chown -R judge:judge /state /app
USER judge
VOLUME ["/state"]
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8001/api/health | grep -q '"deps_ok":true' || exit 1

# ONE uvicorn worker on purpose: the job queue + SQLite live in-process.
# Parallel analyses are controlled by JUDGE_WORKERS (threads), not by processes.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--log-level", "info"]
