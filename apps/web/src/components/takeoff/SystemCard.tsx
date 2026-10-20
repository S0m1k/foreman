import {
  EXCLUDED,
  SYSTEMS,
  SYSTEM_COLOUR,
  UNKNOWN,
  formatM,
  sheet,
  type Group,
  type SystemSummary,
} from "./model";

interface Props {
  summary: SystemSummary;
  selectedKey: string | null;
  onSelect: (group: Group | null) => void;
  onMove: (group: Group, target: string) => void;
}

const TOLERANCE = 0.03;

function verdict(measured: number, spec: number | null) {
  if (spec === null) return { label: "нет в спецификации", tone: "chip-low" };
  const delta = measured - spec;
  if (Math.abs(delta) <= spec * TOLERANCE) return { label: "сходится", tone: "chip-ok" };
  if (delta > 0) return { label: `+${formatM(delta)} м сверх`, tone: "chip-high" };
  return { label: `${formatM(delta)} м недобор`, tone: "chip-medium" };
}

export function SystemCard({ summary, selectedKey, onSelect, onMove }: Props) {
  const colour = SYSTEM_COLOUR[summary.system];
  const v = verdict(summary.measuredM, summary.specM);
  const scaleMax = Math.max(summary.measuredM, summary.specM ?? 0, 1) * 1.12;
  const measuredPct = (summary.measuredM / scaleMax) * 100;
  const specPct = summary.specM === null ? null : (summary.specM / scaleMax) * 100;

  return (
    <article className="card overflow-hidden" style={{ borderLeft: `3px solid ${colour}` }}>
      <header className="px-4 pt-3 pb-2">
        <div className="flex items-baseline gap-3">
          <h3 className="mono text-lg font-bold" style={{ color: colour }}>
            {summary.system}
          </h3>
          <span className="mono text-sm">{formatM(summary.measuredM)} м</span>
          <span className="text-xs text-[var(--muted)]">
            по спец.{" "}
            <span className="mono">{summary.specM === null ? "—" : `${formatM(summary.specM)} м`}</span>
          </span>
          <span className={`chip ${v.tone} ml-auto`}>{v.label}</span>
        </div>
        <div className="relative mt-2.5 h-1.5 rounded-full bg-[var(--surface-2)]" aria-hidden>
          <div className="h-full rounded-full" style={{ width: `${measuredPct}%`, background: colour }} />
          {specPct !== null && (
            <div
              className="absolute -top-1 h-3.5 w-0.5 bg-[var(--text)]"
              style={{ left: `${specPct}%` }}
              title="Лимит по спецификации"
            />
          )}
        </div>
      </header>

      <ul className="border-t border-[var(--line)] divide-y divide-[var(--line)]">
        {summary.groups.map((g) => {
          const active = g.key === selectedKey;
          return (
            <li
              key={g.key}
              className={`grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-4 py-2 text-sm cursor-pointer transition-colors ${
                active
                  ? "bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] shadow-[inset_3px_0_0_var(--accent)]"
                  : "hover:bg-[var(--surface-2)]"
              }`}
              onClick={() => onSelect(active ? null : g)}
            >
              <span className="mono">{g.section}</span>
              <span className="text-xs text-[var(--muted)] w-16">{g.insulated ? "изолир." : "—"}</span>
              <span className="mono w-14 text-right">{formatM(g.lengthM)}</span>
              <select
                aria-label={`Перенести участок ${g.section} в другую систему`}
                value=""
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => e.target.value && onMove(g, e.target.value)}
                className="mono text-xs bg-transparent border border-[var(--line)] rounded px-1 py-0.5 text-[var(--muted)]"
              >
                <option value="">⇄</option>
                {SYSTEMS.filter((s) => s !== g.system).map((s) => (
                  <option key={s} value={s}>
                    → {s}
                  </option>
                ))}
                <option value={EXCLUDED}>исключить</option>
              </select>
            </li>
          );
        })}
        {summary.groups.length === 0 && summary.system !== UNKNOWN && (
          <li className="px-4 py-2 text-xs text-[var(--muted)]">Участков нет</li>
        )}
      </ul>
    </article>
  );
}

export const specTotal = Object.values(sheet.specM as Record<string, number>).reduce(
  (a, b) => a + b,
  0,
);
