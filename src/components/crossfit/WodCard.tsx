"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Clock, ListOrdered } from "lucide-react";
import { useLang } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/**
 * The WOD under judgement — v1 template card style.
 * Content (name, description, scoring, standards) is ALWAYS English
 * (product rule: WODs / movements / terminology are not translated).
 */

const RUNGS = [18, 15, 12, 9, 6, 3];

const THRUSTER_STANDARDS: { title: string; items: string[] }[] = [
  {
    title: "Start of Movement",
    items: [
      "The barbell must start on the ground.",
      "Using a rack to pick up the barbell is not allowed.",
      "When lifting the bar from the ground, a squat clean directly into the thruster is permitted.",
    ],
  },
  {
    title: "Squat Execution",
    items: [
      "The barbell must be held in the rack position on the shoulders.",
      "Elbows must stay in front of the bar.",
      "The hip crease must pass below the top of the knee (below parallel).",
      "Contact of the hands with the legs during the movement is a fault.",
    ],
  },
  {
    title: "Top of the Movement",
    items: [
      "At the top, the hips, knees and elbows must reach full extension.",
      "The bar must be over the middle of the body or behind it (from a profile view).",
      "Both feet must stay in line, directly under the body.",
    ],
  },
  {
    title: "Important Notes",
    items: [
      "A full squat + pause + jerk (push / split / power) is no longer a thruster — the movement must be one continuous motion.",
      "Walking forward during the movement is a fault.",
    ],
  },
];

const BFB_STANDARDS: { title: string; items: string[] }[] = [
  {
    title: "General Rules",
    items: [
      "The athlete must face the bar (not stand parallel to it).",
      "Feet must be close to the bar but not on it.",
      "The chest (sternum) must touch the ground.",
      "The rep finishes with a jump and a simultaneous two-foot landing beyond the bar.",
      "The athlete must completely cross the bar — both feet must land on the far side.",
    ],
  },
  {
    title: "Special Clauses",
    items: [
      "A one-foot takeoff is permitted: one foot lifts and the trailing foot follows into the air shortly after.",
      "It is a fault if one foot crosses and lands beyond the bar while the other foot remains on the ground on the start side.",
      "Twisting the body toward the bar mid-air is allowed (for speed).",
    ],
  },
  {
    title: "Common Faults",
    items: [
      "Chest not touching the ground.",
      "One-foot landing (feet must land together).",
      "Contact with the bar during the jump.",
    ],
  },
];

export function WodCard() {
  const { t } = useLang();
  const [open, setOpen] = useState<"thruster" | "bfb" | null>(null);

  return (
    <div className="rounded-xl border border-edge bg-panel">
      {/* header — the v1 "category header" pattern */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-3 border-b border-edge">
        <span className="text-sm font-bold uppercase tracking-wider text-brand-fg">
          For Time
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-ink-3">
          <Clock className="h-3 w-3" />
          {t("wod.timeCap")}
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-ink-3">
          <ListOrdered className="h-3 w-3" />
          {t("side.totalReps")}
        </span>
      </div>

      <div className="p-4 space-y-4">
        <div>
          <h3 className="font-semibold text-sm text-ink mb-1.5">
            Thruster &amp; Bar-Facing Burpee Ladder
          </h3>
          <p className="text-[13px] leading-relaxed text-ink-3">
            Perform in order: 18 thrusters then 18 bar-facing burpees, 15 thrusters
            then 15 bar-facing burpees, then 12, 9, 6 and 3. Time cap: 10 minutes.
            Total: 126 reps.
          </p>
        </div>

        {/* ladder chips  18+18 → 15+15 → … */}
        <div className="flex flex-wrap items-center gap-2">
          {RUNGS.map((r, i) => (
            <span key={r} className="flex items-center gap-2">
              <span className="rounded bg-chip px-2 py-0.5 text-xs font-bold text-ink-2 tabular-nums">
                {r} + {r}
              </span>
              {i < RUNGS.length - 1 && (
                <ChevronRight className="h-3 w-3 text-ink-4 rtl:rotate-180" />
              )}
            </span>
          ))}
        </div>

        <p className="text-xs leading-relaxed text-ink-3">
          <span className="font-semibold text-ink-2">{t("wod.scoring")}: </span>
          If the workout is completed: finish time (lower is better). If not
          completed within the cap: total credited reps at the 10-minute mark.
        </p>

        {/* movement standards — v1 collapsible category style */}
        <div className="space-y-2 pt-1">
          <StandardsSection
            label={t("wod.standardsThruster")}
            sections={THRUSTER_STANDARDS}
            isOpen={open === "thruster"}
            onToggle={() => setOpen(open === "thruster" ? null : "thruster")}
          />
          <StandardsSection
            label={t("wod.standardsBfb")}
            sections={BFB_STANDARDS}
            isOpen={open === "bfb"}
            onToggle={() => setOpen(open === "bfb" ? null : "bfb")}
          />
        </div>
      </div>
    </div>
  );
}

function StandardsSection({
  label, sections, isOpen, onToggle,
}: {
  label: string;
  sections: { title: string; items: string[] }[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-panel-2/40 transition-colors",
        isOpen ? "border-edge-2" : "border-edge",
      )}
    >
      <button
        onClick={onToggle}
        aria-expanded={isOpen}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
      >
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-ink-3 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-ink-3 shrink-0 rtl:rotate-180" />
        )}
        <div className="flex-1 min-w-0">
          <span className="text-sm font-bold uppercase tracking-wider text-brand-fg">
            {label}
          </span>
        </div>
      </button>
      {isOpen && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 pt-1 border-t border-edge/60">
          {sections.map((sec) => (
            <div key={sec.title}>
              <h4 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-ink-2">
                {sec.title}
              </h4>
              <ul className="list-disc space-y-1 ps-4 text-[13px] leading-relaxed text-ink-3">
                {sec.items.map((it) => <li key={it}>{it}</li>)}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
