"""
Timeline visualisation: a horizontal chart of every rep attempt over time,
coloured by verdict, with the time-cap marked. Saved as a PNG.
"""
from __future__ import annotations

from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from movements.base_movement import RepEvent


def render_timeline(events: list[RepEvent], time_cap: float | None,
                    out_path: str, workout_name: str = "") -> str:
    if not events:
        # Still render an empty timeline so the UI always has an asset.
        fig, ax = plt.subplots(figsize=(12, 3))
        ax.set_title(f"{workout_name} — Rep Timeline (no reps detected)")
        ax.set_xlabel("Time (s)")
        ax.set_yticks([])
        if time_cap:
            ax.axvline(time_cap, color="red", linestyle="--", label="Time cap")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return out_path

    times = [e.end_time for e in events]
    labels = [e.movement for e in events]
    colors = ["#22c55e" if e.valid else "#ef4444" for e in events]
    confidences = [e.confidence for e in events]

    # Group movements on separate rows.
    unique_movements = list(dict.fromkeys(labels))
    row_map = {m: i for i, m in enumerate(unique_movements)}
    rows = [row_map[m] for m in labels]

    fig, ax = plt.subplots(figsize=(12, max(2, 0.8 + 0.6 * len(unique_movements))))
    sc = ax.scatter(times, rows, c=colors, s=[120 + 200 * c for c in confidences],
                    edgecolors="black", linewidths=0.6, zorder=3)

    # Connect reps within the same movement.
    for i in range(1, len(events)):
        if labels[i] == labels[i - 1]:
            ax.plot([times[i - 1], times[i]], [rows[i - 1], rows[i]],
                    color="#6b7280", linewidth=1, zorder=2)

    if time_cap:
        ax.axvline(time_cap, color="#ef4444", linestyle="--", linewidth=1.5,
                   zorder=1, label="Time cap")

    ax.set_yticks(range(len(unique_movements)))
    ax.set_yticklabels([m.replace("_", " ").title() for m in unique_movements])
    ax.set_xlabel("Time (seconds)")
    ax.set_title(f"{workout_name} — Rep Timeline" if workout_name else "Rep Timeline")
    ax.grid(axis="x", alpha=0.3)

    legend_handles = [
        Patch(facecolor="#22c55e", edgecolor="black", label="Good rep"),
        Patch(facecolor="#ef4444", edgecolor="black", label="No-rep"),
    ]
    if time_cap:
        legend_handles.append(plt.Line2D([0], [0], color="#ef4444",
                                         linestyle="--", label="Time cap"))
    ax.legend(handles=legend_handles, loc="upper right", fontsize=9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
