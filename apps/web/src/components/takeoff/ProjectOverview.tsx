import Link from "next/link";
import type { SheetKind, SystemTotal, Takeoff, TakeoffSheetSummary } from "@/lib/api";
import { UNKNOWN, formatM, naturalOrder, systemColour, verdict } from "./model";

interface Props {
  projectId: string;
  takeoff: Takeoff;
  exportHref: string;
}

const SKIPPED_LABEL: Record<Exclude<SheetKind, "plan">, string> = {
  schematic: "схемы",
  specification: "спецификация",
  other: "прочие листы",
};

function PlanCard({ projectId, sheet }: { projectId: string; sheet: TakeoffSheetSummary }) {
  const href = `/takeoff/${projectId}/sheet/${sheet.document_id}/${sheet.page}`;
  const isEmpty = sheet.run_count === 0;
  return (
    <Link href={href} className="card card-hover block p-4">
      <p className="font-semibold leading-snug">{sheet.title ?? `Лист ${sheet.page}`}</p>
      <p className="text-xs text-[var(--muted)] mt-1 truncate">
        лист {sheet.page} · {sheet.filename}
      </p>
      <div className="flex items-baseline gap-3 mt-4">
        <span className={`mono text-2xl font-bold ${isEmpty ? "text-[var(--muted)]" : ""}`}>
          {formatM(sheet.length_m)} м
        </span>
        <span className="text-xs text-[var(--muted)]">{sheet.run_count} участков</span>
        {sheet.scale && <span className="chip chip-review ml-auto">1:{sheet.scale}</span>}
      </div>
      {isEmpty && (
        <p className="text-xs text-[var(--medium)] mt-2">
          Воздуховоды не найдены — возможно, они нарисованы цветом вне палитры.
        </p>
      )}
    </Link>
  );
}

function SkippedSheets({ sheets }: { sheets: TakeoffSheetSummary[] }) {
  const byKind = Object.entries(SKIPPED_LABEL).map(([kind, label]) => ({
    label,
    sheets: sheets.filter((s) => s.kind === kind),
  }));
  return (
    <details className="card p-4 text-sm">
      <summary className="cursor-pointer text-[var(--muted)]">
        Не измеряются:{" "}
        {byKind
          .filter((k) => k.sheets.length > 0)
          .map((k) => `${k.label} — ${k.sheets.length}`)
          .join(", ")}
      </summary>
      <ul className="mt-3 space-y-1 max-h-72 overflow-auto">
        {byKind.flatMap((k) =>
          k.sheets.map((s) => (
            <li key={`${s.document_id}:${s.page}`} className="flex gap-3">
              <span className="mono text-[var(--muted)] w-10 text-right">{s.page}</span>
              <span className="text-[var(--muted)] w-28">{k.label}</span>
              <span className="truncate">{s.title ?? "—"}</span>
            </li>
          )),
        )}
      </ul>
    </details>
  );
}

function rank(system: SystemTotal): number {
  const v = verdict(system.measured_m, system.spec_m);
  if (system.system === UNKNOWN) return 3;
  return v.isOver ? 0 : system.spec_m === null ? 1 : 2;
}

function SystemsTable({ systems }: { systems: SystemTotal[] }) {
  const ordered = [...systems].sort(
    (a, b) => rank(a) - rank(b) || naturalOrder(a.system, b.system),
  );
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-xs text-[var(--muted)] text-left">
          <th className="font-normal py-2">Система</th>
          <th className="font-normal text-right">Измерено, м</th>
          <th className="font-normal text-right">По спец., м</th>
          <th className="font-normal text-right">Сверка</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-[var(--line)]">
        {ordered.map((s) => {
          const v = verdict(s.measured_m, s.spec_m);
          return (
            <tr key={s.system}>
              <td className="py-1.5 mono font-semibold" style={{ color: systemColour(s.system) }}>
                {s.system}
              </td>
              <td className="mono text-right">{formatM(s.measured_m)}</td>
              <td className="mono text-right text-[var(--muted)]">
                {s.spec_m === null ? "—" : formatM(s.spec_m)}
              </td>
              <td className="text-right">
                {s.system === UNKNOWN ? (
                  <span className="chip chip-medium">разобрать</span>
                ) : (
                  <span className={`chip ${v.tone}`}>{v.label}</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function ProjectOverview({ projectId, takeoff, exportHref }: Props) {
  const plans = takeoff.sheets.filter((s) => s.kind === "plan");
  const skipped = takeoff.sheets.filter((s) => s.kind !== "plan");
  const total = plans.reduce((sum, s) => sum + s.length_m, 0);
  const overCount = takeoff.systems.filter((s) => verdict(s.measured_m, s.spec_m).isOver).length;

  return (
    <div className="grid lg:grid-cols-[1fr_380px] gap-8 items-start">
      <section>
        <div className="flex items-baseline gap-4 mb-4">
          <h2 className="text-lg font-bold">Планы</h2>
          <span className="text-sm text-[var(--muted)]">
            {plans.length} из {takeoff.sheets.length} листов · всего{" "}
            <span className="mono text-[var(--text)]">{formatM(total)} м</span>
          </span>
        </div>
        {plans.length === 0 ? (
          <p className="card p-4 text-sm text-[var(--muted)]">
            В альбоме не найдено листов с заголовком «План…».
          </p>
        ) : (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 mb-4">
            {plans.map((s) => (
              <PlanCard key={`${s.document_id}:${s.page}`} projectId={projectId} sheet={s} />
            ))}
          </div>
        )}
        {skipped.length > 0 && <SkippedSheets sheets={skipped} />}
      </section>

      <aside className="card p-4 lg:sticky lg:top-20">
        <div className="flex items-baseline justify-between mb-1">
          <h2 className="font-bold">Сверка со спецификацией</h2>
          {overCount > 0 && <span className="chip chip-high">{overCount} сверх</span>}
        </div>
        <p className="text-xs text-[var(--muted)] mb-3">
          Спецификация — на всё здание, поэтому превышение всегда ошибка, а «ещё N м» значит,
          что остальное на неизмеренных листах.
        </p>
        <div className="max-h-[60vh] overflow-auto">
          <SystemsTable systems={takeoff.systems} />
        </div>
        <a href={exportHref} className="btn btn-primary w-full justify-center mt-4">
          Ведомость (XLSX)
        </a>
      </aside>
    </div>
  );
}
