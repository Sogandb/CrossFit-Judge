"""Movement registry. Maps movement names to their detector classes."""
from __future__ import annotations

from typing import Type

from movements.base_movement import BaseMovement
from movements.squat import Squat
from movements.pushup import Pushup
from movements.burpee import Burpee
from movements.thruster import Thruster
from movements.pullup import Pullup
from movements.kettlebell_swing import KettlebellSwing

MOVEMENTS: dict[str, Type[BaseMovement]] = {
    "squat": Squat,
    "pushup": Pushup,
    "burpee": Burpee,
    "thruster": Thruster,
    "pullup": Pullup,
    "kettlebell_swing": KettlebellSwing,
}


def get_movement_class(name: str) -> Type[BaseMovement]:
    if name not in MOVEMENTS:
        raise KeyError(f"Unknown movement: {name}")
    return MOVEMENTS[name]
