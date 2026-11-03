import Link from "next/link";
import type {
  FittingTotal,
  SheetKind,
  SystemTotal,
  Takeoff,
  TakeoffSheetSummary,
} from "@/lib/api";
import { UNKNOWN, formatM, naturalOrder, systemColour, verdict } from "./model";
import { ReviewQueue } from "./ReviewQueue";

interface Props {
  projectId: string;
  takeoff: Takeoff;
  onUpdate: (takeoff: Takeoff) => void;
}

const SKIPPED_LABEL: Record<Exclude<SheetKind, "plan">, string> = {
  schematic: "Схемы",
  specification: "Спецификация",
  other: "Прочие листы",
};

/** Over the specification first, then not in it, then the rest in system order. */
function rank(system: SystemTotal): number {
  if (system.system === UNKNOWN) return 3;
  const v = verdict(system.measured_m, system.spec_m);
  return v.isOver ? 0 : !system.spec_m ? 1 : 2;
}

function countVerdict(counted: number, spec: number | null) {
  if (spec === null) return { label: "нет в спец.", tone: "pill-warning" };
  if (counted > spec) return { label: `+${counted - spec} сверх`, tone: "pill-negative" };
  if (counted === spec) return { label: "сходится", tone: "pill-positive" };
  return { label: `ещё ${spec - counted}`, tone: "pill-neutral" };
}

