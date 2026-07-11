"""Misc helpers."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def timer(label: str) -> Iterator[float]:
    """Context manager that prints elapsed time for a block."""
    start = time.perf_counter()
    yield start
    elapsed = time.perf_counter() - start
    print(f"[timer] {label}: {elapsed:.2f}s")


def format_timestamp(seconds: float) -> str:
    """mm:ss.cs formatting."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default
