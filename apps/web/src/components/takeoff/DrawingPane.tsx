"use client";

import { useState } from "react";
import {
  EXCLUDED,
  SYSTEM_COLOUR,
  UNKNOWN,
  effectiveSystem,
  sheet,
  type Overrides,
} from "./model";

interface Props {
  overrides: Overrides;
  highlighted: ReadonlySet<number>;
  onHover: (runId: number | null) => void;
  onPick: (runId: number) => void;
}

const ZOOMS = [1, 1.5, 2, 3];

export function DrawingPane({ overrides, highlighted, onHover, onPick }: Props) {
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
          <image href="/demo/sheet-1.svg" width={sheet.width} height={sheet.height} opacity={0.55} />
          {sheet.runs.map((run) => {
            const system = effectiveSystem(run, overrides);
            const excluded = system === EXCLUDED;
            const on = highlighted.has(run.id);
            const colour = excluded ? "#9aa5b1" : SYSTEM_COLOUR[system] ?? SYSTEM_COLOUR[UNKNOWN];
            const opacity = excluded ? 0.35 : dim && !on ? 0.28 : 1;
            const [x1, y1] = run.p0;
            const [x2, y2] = run.p1;
            return (
              <g key={run.id} opacity={opacity}>
                {on && (
                  <line
                    x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={colour} strokeWidth={16} strokeLinecap="round" opacity={0.28}
                  />
                )}
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke={colour} strokeWidth={on ? 6 : 4} strokeLinecap="round"
                  strokeDasharray={excluded ? "2 8" : undefined}
                />
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="transparent" strokeWidth={22} strokeLinecap="round"
                  className="cursor-pointer"
                  onMouseEnter={() => onHover(run.id)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onPick(run.id)}
                />
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}
