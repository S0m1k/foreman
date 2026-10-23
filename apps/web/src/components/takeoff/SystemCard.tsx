import {
  EXCLUDED,
  UNKNOWN,
  formatM,
  systemColour,
  verdict,
  type Group,
  type SystemSummary,
} from "./model";

interface Props {
  summary: SystemSummary;
  targets: string[];
  selectedKey: string | null;
  onSelect: (group: Group | null) => void;
  onMove: (group: Group, target: string) => void;
}

export function SystemCard({ summary, targets, selectedKey, onSelect, onMove }: Props) {
  const colour = systemColour(summary.system);
  const v = verdict(summary.projectM, summary.specM);
  const scaleMax = Math.max(summary.projectM, summary.specM ?? 0, 1) * 1.08;
  const otherPct = ((summary.projectM - summary.sheetM) / scaleMax) * 100;
  const sheetPct = (summary.sheetM / scaleMax) * 100;
  const specPct = summary.specM === null ? null : (summary.specM / scaleMax) * 100;

  return (
    <article className="card overflow-hidden" style={{ borderLeft: `3px solid ${colour}` }}>
      <header className="px-4 pt-3 pb-2">
        <div className="flex items-baseline gap-3">
          <h3 className="mono text-lg font-bold" style={{ color: colour }}>
            {summary.system}
          </h3>
          <span className="mono text-sm" title="Длина на этом листе">
            {formatM(summary.sheetM)} м
          </span>
          <span className={`chip ${v.tone} ml-auto`}>{v.label}</span>
        </div>
        <p className="text-xs text-[var(--muted)] mt-1">
          по проекту <span className="mono">{formatM(summary.projectM)}</span>
          {summary.specM !== null && (
            <>
              {" "}из <span className="mono">{formatM(summary.specM)} м</span> по спецификации
            </>
          )}
        </p>
        <div className="relative mt-2 h-1.5 rounded-full bg-[var(--surface-2)] flex" aria-hidden>
          <div className="h-full rounded-l-full opacity-40" style={{ width: `${otherPct}%`, background: colour }}
               title="На других листах" />
          <div className="h-full" style={{ width: `${sheetPct}%`, background: colour }}
               title="На этом листе" />
          {specPct !== null && (
            <div className="absolute -top-1 h-3.5 w-0.5 bg-[var(--text)]" style={{ left: `${specPct}%` }}
                 title="Лимит по спецификации" />
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
                className="mono text-xs bg-transparent border border-[var(--line)] rounded px-1 py-0.5 text-[var(--muted)] max-w-20"
              >
                <option value="">⇄</option>
                {targets.map((s) => (
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
