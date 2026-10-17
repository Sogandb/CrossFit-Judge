"""Upload ingest validation gates (ffprobe-based). Bilingual error messages —
the athlete should immediately understand what to fix (fa) while the English
UI (default) shows the parallel error_en."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.settings import (
    MAX_VIDEO_DURATION_SEC,
    MIN_VIDEO_DURATION_SEC,
)
from core.frame_source import ToolMissing, probe


@dataclass
class IngestResult:
    ok: bool
    error_fa: Optional[str] = None
    error_en: Optional[str] = None
    info: Optional[object] = None


def validate_video(path: str) -> IngestResult:
    try:
        info = probe(path)
    except ToolMissing:
        return IngestResult(
            False,
            "ابزار ffprobe/ffmpeg روی سرور نصب نیست (macOS: brew install ffmpeg — Ubuntu: apt install ffmpeg) و سپس سرویس را دوباره اجرا کنید",
            "ffprobe/ffmpeg is not installed on the server (macOS: brew install ffmpeg — Ubuntu: apt install ffmpeg), then restart the service")
    if info is None:
        return IngestResult(
            False,
            "فایل ویدیو قابل خواندن نیست (ffprobe). فرمت پشتیبانی‌شده: MP4 / MOV / WebM",
            "The video file is not readable (ffprobe). Supported formats: MP4 / MOV / WebM")
    if info.duration_sec <= 0:
        return IngestResult(
            False,
            "مدت زمان ویدیو قابل تشخیص نیست — فایل احتمالاً ناقص آپلود شده است",
            "Video duration could not be determined — the upload may be incomplete")
    if info.duration_sec < MIN_VIDEO_DURATION_SEC:
        return IngestResult(
            False,
            f"مدت ویدیو ({info.duration_sec:.0f} ثانیه) بسیار کوتاه است — ویدیوی کامل وادی را ارسال کنید",
            f"Video duration ({info.duration_sec:.0f}s) is too short — submit the full workout video")
    if info.duration_sec > MAX_VIDEO_DURATION_SEC + 1.0:
        return IngestResult(
            False,
            f"مدت ویدیو ({info.duration_sec / 60:.1f} دقیقه) از سقف مجاز ({MAX_VIDEO_DURATION_SEC // 60} دقیقه) بیشتر است",
            f"Video duration ({info.duration_sec / 60:.1f} min) exceeds the allowed maximum ({MAX_VIDEO_DURATION_SEC // 60} min)")
    if info.height < 360 or info.width < 480:
        return IngestResult(
            False,
            "رزولوشن ویدیو بسیار پایین است — حداقل 480p توصیه می‌شود (720p یا بالاتر بهتر است)",
            "Video resolution is too low — 480p minimum recommended (720p or better preferred)")
    return IngestResult(True, None, None, info)