function Kpis({ takeoff, plans }: { takeoff: Takeoff; plans: TakeoffSheetSummary[] }) {
  const total = plans.reduce((sum, s) => sum + s.length_m, 0);
  const over = takeoff.systems.filter((s) => s.system !== UNKNOWN && verdict(s.measured_m, s.spec_m).isOver).length;
  const unknown = takeoff.systems.find((s) => s.system === UNKNOWN)?.measured_m ?? 0;
  const counted = takeoff.fittings.reduce((sum, f) => sum + f.counted, 0);
  const specified = takeoff.fittings.reduce((sum, f) => sum + (f.spec ?? 0), 0);
  const cells = [
    { label: "Воздуховоды на планах", value: <>{formatM(total)} <small>м</small></>, lead: true },
    { label: "Систем сверх спецификации", value: over, tone: over > 0 ? "text-[var(--negative)]" : "" },
    { label: "Не разнесено по системам", value: <>{formatM(unknown)} <small>м</small></> },
    { label: "Решётки и клапаны", value: <>{counted} <small>из {specified} по спец.</small></> },
  ];
  return (
    <div className="panel grid grid-cols-4 max-[900px]:grid-cols-2 mb-4">
      {cells.map((c, i) => (
        <div key={c.label} className={`px-5 py-4 ${i > 0 ? "border-l border-[var(--border)]" : ""} max-[900px]:[&:nth-child(3)]:border-l-0`}>
          <div className="text-xs muted">{c.label}</div>
          <div className={`num mt-1 ${c.lead ? "text-[28px] leading-9" : "text-[22px] leading-9"} ${c.tone ?? ""} [&_small]:text-sm [&_small]:leading-5 [&_small]:text-[var(--muted)]`}>
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function PlansTable({ projectId, plans }: { projectId: string; plans: TakeoffSheetSummary[] }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Планы</h2>
        <span className="meta">измеряются по геометрии; откройте лист, чтобы проверить разнесение</span>
      </header>
      {plans.length === 0 ? (
        <div className="panel-body"><p className="empty">В альбоме не найдено листов с заголовком «План…».</p></div>
      ) : (
        <table className="table">
          <thead>
            <tr><th>Лист</th><th className="num">№</th><th className="num">Масштаб</th><th className="num max-[640px]:hidden">Участков</th><th className="num">Длина, м</th></tr>
          </thead>
          <tbody>
            {plans.map((s) => (
              <tr key={`${s.document_id}:${s.page}`}>
                <td className="max-w-0 w-1/2">
                  <Link className="block truncate font-medium hover:underline" href={`/takeoff/${projectId}/sheet/${s.document_id}/${s.page}`}>
                    {s.title ?? `Лист ${s.page}`}
                  </Link>
                  {s.run_count === 0 && <div className="text-xs muted">воздуховоды не найдены</div>}
                </td>
                <td className="num">{s.page}</td>
                <td className="num">{s.scale ? `1:${s.scale}` : <span className="dash">—</span>}</td>
                <td className="num max-[640px]:hidden">{s.run_count}</td>
                <td className="num font-medium">{formatM(s.length_m)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function SystemsTable({ systems }: { systems: SystemTotal[] }) {
  const ordered = [...systems].sort((a, b) => rank(a) - rank(b) || naturalOrder(a.system, b.system));
  return (
    <section className="panel flex flex-col max-h-[560px]">
      <header className="panel-head">
        <h2>Сверка со спецификацией</h2>
        <span className="meta num">{systems.length} систем</span>
      </header>
      <p className="px-5 pb-3 text-xs muted">
        Спецификация — на всё здание: превышение — ошибка, «ещё N м» — остаток на неизмеренных листах.
      </p>
      <div className="overflow-auto min-h-0">
        <table className="table">
          <thead className="sticky top-0 bg-[var(--surface)]">
            <tr><th>Система</th><th className="num">Измерено</th><th className="num max-[640px]:hidden">По спец.</th><th className="text-right">Сверка</th></tr>
          </thead>
          <tbody>
            {ordered.map((s) => {
              const v = verdict(s.measured_m, s.spec_m);
              return (
                <tr key={s.system}>
                  <td>
                    <span className="inline-flex items-center gap-2 font-medium">
                      <span className="dot" style={{ background: systemColour(s.system) }} />
                      {s.system}
                    </span>
                  </td>
                  <td className="num">{formatM(s.measured_m)}</td>
                  <td className="num max-[640px]:hidden">{s.spec_m ? formatM(s.spec_m) : <span className="dash">—</span>}</td>
                  <td className="text-right">
                    {s.system === UNKNOWN
                      ? <span className="pill pill-warning">разнести</span>
                      : <span className={`pill ${v.tone}`}>{v.label}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FittingsTable({ fittings }: { fittings: FittingTotal[] }) {
  return (
    <section className="panel flex flex-col max-h-[480px]">
      <header className="panel-head">
        <h2>Решётки и клапаны</h2>
        <span className="meta">подписи на планах против строк спецификации</span>
      </header>
      {fittings.length === 0 ? (
        <div className="panel-body"><p className="empty">На планах нет подписей решёток и клапанов.</p></div>
      ) : (
        <div className="overflow-auto min-h-0">
          <table className="table">
            <thead className="sticky top-0 bg-[var(--surface)]">
              <tr><th>Элемент</th><th className="max-[640px]:hidden">Тип</th><th className="num">На планах</th><th className="num">По спец.</th><th className="text-right">Сверка</th></tr>
            </thead>
            <tbody>
              {fittings.map((f) => {
                const v = countVerdict(f.counted, f.spec);
                return (
                  <tr key={f.mark}>
                    <td className="font-medium whitespace-nowrap max-[640px]:whitespace-normal max-[640px]:break-all">{f.mark}</td>
                    <td className="muted max-[640px]:hidden">{f.kind}</td>
                    <td className="num">{f.counted}</td>
                    <td className="num">{f.spec ?? <span className="dash">—</span>}</td>
                    <td className="text-right"><span className={`pill ${v.tone}`}>{v.label}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SkippedSheets({ sheets }: { sheets: TakeoffSheetSummary[] }) {
  const byKind = Object.entries(SKIPPED_LABEL)
    .map(([kind, label]) => ({ kind, label, sheets: sheets.filter((s) => s.kind === kind) }))
    .filter((k) => k.sheets.length > 0);
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>Не измеряются</h2>
        <span className="meta num">{sheets.length} листов</span>
      </header>
      <ul className="pb-2">
        {byKind.map((k) => (
          <li key={k.kind} className="border-t border-[var(--rule)]">
            <details>
              <summary className="flex items-center gap-3 px-5 h-11 cursor-pointer hover:bg-[var(--raised)]">
                <span className="font-medium">{k.label}</span>
                <span className="num muted ml-auto">{k.sheets.length}</span>
              </summary>
              <ul className="px-5 pb-3 text-sm max-h-56 overflow-auto">
                {k.sheets.map((s) => (
                  <li key={`${s.document_id}:${s.page}`} className="flex gap-3 py-1">
                    <span className="num muted w-8 text-right flex-none">{s.page}</span>
                    <span className="truncate">{s.title ?? "без заголовка"}</span>
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ProjectOverview({ projectId, takeoff, onUpdate }: Props) {
  const plans = takeoff.sheets.filter((s) => s.kind === "plan");
  const skipped = takeoff.sheets.filter((s) => s.kind !== "plan");
  return (
    <>
      <Kpis takeoff={takeoff} plans={plans} />
      {/* two columns, each a stack, so both end on their content: 1fr + 16 + 460 */}
      <div className="grid grid-cols-[minmax(0,1fr)_460px] max-[1100px]:grid-cols-1 gap-4 items-start">
        <div className="flex flex-col gap-4 min-w-0">
          <ReviewQueue projectId={projectId} takeoff={takeoff} onUpdate={onUpdate} />
          <PlansTable projectId={projectId} plans={plans} />
          <FittingsTable fittings={takeoff.fittings ?? []} />
        </div>
        <div className="flex flex-col gap-4 min-w-0">
          <SystemsTable systems={takeoff.systems} />
          {skipped.length > 0 && <SkippedSheets sheets={skipped} />}
        </div>
      </div>
    </>
  );
}
