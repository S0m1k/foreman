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
  const [showFittings, setShowFittings] = useState(true);
  const dim = highlighted.size > 0;
  const fittingCount = sheet.fittings?.length ?? 0;

  return (
    <section className="relative flex-1 min-w-0 flex flex-col bg-[var(--raised)]" aria-label="Чертёж">
      <div className="absolute left-4 top-4 z-10 flex items-center gap-2">
        <div className="segmented" role="group" aria-label="Масштаб просмотра">
          {ZOOMS.map((z) => (
            <button key={z} aria-pressed={zoom === z} onClick={() => setZoom(z)}>
              {Math.round(z * 100)}%
            </button>
          ))}
        </div>
        {fittingCount > 0 && (
          <div className="segmented">
            <button aria-pressed={showFittings} onClick={() => setShowFittings((on) => !on)}>
              Решётки и клапаны · {fittingCount}
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        <svg
          viewBox={`0 0 ${sheet.width} ${sheet.height}`}
          style={{ width: `${zoom * 100}%`, minWidth: 640 }}
          className="block"
          role="img"
          aria-label="План ОВ с размеченными воздуховодами"
        >
          <rect width={sheet.width} height={sheet.height} fill="#ffffff" />
          <image href={imageUrl} width={sheet.width} height={sheet.height} opacity={0.5} />
          {sheet.runs.map((run) => {
            const system = effectiveSystem(run, overrides);
            const excluded = system === EXCLUDED;
            const on = highlighted.has(run.id);
            const colour = systemColour(system);
            const opacity = excluded ? 0.4 : dim && !on ? 0.22 : 1;
            const [x1, y1] = run.p0;
            const [x2, y2] = run.p1;
            const line = { x1, y1, x2, y2, strokeLinecap: "round" as const };
            return (
              <g key={run.id} opacity={opacity}>
                {on && (
                  <line {...line} stroke={colour} strokeWidth={14} opacity={0.22}
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
          {showFittings &&
            (sheet.fittings ?? []).map((item) => (
              <g key={`f${item.id}`} transform={`translate(${item.x} ${item.y})`}>
                <title>{item.mark}</title>
                <rect x={-4.5} y={-4.5} width={9} height={9} transform="rotate(45)"
                      fill={item.kind === "клапан" ? "#141619" : "#ffffff"}
                      stroke="#141619" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
              </g>
            ))}
        </svg>
      </div>
    </section>
  );
}
