"use client";

import Link from "next/link";
import { useState } from "react";
import { api, type FittingTotal, type ReviewItem, type Takeoff } from "@/lib/api";
import { formatM, plural } from "./model";

interface Props {
  projectId: string;
  takeoff: Takeoff;
  onUpdate: (takeoff: Takeoff) => void;
}

const RUNS = ["участок", "участка", "участков"] as const;

function describe(item: ReviewItem, fittings: FittingTotal[]): string {
  const n = item.count ?? 0;
  const m = formatM(item.length_m ?? 0);
  switch (item.kind) {
    case "scale":
      return `Масштаб 1:${item.scale} не подтверждён`;
    case "unassigned":
      return `Не разнесено ${m} м — ${n} ${plural(n, RUNS)}`;
    case "section":
      return `Сечение не прочитано: ${m} м — ${n} ${plural(n, RUNS)}`;
    case "no_runs":
      return "Воздуховоды не найдены — проверьте, план ли это";
    case "over_spec":
      return `${item.system} сверх спецификации на ${m} м`;
    case "fitting": {
      const spec = fittings.find((f) => f.mark === item.mark)?.spec;
      return spec == null
        ? `${item.mark}: нет в спецификации, на планах ${n} шт.`
        : `${item.mark}: на планах на ${n} шт. больше спецификации`;
    }
  }
}

const sheetHref = (projectId: string, item: ReviewItem) =>
  `/takeoff/${projectId}/sheet/${item.document_id}/${item.page}`;

function Row({ item, projectId, takeoff, isBusy, onScale, onReviewed }: {
  item: ReviewItem;
  projectId: string;
  takeoff: Takeoff;
  isBusy: boolean;
  onScale: (item: ReviewItem) => void;
  onReviewed: (item: ReviewItem, reviewed: boolean) => void;
}) {
  const hasSheet = item.document_id !== null && item.page !== null;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 min-h-12 py-2 border-t border-[var(--rule)] text-sm">
      <span className={`dot flex-none ${item.can_dismiss ? "bg-[var(--warning)]" : "bg-[var(--negative)]"}`} aria-hidden />
      <span className="min-w-[200px] flex-1">
        <span className={item.is_reviewed ? "muted line-through decoration-[var(--faint)]" : ""}>
          {describe(item, takeoff.fittings)}
        </span>
        {hasSheet && (
          <Link href={sheetHref(projectId, item)} className="block text-xs muted truncate hover:underline">
            Лист {item.page} · {item.sheet_title ?? "без заголовка"}
          </Link>
        )}
      </span>
      {item.kind === "scale" && (
        <>
          <Link href={sheetHref(projectId, item)} className="btn btn-text flex-none max-[640px]:hidden">Сверить</Link>
          <button className="btn btn-secondary flex-none" disabled={isBusy} onClick={() => onScale(item)}>
            Подтвердить 1:{item.scale}
          </button>
        </>
      )}
      {item.kind === "unassigned" && (
        <Link href={sheetHref(projectId, item)} className="btn btn-secondary flex-none">Разнести</Link>
      )}
      {item.can_dismiss && (
        <button className="btn btn-text flex-none" disabled={isBusy} onClick={() => onReviewed(item, !item.is_reviewed)}>
          {item.is_reviewed ? "Вернуть" : "Проверено"}
        </button>
      )}
    </li>
  );
}

export function ReviewQueue({ projectId, takeoff, onUpdate }: Props) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const open = takeoff.review.filter((i) => !i.is_reviewed);
  const done = takeoff.review.filter((i) => i.is_reviewed);
  // a mark per row would bury the sheets' items: the album has dozens of them
  const openMarks = open.filter((i) => i.kind === "fitting");
  const openRest = open.filter((i) => i.kind !== "fitting");

  async function act(item: ReviewItem, call: () => Promise<Takeoff>) {
    setBusyKey(item.key);
    setError(null);
    try {
      onUpdate(await call());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyKey(null);
    }
  }
  const confirmScale = (item: ReviewItem) =>
    act(item, async () => {
      await api.setTakeoffScale(takeoff.id, item.document_id!, item.page!, item.scale!);
      return api.getTakeoff(projectId);
    });
  const markReviewed = (item: ReviewItem, reviewed: boolean) =>
    act(item, () => api.setReviewed(takeoff.id, item.key, reviewed));

  const row = (item: ReviewItem) => (
    <Row key={item.key} item={item} projectId={projectId} takeoff={takeoff}
      isBusy={busyKey === item.key} onScale={confirmScale} onReviewed={markReviewed} />
  );

  return (
    <section className="panel flex flex-col max-h-[520px]" aria-label="Проверка">
      <header className="panel-head">
        <h2>Проверка</h2>
        <span className="meta num">
          {open.length > 0 ? `${open.length} ${plural(open.length, ["место", "места", "мест"])} на проверку` : "всё проверено"}
        </span>
      </header>
      {error && <p className="px-5 pb-3 text-sm error-line">{error}</p>}
      <div className="overflow-auto min-h-0">
        {open.length === 0 && (
          <p className="empty mx-5 mb-4">Спорных мест не осталось — ведомость можно выгружать.</p>
        )}
        {openRest.length > 0 && <ul>{openRest.map(row)}</ul>}
        {openMarks.length > 0 && (
          <details className="border-t border-[var(--rule)]">
            <summary className="px-5 min-h-12 flex items-center gap-3 text-sm cursor-pointer hover:bg-[var(--raised)]">
              <span className="dot flex-none bg-[var(--warning)]" aria-hidden />
              <span>
                Решётки и клапаны расходятся со спецификацией:{" "}
                <span className="num">{openMarks.length}</span> {plural(openMarks.length, ["марка", "марки", "марок"])}
              </span>
              <span className="text-xs muted ml-auto">раскрыть</span>
            </summary>
            <ul>{openMarks.map(row)}</ul>
          </details>
        )}
        {done.length > 0 && (
          <details className="border-t border-[var(--rule)]">
            <summary className="px-5 h-11 flex items-center gap-3 text-sm cursor-pointer hover:bg-[var(--raised)]">
              <span className="muted">Проверено</span>
              <span className="num muted ml-auto">{done.length}</span>
            </summary>
            <ul>{done.map(row)}</ul>
          </details>
        )}
      </div>
    </section>
  );
}
