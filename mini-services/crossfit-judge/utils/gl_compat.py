"""GL runtime self-sufficiency for MediaPipe's C bindings.

MediaPipe's pose landmarker dlopen()s ``libmediapipe.so`` which declares
DT_NEEDED on ``libEGL.so.1`` / ``libGLESv2.so.2`` (GPU handshake even when
running fully on CPU). The canonical spawn path (the Next.js supervisor in
``python-server.ts``) exports LD_LIBRARY_PATH pointing at the git-vendored
``pylibs/`` directory — but ANY other spawn (manual restart, systemd, a
crash-recovery re-spawn, a bare ``uvicorn`` command) lacks it, and every
analysis then dies with::

    OSError: libEGL.so.1: cannot open shared object file

…while ``import mediapipe`` still succeeds, so shallow health checks keep
reporting ``deps_ok: true`` — exactly the deceptive "engine healthy,
analysis crashes" failure the users kept hitting.

This module makes the engine robust no matter HOW the process was started:

* probe each required GL soname with ``ctypes.CDLL``;
* on failure, load the git-vendored copy from ``pylibs/`` with RTLD_GLOBAL;
* once a library with a given SONAME is loaded into the process, the dynamic
  loader satisfies later dlopen()s from the already-loaded module — no
  LD_LIBRARY_PATH required.

Load order matters (glvnd layering):
``libGLdispatch`` → ``libEGL`` / ``libGLESv2`` → ``libGL`` / ``libGLX``.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Tuple

# Order matters: libGLdispatch first (everything else depends on it).
_NEEDED = (
    "libGLdispatch.so.0",
    "libEGL.so.1",
    "libGLESv2.so.2",
    "libGL.so.1",
    "libGLX.so.0",
)


def _pylibs_dirs() -> list[Path]:
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "pylibs",     # <service>/pylibs (git-vendored)
        Path.cwd() / "pylibs",
    ]
    return [d for d in candidates if d.is_dir()]


def ensure_gl() -> Tuple[bool, str]:
    """Make every required GL soname loadable in THIS process.

    Returns ``(ok, detail)``; ``detail`` says where each lib came from.
    Safe to call repeatedly (idempotent — the loader caches by soname).
    """
    missing: list[str] = []
    for soname in _NEEDED:
        try:
            ctypes.CDLL(soname, mode=ctypes.RTLD_GLOBAL)
        except OSError:
            missing.append(soname)
    if not missing:
        return True, "system"

    sources: list[str] = []
    for d in _pylibs_dirs():
        # Best-effort: also help the loader for any FULL-PATH loads done
        # later (harmless if the env var was already set by the supervisor).
        os.environ["LD_LIBRARY_PATH"] = (
            f"{d}:{os.environ.get('LD_LIBRARY_PATH', '')}").rstrip(":")
        for soname in list(missing):
            p = d / soname
            if not p.exists():
                continue
            try:
                ctypes.CDLL(str(p), mode=ctypes.RTLD_GLOBAL)
                missing.remove(soname)
                sources.append(soname)
            except OSError:
                # e.g. libGLX needs libX11 — absent systems just skip it
                pass
        if not missing:
            break

    if not missing:
        return True, "vendored:" + ",".join(sources)
    # libGL / libGLX are optional for MediaPipe (EGL/GLES are the hard reqs)
    hard = [s for s in missing if s not in ("libGL.so.1", "libGLX.so.0")]
    if not hard:
        return True, "partial-vendored:" + ",".join(sources)
    return False, "missing:" + ",".join(missing)


def mediapipe_bindings_ok() -> Tuple[bool, str]:
    """Deep check: force-load MediaPipe's C bindings exactly like the
    analyzer will (``load_raw_library`` is cached module-global, so this
    also PRE-WARMS the library — zero extra cost for the first analysis)."""
    try:
        from mediapipe.tasks.python.core import mediapipe_c_bindings as mcb
        mcb.load_raw_library(())  # noqa: F401 — side effect: ctypes.CDLL
        return True, ""
    except Exception as e:  # noqa: BLE001 — OSError / ImportError alike
        return False, str(e)
