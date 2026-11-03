"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { TakeoffSheet } from "@/lib/api";
import { IconBack } from "@/components/ui/icons";
import { DrawingPane } from "./DrawingPane";
import { ScalePanel } from "./ScalePanel";
import { SystemCard } from "./SystemCard";
import {
  EXCLUDED,
  UNKNOWN,
  countFittings,
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
  // confirms or corrects the sheet's scale; the page swaps in the sheet it returns
  onSetScale?: (scale: number) => Promise<void>;
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

export function SheetScreen({ sheet, imageUrl, backHref, onSave, exportHref, onSetScale, isDemo }: Props) {
  const [overrides, setOverrides] = useState<Overrides>(sheet.overrides);
  const [selected, setSelected] = useState<Group | null>(null);
  const [hoverRun, setHoverRun] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [savedOverrides, setSavedOverrides] = useState<Overrides>(sheet.overrides);

  const summary = useMemo(() => summarise(sheet, overrides), [sheet, overrides]);
  const fittingCounts = useMemo(() => countFittings(sheet), [sheet]);
  const sheetTotal = summary.reduce((sum, s) => sum + s.sheetM, 0);
  const excludedCount = Object.values(overrides).filter((v) => v === EXCLUDED).length;
  const changed = Object.keys(overrides).length;

  const highlighted = useMemo<ReadonlySet<number>>(() => {
    if (hoverRun !== null) return new Set([hoverRun]);
    return new Set(selected?.runIds ?? []);
  }, [hoverRun, selected]);

  useEffect(() => {
    if (!onSave || overrides === savedOverrides) return;
    const timer = setTimeout(() => {
      setSaveState("saving");
      onSave(overrides)
        .then(() => {
          setSavedOverrides(overrides);
          setSaveState("saved");
        })
        .catch(() => setSaveState("error"));
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [overrides, onSave, savedOverrides]);

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

  const unknown = summary.find((g) => g.system === UNKNOWN);
  const code = sheet.filename.replace(/\.pdf$/i, "");

  return (
    <div className="flex flex-col h-[calc(100vh-18px)] max-[900px]:h-auto rounded-[var(--radius-sheet)] overflow-hidden">
      <header className="flex items-center gap-4 px-5 h-[60px] max-[640px]:h-auto max-[640px]:py-3 max-[640px]:flex-wrap max-[640px]:gap-y-2 border-b border-[var(--border)] flex-none">
        {backHref && (
          <Link href={backHref} className="btn btn-text -ml-2" aria-label="К проекту">
            <IconBack /> Проект
          </Link>
        )}
        <h1 className="text-[18px] leading-6 font-semibold truncate min-w-0 max-[640px]:order-last max-[640px]:basis-full">
          {sheet.title ?? `Лист ${sheet.page}`}
        </h1>
        <div className="stamp max-[1200px]:hidden" aria-label="Штамп листа">
          <div className="max-w-[220px]"><span className="k">Шифр</span><span className="v" title={sheet.filename}>{code}</span></div>
          <div><span className="k">Лист</span><span className="v num">{sheet.page}</span></div>
          <div><span className="k">Масштаб</span><span className="v num">{sheet.scale ? `1:${sheet.scale}` : "—"}</span></div>
          <div><span className="k">Итого</span><span className="v num">{formatM(sheetTotal)} м</span></div>
        </div>
        {isDemo && <span className="pill pill-neutral">демо-данные</span>}
        <div className="ml-auto flex items-center gap-2 flex-none">
          {saveState !== "idle" && (
            <span className={`text-xs ${saveState === "error" ? "error-line" : "muted"}`} role="status">
              {SAVE_LABEL[saveState]}
            </span>
          )}
          {changed > 0 && (
            <button className="btn btn-secondary" onClick={reset}>
              Сбросить правки ({changed})
            </button>
          )}
          {exportHref ? (
            <a className="btn btn-primary" href={exportHref}>Ведомость XLSX</a>
          ) : (
            <button className="btn btn-primary" onClick={() => downloadCsv(toRuCsv(summary))}>
              Ведомость CSV
            </button>
          )}
        </div>
      </header>

      <div className="flex flex-1 min-h-0 max-[900px]:flex-col">
        <DrawingPane
          sheet={sheet}
          imageUrl={imageUrl}
          overrides={overrides}
          highlighted={highlighted}
          onHover={setHoverRun}
          onPick={pickRun}
        />
        <aside className="w-[400px] max-[900px]:w-full shrink-0 border-l border-[var(--border)] flex flex-col" aria-label="Системы листа">
          <div className="flex-1 overflow-auto p-4 space-y-3">
            {sheet.runs.length > 0 && (
              <ScalePanel
                sheet={sheet}
                editCount={changed}
                canChange={overrides === savedOverrides && saveState !== "saving"}
                onSetScale={onSetScale}
              />
            )}
            <p className="text-sm">
              {unknown
                ? <>Не разнесено <span className="num font-medium">{formatM(unknown.sheetM)} м</span> — выберите строку и перенесите участки в систему.</>
                : <>Все участки листа разнесены по системам.</>}
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
            {fittingCounts.length > 0 && (
              <article className="panel overflow-hidden">
                <header className="panel-head !pb-2.5">
                  <h3>Решётки и клапаны</h3>
                  <span className="meta num">{fittingCounts.reduce((sum, f) => sum + f.count, 0)} шт. на листе</span>
                </header>
                <ul>
                  {fittingCounts.map((f) => (
                    <li key={f.mark} className="flex items-center gap-3 px-4 h-9 text-sm border-t border-[var(--rule)]">
                      <span>{f.mark}</span>
                      <span className="text-xs muted">{f.kind}</span>
                      <span className="num ml-auto">{f.count}</span>
                    </li>
                  ))}
                </ul>
              </article>
            )}
            {summary.length === 0 && (
              <p className="empty">На листе не найдено воздуховодов.</p>
            )}
          </div>
          <footer className="border-t border-[var(--border)] px-4 h-14 flex items-center gap-3 flex-none">
            <span className="text-sm muted">Итого по листу</span>
            <span className="num text-[22px] ml-auto">{formatM(sheetTotal)} <span className="text-sm muted">м</span></span>
            {excludedCount > 0 && <span className="pill pill-neutral">исключено {excludedCount}</span>}
          </footer>
        </aside>
      </div>
    </div>
  );
}
