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

/**
 * The plan track: as long as the specification allows, the other sheets' metres as a pale
 * segment, this sheet's in the system's colour, anything past the limit in the negative colour.
 */
function PlanTrack({ summary, colour }: { summary: SystemSummary; colour: string }) {
  const { sheetM, projectM, specM } = summary;
  const limit = specM && specM > 0 ? specM : null;
  const scale = Math.max(projectM, limit ?? 0, 1);
  const pct = (m: number) => `${(Math.min(m, scale) / scale) * 100}%`;
  const others = Math.max(projectM - sheetM, 0);
  const within = limit ? Math.min(projectM, limit) : projectM;
  const over = limit ? Math.max(projectM - limit, 0) : 0;
  return (
    <div className="relative mt-3 h-1.5 rounded-full bg-[var(--active)] overflow-hidden" aria-hidden>
      <div className="absolute inset-y-0 left-0 opacity-35" style={{ width: pct(Math.min(others, within)), background: colour }} />
      <div className="absolute inset-y-0" style={{ left: pct(Math.min(others, within)), width: pct(Math.max(within - others, 0)), background: colour }} />
      {over > 0 && (
        <div className="absolute inset-y-0" style={{ left: pct(limit!), width: pct(over), background: "var(--negative)" }} />
      )}
    </div>
  );
}

export function SystemCard({ summary, targets, selectedKey, onSelect, onMove }: Props) {
  const colour = systemColour(summary.system);
  const v = verdict(summary.projectM, summary.specM);
  const isUnknown = summary.system === UNKNOWN;

  return (
    <article className="panel overflow-hidden">
      <header className="px-4 pt-3.5 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="dot" style={{ background: colour }} />
          <h3 className="text-[15px] font-semibold">{summary.system}</h3>
          <span className="num text-[15px] ml-1" title="Длина на этом листе">
            {formatM(summary.sheetM)} <span className="muted text-xs">м</span>
          </span>
          {isUnknown ? (
            <span className="pill pill-warning ml-auto">разнести</span>
          ) : (
            <span className={`pill ${v.tone} ml-auto`}>{v.label}</span>
          )}
        </div>
        {!isUnknown && (
          <>
            <p className="text-xs muted mt-1.5 num">
              по проекту {formatM(summary.projectM)} м
              {summary.specM ? ` из ${formatM(summary.specM)} м по спецификации` : ""}
            </p>
            <PlanTrack summary={summary} colour={colour} />
          </>
        )}
      </header>

      <ul>
        {summary.groups.map((g) => {
          const active = g.key === selectedKey;
          return (
            <li
              key={g.key}
              className={`grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 px-4 h-10 text-sm border-t border-[var(--rule)] cursor-pointer transition-colors ${
                active ? "bg-[var(--active)]" : "hover:bg-[var(--raised)]"
              }`}
              onClick={() => onSelect(active ? null : g)}
              aria-selected={active}
            >
              <span className="num truncate">{g.section}</span>
              <span className="text-xs muted w-16 max-[640px]:w-auto">
                {g.insulated && <><span className="max-[640px]:hidden">в изоляции</span><span className="hidden max-[640px]:inline">изол.</span></>}
              </span>
              <span className="num w-14 text-right">{formatM(g.lengthM)}</span>
              <select
                aria-label={`Перенести участки ${g.section} в другую систему`}
                value=""
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => e.target.value && onMove(g, e.target.value)}
                className="input-sm w-[112px] flex-none"
              >
                <option value="">Перенести</option>
                {targets.map((s) => (
                  <option key={s} value={s}>
                    в {s}
                  </option>
                ))}
                <option value={EXCLUDED}>Исключить</option>
              </select>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
