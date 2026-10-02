"""Upload ingest validation gates (ffprobe-based). Persian error messages —
the athlete should immediately understand what to fix."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.settings import (
    MAX_VIDEO_DURATION_SEC,
    MIN_VIDEO_DURATION_SEC,
)
from core.frame_source import probe


@dataclass
class IngestResult:
    ok: bool
    error_fa: Optional[str] = None
    info: Optional[object] = None


def validate_video(path: str) -> IngestResult:
    info = probe(path)
    if info is None:
        return IngestResult(False, "فایل ویدیو قابل خواندن نیست (ffprobe). فرمت پشتیبانی‌شده: MP4 / MOV / WebM")
    if info.duration_sec <= 0:
        return IngestResult(False, "مدت زمان ویدیو قابل تشخیص نیست — فایل احتمالاً ناقص آپلود شده است")
    if info.duration_sec < MIN_VIDEO_DURATION_SEC:
        return IngestResult(False, f"مدت ویدیو ({info.duration_sec:.0f} ثانیه) بسیار کوتاه است — ویدیوی کامل وادی را ارسال کنید")
    if info.duration_sec > MAX_VIDEO_DURATION_SEC + 1.0:
        return IngestResult(
            False,
            f"مدت ویدیو ({info.duration_sec / 60:.1f} دقیقه) از سقف مجاز ({MAX_VIDEO_DURATION_SEC // 60} دقیقه) بیشتر است",
        )
    if info.height < 360 or info.width < 480:
        return IngestResult(False, "رزولوشن ویدیو بسیار پایین است — حداقل 480p توصیه می‌شود (720p یا بالاتر بهتر است)")
    return IngestResult(True, None, info)
