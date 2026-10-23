"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { TakeoffSheet } from "@/lib/api";
import { DrawingPane } from "./DrawingPane";
import { SystemCard } from "./SystemCard";
import {
  EXCLUDED,
  formatM,
  moveTargets,
  summarise,
  toRuCsv,
  type Group,
  type Overrides,
} from "./model";

type SaveState = "idle" | "saving" | "saved" | "error";

interface Props {
  sheet: TakeoffSheet;
  imageUrl: string;
  backHref?: string;
  // persists the sheet's edits; without it edits live only in the page
  onSave?: (overrides: Overrides) => Promise<void>;
  // the project's XLSX; without it the sheet downloads as CSV
  exportHref?: string;
  isDemo?: boolean;
}

const SAVE_DELAY_MS = 500;

const SAVE_LABEL: Record<SaveState, string> = {
  idle: "",
  saving: "сохраняю…",
  saved: "правки сохранены",
  error: "не сохранилось — повторю при следующей правке",
};

function downloadCsv(text: string) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ведомость-воздуховодов.csv";
  link.click();
  URL.revokeObjectURL(url);
}

export function SheetScreen({ sheet, imageUrl, backHref, onSave, exportHref, isDemo }: Props) {
  const [overrides, setOverrides] = useState<Overrides>(sheet.overrides);
  const [selected, setSelected] = useState<Group | null>(null);
  const [hoverRun, setHoverRun] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const lastSaved = useRef<Overrides>(sheet.overrides);

  const summary = useMemo(() => summarise(sheet, overrides), [sheet, overrides]);
  const sheetTotal = summary.reduce((sum, s) => sum + s.sheetM, 0);
  const excludedCount = Object.values(overrides).filter((v) => v === EXCLUDED).length;
  const changed = Object.keys(overrides).length;

  const highlighted = useMemo<ReadonlySet<number>>(() => {
    if (hoverRun !== null) return new Set([hoverRun]);
    return new Set(selected?.runIds ?? []);
  }, [hoverRun, selected]);

  useEffect(() => {
    if (!onSave || overrides === lastSaved.current) return;
    const timer = setTimeout(() => {
      setSaveState("saving");
      onSave(overrides)
        .then(() => {
          lastSaved.current = overrides;
          setSaveState("saved");
        })
        .catch(() => setSaveState("error"));
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [overrides, onSave]);

  const move = (group: Group, target: string) => {
    setOverrides((prev) => ({
      ...prev,
      ...Object.fromEntries(group.runIds.map((id) => [String(id), target])),
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

  return (
    <div className="relative left-1/2 w-screen -translate-x-1/2 -my-8 flex flex-col h-[calc(100vh-48px)]">
      <div className="flex items-center gap-3 px-5 py-2.5 border-b border-[var(--line)] bg-[var(--surface)]">
        {backHref && (
          <Link href={backHref} className="text-[var(--muted)] hover:text-[var(--text)] text-sm" title="К листам">
            ← листы
          </Link>
        )}
        <span className="mono text-sm truncate max-w-[28ch]" title={sheet.filename}>{sheet.filename}</span>
        <span className="text-xs text-[var(--muted)]">
          лист {sheet.page}
          {sheet.title ? ` · ${sheet.title}` : ""}
        </span>
        {sheet.scale && (
          <span className="chip chip-review" title="Масштаб найден по типовым сечениям воздуховодов">
            М 1:{sheet.scale} · авто
          </span>
        )}
        {isDemo && <span className="chip chip-low">демо-данные</span>}
        <div className="ml-auto flex items-center gap-3">
          {saveState !== "idle" && (
            <span className={`text-xs ${saveState === "error" ? "text-[var(--high)]" : "text-[var(--muted)]"}`}>
              {SAVE_LABEL[saveState]}
            </span>
          )}
          {changed > 0 && (
            <button className="btn btn-ghost !py-1 !px-3 text-xs" onClick={reset}>
              Сбросить правки ({changed})
            </button>
          )}
          {exportHref ? (
            <a className="btn btn-primary !py-1.5" href={exportHref}>
              Ведомость по проекту (XLSX)
            </a>
          ) : (
            <button className="btn btn-primary !py-1.5" onClick={() => downloadCsv(toRuCsv(summary))}>
              Скачать ведомость (CSV)
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <DrawingPane
          sheet={sheet}
          imageUrl={imageUrl}
          overrides={overrides}
          highlighted={highlighted}
          onHover={setHoverRun}
          onPick={pickRun}
        />
        <aside className="w-[420px] shrink-0 border-l border-[var(--line)] bg-[var(--bg)] flex flex-col">
          <div className="flex-1 overflow-auto p-4 space-y-3">
            <p className="text-xs text-[var(--muted)] leading-relaxed">
              Клик по строке подсвечивает участки на чертеже, клик по участку — строку. Полоса —
              система по всему проекту: бледная часть на других листах, яркая на этом, метка —
              лимит спецификации.
            </p>
            {summary.map((s) => (
              <SystemCard
                key={s.system}
                summary={s}
                targets={moveTargets(sheet, s.system)}
                selectedKey={selected?.key ?? null}
                onSelect={setSelected}
                onMove={move}
              />
            ))}
            {summary.length === 0 && (
              <p className="text-sm text-[var(--muted)]">На листе не найдено воздуховодов.</p>
            )}
          </div>
          <footer className="border-t border-[var(--line)] bg-[var(--surface)] px-4 py-3 flex items-baseline gap-4">
            <span className="text-xs text-[var(--muted)]">Итого по листу</span>
            <span className="mono text-xl font-bold">{formatM(sheetTotal)} м</span>
            {excludedCount > 0 && <span className="chip chip-low ml-auto">исключено: {excludedCount}</span>}
          </footer>
        </aside>
      </div>
    </div>
  );
}
