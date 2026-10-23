"use client";

import { useState } from "react";
import type { TakeoffSheet } from "@/lib/api";
import { EXCLUDED, effectiveSystem, systemColour, type Overrides } from "./model";

interface Props {
  sheet: TakeoffSheet;
  imageUrl: string;
  overrides: Overrides;
  highlighted: ReadonlySet<number>;
  onHover: (runId: number | null) => void;
  onPick: (runId: number) => void;
}

// A full-size plan is ~5000 pt wide; 800% is what it takes to read a callout.
const ZOOMS = [1, 2, 4, 8];

export function DrawingPane({ sheet, imageUrl, overrides, highlighted, onHover, onPick }: Props) {
  const [zoom, setZoom] = useState(1);
  const dim = highlighted.size > 0;

  return (
    <section className="relative flex-1 min-w-0 flex flex-col">
      <div className="absolute right-4 top-4 z-10 flex items-center gap-1 card px-1.5 py-1">
        {ZOOMS.map((z) => (
          <button
            key={z}
            onClick={() => setZoom(z)}
            className={`mono text-xs px-2 py-1 rounded ${
              zoom === z
                ? "bg-[var(--accent)] text-[#17130a]"
                : "text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            {Math.round(z * 100)}%
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto bg-[#0c1014]">
        <svg
          viewBox={`0 0 ${sheet.width} ${sheet.height}`}
          style={{ width: `${zoom * 100}%`, minWidth: 640 }}
          className="block"
          role="img"
          aria-label="План ОВ с размеченными воздуховодами"
        >
          <rect width={sheet.width} height={sheet.height} fill="#f4f1ea" />
          <image href={imageUrl} width={sheet.width} height={sheet.height} opacity={0.55} />
          {sheet.runs.map((run) => {
            const system = effectiveSystem(run, overrides);
            const excluded = system === EXCLUDED;
            const on = highlighted.has(run.id);
            const colour = systemColour(system);
            const opacity = excluded ? 0.35 : dim && !on ? 0.25 : 1;
            const [x1, y1] = run.p0;
            const [x2, y2] = run.p1;
            const line = { x1, y1, x2, y2, strokeLinecap: "round" as const };
            return (
              <g key={run.id} opacity={opacity}>
                {on && (
                  <line {...line} stroke={colour} strokeWidth={14} opacity={0.3}
                        vectorEffect="non-scaling-stroke" />
                )}
                <line {...line} stroke={colour} strokeWidth={on ? 5 : 3}
                      strokeDasharray={excluded ? "2 6" : undefined}
                      vectorEffect="non-scaling-stroke" />
                <line {...line} stroke="transparent" strokeWidth={16}
                      vectorEffect="non-scaling-stroke" className="cursor-pointer"
                      onMouseEnter={() => onHover(run.id)}
                      onMouseLeave={() => onHover(null)}
                      onClick={() => onPick(run.id)} />
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}
