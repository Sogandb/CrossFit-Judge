"""Shared test fixtures: a calibrated SceneModel + frame runner."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from core.mock_pose import SkeletonBuilder, gen_bfb_rep, gen_thruster_rep, pose_frame  # noqa: E402
from core.types import SceneModel  # noqa: E402
from movements.base import FrameContext  # noqa: E402

GY = 800.0
H = 500.0
X0 = 600.0
BAR_X = X0  # the barbell lives at the thruster station


@pytest.fixture
def scene() -> SceneModel:
    s = SceneModel()
    s.H = H
    s.set_ground(GY, 0.0)          # flat ground for tests
    s.set_bar(BAR_X, GY, 1.0)      # confident bar anchor
    return s


def run_fsm(fsm, frames, scene, t0=0.0):
    """Feed frames through an FSM; return collected attempts (with a final
    force-close so trailing attempts are not lost)."""
    out = []
    last_t = t0
    for i, pf in enumerate(frames):
        ctx = FrameContext(t=pf.timestamp, frame_index=pf.frame_index,
                           pose=pf, scene=scene)
        fsm.process(ctx)
        out.extend(fsm.collect())
        last_t = pf.timestamp
    if hasattr(fsm, "force_close"):
        fsm.force_close(last_t)
        out.extend(fsm.collect())
    return out


def make_frames(fn) -> list:
    """Run a generator fn that appends PoseFrames into a list."""
    buf = []
    fn(buf)
    return buf
