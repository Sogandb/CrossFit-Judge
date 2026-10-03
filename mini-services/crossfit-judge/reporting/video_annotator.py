"""
Annotated review-video generator (second pass).

Draws on-frame overlays (Latin-only text — Persian is rendered in the web UI
timeline, avoiding ffmpeg/PIL RTL shaping problems):
  * top-left: workout clock T (relative to the detected start)
  * top-right: running credited-rep counter
  * bottom banner: the latest rep/no-rep event (green / red)
  * border flash: green = rep credited, red = no-rep

CRITICAL v1 fix: the original AUDIO TRACK IS KEPT (-map 1:a) — judges must
hear the timer beeps and the judge's count calls.
"""
from __future__ import annotations

import subprocess
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config.settings import PREROLL_SEC, TARGET_FPS

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fmt_clock(sec: float) -> str:
    neg = sec < 0
    sec = abs(sec)
    m, s = int(sec // 60), int(sec % 60)
    return ("-" if neg else "") + f"{m:02d}:{s:02d}"


def _active_events(result: dict) -> tuple[list[dict], list[dict]]:
    scored = [e for e in result.get("events", []) if e.get("scored")]
    no_reps = [e for e in result.get("events", [])
               if e.get("outcome") == "no_rep" and not e.get("post_cap")]
    scored.sort(key=lambda e: e["t_end"])
    no_reps.sort(key=lambda e: e["t_end"])
    return scored, no_reps


def annotate_video(src_path: str, dst_path: str, result: dict,
                   hold_sec: float = 2.0) -> None:
    from core.frame_source import FrameSource

    window = result.get("analysis_window", {})
    window_start = float(window.get("start_sec") or 0.0)
    window_end = window.get("end_sec")
    t_start = float(result["start_detection"]["t_start_sec"])

    scored, no_reps = _active_events(result)
    # merged banner timeline: last event whose t_end has passed
    banners = []
    for e in scored:
        banners.append((e["t_end"], "rep",
                        f"REP {e.get('rep_no', '')} {e['movement'].upper()}"))
    for e in no_reps:
        code = (e.get("reason_code") or "").replace("_", " ")
        banners.append((e["t_end"], "no_rep", f"NO-REP  {code}"))
    banners.sort(key=lambda b: b[0])

    font_big = _font(34)
    font_small = _font(26)

    with FrameSource(src_path, start_sec=window_start, end_sec=window_end,
                     fps=TARGET_FPS) as src:
        h, w = src.frame_shape
        enc = subprocess.Popen(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "bgr24",
                "-s", f"{w}x{h}", "-r", str(TARGET_FPS), "-i", "pipe:0",
                "-ss", f"{window_start:.3f}", "-i", src_path,
                "-map", "0:v", "-map", "1:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", "-shortest",
                dst_path,
            ],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert enc.stdin
        try:
            for idx, t_rel, bgr in src.frames():
                t_abs = window_start + t_rel
                frame = annotate_frame(bgr, t_abs, t_start, scored,
                                       banners, hold_sec,
                                       font_big, font_small)
                enc.stdin.write(frame.tobytes())
        finally:
            try:
                enc.stdin.close()
            except Exception:
                pass
            enc.wait(timeout=120)


def annotate_frame(bgr, t_abs: float, t_start: float, scored: list[dict],
                   banners: list[tuple[float, str, str]], hold_sec: float,
                   font_big, font_small):
    from PIL import Image
    import numpy as np  # local import (mediapipe already requires numpy)

    img = Image.fromarray(bgr[:, :, ::-1])  # BGR → RGB
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # credited reps so far
    credited = sum(1 for e in scored if e["t_end"] <= t_abs)
    clock = t_abs - t_start

    # banner: latest event within the hold window
    active = None
    for t_ev, kind, text in banners:
        if t_ev <= t_abs and t_abs <= t_ev + hold_sec:
            active = (kind, text)

    border = None
    if active:
        border = (0, 200, 80) if active[0] == "rep" else (230, 60, 60)

    # draw border flash
    if border:
        bw = 10
        draw.rectangle([0, 0, w, bw], fill=border)
        draw.rectangle([0, h - bw, w, h], fill=border)
        draw.rectangle([0, 0, bw, h], fill=border)
        draw.rectangle([w - bw, 0, w, h], fill=border)

    # clock (top-left)
    clock_txt = f"T {_fmt_clock(clock)}"
    draw.rectangle([12, 12, 230, 62], fill=(0, 0, 0, 160))
    draw.text((22, 18), clock_txt, fill=(255, 255, 255), font=font_big)

    # rep counter (top-right)
    rep_txt = f"REPS {credited}"
    tw = draw.textlength(rep_txt, font=font_big)
    draw.rectangle([w - tw - 36, 12, w - 12, 62], fill=(0, 0, 0, 160))
    draw.text((w - tw - 26, 18), rep_txt, fill=(255, 255, 255), font=font_big)

    # banner (bottom-left)
    if active:
        kind, text = active
        color = (140, 255, 160) if kind == "rep" else (255, 140, 140)
        tw2 = draw.textlength(text, font=font_small)
        draw.rectangle([12, h - 60, 24 + tw2, h - 12], fill=(0, 0, 0, 170))
        draw.text((22, h - 54), text, fill=color, font=font_small)

    out = np.array(img)[:, :, ::-1]  # RGB → BGR
    return out
