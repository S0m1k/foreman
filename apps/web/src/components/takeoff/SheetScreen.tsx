"use client";

import { useMemo, useState } from "react";
import { DrawingPane } from "./DrawingPane";
import { SystemCard, specTotal } from "./SystemCard";
import {
  EXCLUDED,
  formatM,
  sheet,
  summarise,
  toRuCsv,
  type Group,
  type Overrides,
} from "./model";

export function SheetScreen() {
  const [overrides, setOverrides] = useState<Overrides>({});
  const [selected, setSelected] = useState<Group | null>(null);
  const [hoverRun, setHoverRun] = useState<number | null>(null);

  const summary = useMemo(() => summarise(overrides), [overrides]);
  const total = summary.reduce((sum, s) => sum + s.measuredM, 0);
  const excludedCount = Object.values(overrides).filter((v) => v === EXCLUDED).length;
  const changed = Object.keys(overrides).length;

  const highlighted = useMemo<ReadonlySet<number>>(() => {
    if (hoverRun !== null) return new Set([hoverRun]);
    return new Set(selected?.runIds ?? []);
  }, [hoverRun, selected]);

  const move = (group: Group, target: string) => {
    setOverrides((prev) => ({
      ...prev,
      ...Object.fromEntries(group.runIds.map((id) => [id, target])),
    }));
    setSelected(null);
  };

  const pickRun = (runId: number) => {
    const owner = summary.flatMap((s) => s.groups).find((g) => g.runIds.includes(runId));
    setSelected(owner && owner.key !== selected?.key ? owner : null);
  };

  const reset = () => {
    setOverrides({});
    setSelected(null);
  };

  const download = () => {
    const blob = new Blob([toRuCsv(summary)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ведомость-воздуховодов.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative left-1/2 w-screen -translate-x-1/2 -my-8 flex flex-col h-[calc(100vh-48px)]">
      <div className="flex items-center gap-3 px-5 py-2.5 border-b border-[var(--line)] bg-[var(--surface)]">
        <span className="mono text-sm">{sheet.file}</span>
        <span className="text-xs text-[var(--muted)]">
          Лист {sheet.page} из {sheet.pages}
        </span>
        <span className="chip chip-review" title="Масштаб найден по типовым сечениям воздуховодов">
          М 1:{sheet.scale} · авто
        </span>
        <span className="chip chip-low">демо-данные</span>
        <div className="ml-auto flex items-center gap-2">
          {changed > 0 && (
            <button className="btn btn-ghost !py-1 !px-3 text-xs" onClick={reset}>
              Сбросить правки ({changed})
            </button>
          )}
          <button className="btn btn-primary !py-1.5" onClick={download}>
            Скачать ведомость (CSV)
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <DrawingPane
          overrides={overrides}
          highlighted={highlighted}
          onHover={setHoverRun}
          onPick={pickRun}
        />
        <aside className="w-[420px] shrink-0 border-l border-[var(--line)] bg-[var(--bg)] flex flex-col">
          <div className="flex-1 overflow-auto p-4 space-y-3">
            <p className="text-xs text-[var(--muted)] leading-relaxed">
              Клик по строке подсвечивает участки на чертеже, клик по участку — строку. Метка на
              шкале — лимит системы по спецификации.
            </p>
            {summary.map((s) => (
              <SystemCard
                key={s.system}
                summary={s}
                selectedKey={selected?.key ?? null}
                onSelect={setSelected}
                onMove={move}
              />
            ))}
          </div>
          <footer className="border-t border-[var(--line)] bg-[var(--surface)] px-4 py-3 flex items-baseline gap-4">
            <span className="text-xs text-[var(--muted)]">Итого по листу</span>
            <span className="mono text-xl font-bold">{formatM(total)} м</span>
            <span className="text-xs text-[var(--muted)] mono">спец. {formatM(specTotal)} м</span>
            {excludedCount > 0 && <span className="chip chip-low ml-auto">исключено: {excludedCount}</span>}
          </footer>
        </aside>
      </div>
    </div>
  );
}
