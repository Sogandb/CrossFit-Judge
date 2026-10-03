"""Movement FSM base class — the contract every deep-implemented movement
follows. Design pillars (from the V2 architecture sessions):

1. Output-based validity predicates (what the rulebook demands at the
   checkpoints), not technique-style mimicry.
2. Hysteresis + debounce on every continuous signal (lessons from the v1
   kettlebell dead-FSM bug: the raw signal must demonstrably traverse the
   hysteresis band — verified in unit tests).
3. Scale-invariance: every threshold is a fraction of calibrated body height H.
4. Asymmetric error policy: auto no-rep only on high-confidence signals;
   everything else becomes a REVIEW flag.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from core.types import Attempt, PoseFrame, SceneModel


@dataclass
class FrameContext:
    t: float                 # seconds from video start (CFR timeline)
    frame_index: int
    pose: PoseFrame
    scene: SceneModel


class MovementFSM(abc.ABC):
    """Stateful per-video movement judge.

    `process(ctx)` is called once per analysis frame; the FSM buffers an
    `Attempt` while a rep is in progress and finalises it (REP / NO_REP) when
    the rep completes or times out. Completed attempts are returned exactly
    once from the *next* process() call via the outbox pattern.

    `enabled` implements the expected-sequence constraint: the WOD sequencer
    activates only the movements prescribed for the current (and next) block,
    so movement FSMs never interfere across transitions.
    """

    movement_id: str = ""

    def __init__(self) -> None:
        self._outbox: list[Attempt] = []
        self.enabled: bool = True

    @abc.abstractmethod
    def process(self, ctx: FrameContext) -> None: ...

    def gate(self) -> bool:
        """Subclasses call this first inside process(): when disabled the FSM
        consumes the frame without state changes."""
        return self.enabled

    def collect(self) -> list[Attempt]:
        out, self._outbox = self._outbox, []
        return out

    def emit(self, attempt: Attempt) -> None:
        self._outbox.append(attempt)

    def reset(self) -> None:
        self._outbox.clear()
