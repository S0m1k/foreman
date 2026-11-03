"use client";

import { useState } from "react";
import type { TakeoffSheet } from "@/lib/api";

interface Props {
  sheet: TakeoffSheet;
  // run edits the sheet holds; a correction measures it again and drops them
  editCount: number;
  // false while an edit is still on its way to the server
  canChange: boolean;
  // without it (the demo) the scale is shown, not settled
  onSetScale?: (scale: number) => Promise<void>;
}

// HVAC plans are drawn at 1:50-1:200; the rest covers details and site plans
const SCALES = [25, 50, 75, 100, 150, 200, 250, 500];

export function ScalePanel({ sheet, editCount, canChange, onSetScale }: Props) {
  const current = sheet.scale ?? 100;
  const [isEditing, setIsEditing] = useState(false);
  const [choice, setChoice] = useState(current);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isCorrection = choice !== current;
  const options = SCALES.includes(current) ? SCALES : [...SCALES, current].sort((a, b) => a - b);

  async function submit() {
    if (!onSetScale) return;
    setIsBusy(true);
    setError(null);
    try {
      await onSetScale(choice);
      setIsEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsBusy(false);
    }
  }

  if (sheet.scale_confirmed && !isEditing) {
    return (
      <div className="text-sm">
        <div className="flex items-center gap-2">
          <span>Масштаб <span className="num font-medium">1:{current}</span></span>
          <span className="pill pill-positive">подтверждён</span>
          {onSetScale && (
            <button className="btn btn-text ml-auto" onClick={() => setIsEditing(true)}>Изменить</button>
          )}
        </div>
        {sheet.detected_scale && sheet.detected_scale !== current && (
          <p className="text-xs muted mt-0.5">По чертежу читался 1:{sheet.detected_scale}</p>
        )}
      </div>
    );
  }

  return (
    <section className="panel" aria-label="Масштаб листа">
      <header className="panel-head !pb-2">
        <h3>Масштаб листа</h3>
        {!sheet.scale_confirmed && <span className="pill pill-warning ml-auto">не подтверждён</span>}
      </header>
      <div className="px-4 pb-4 space-y-3">
        <p className="text-sm muted">
          {sheet.scale_confirmed
            ? "Другой масштаб перемерит лист заново."
            : <>Прочитан по чертежу: <span className="num text-[var(--text)]">1:{current}</span>. Сверьте со штампом — от масштаба зависят все длины листа.</>}
        </p>
        {onSetScale ? (
          <div className="flex items-center gap-2">
            <select
              className="input-sm w-[96px]"
              aria-label="Масштаб"
              value={choice}
              disabled={isBusy}
              onChange={(e) => setChoice(Number(e.target.value))}
            >
              {options.map((s) => <option key={s} value={s}>1:{s}</option>)}
            </select>
            <button className="btn btn-secondary" disabled={isBusy || !canChange} onClick={submit}>
              {isBusy ? (isCorrection ? "Перемеряю…" : "Сохраняю…") : isCorrection ? `Перемерить в 1:${choice}` : "Подтвердить"}
            </button>
            {sheet.scale_confirmed && !isBusy && (
              <button className="btn btn-text" onClick={() => { setIsEditing(false); setChoice(current); }}>Отмена</button>
            )}
          </div>
        ) : (
          <p className="text-xs muted">В демо масштаб не меняется.</p>
        )}
        {isCorrection && editCount > 0 && (
          <p className="text-xs text-[var(--warning)]">Правки листа ({editCount}) сбросятся: участки измерятся заново.</p>
        )}
        {error && <p className="text-xs error-line">{error}</p>}
      </div>
    </section>
  );
}
