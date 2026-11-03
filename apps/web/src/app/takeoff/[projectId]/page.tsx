"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { UNKNOWN, formatM, verdict } from "@/components/takeoff/model";
import { ProjectOverview } from "@/components/takeoff/ProjectOverview";
import { api, takeoffExportUrl, type Project, type Takeoff } from "@/lib/api";

const POLL_MS = 1000;

const STEP_LABEL: Record<string, string> = {
  classify: "Определяю листы по штампу",
  spec: "Читаю спецификацию",
  measure: "Измеряю планы",
};

function Progress({ takeoff }: { takeoff: Takeoff }) {
  const p = takeoff.progress;
  const pct = p && p.total > 0 ? Math.round((p.done / p.total) * 100) : 0;
  return (
    <section className="panel max-w-xl" aria-live="polite">
      <header className="panel-head">
        <h2>{p ? STEP_LABEL[p.step] ?? p.step : "Ставлю в очередь"}</h2>
        {p && p.step !== "spec" && <span className="meta num">{p.done} из {p.total}</span>}
      </header>
      <div className="panel-body">
        {p?.document && <p className="text-sm muted mb-3 truncate">{p.document}</p>}
        <div className="h-1.5 rounded-full bg-[var(--active)] overflow-hidden">
          <div className="h-full bg-[var(--text)] transition-[width] duration-300" style={{ width: `${pct}%` }} />
        </div>
        <p className="text-xs muted mt-3">Альбом на сотню листов считается около минуты.</p>
      </div>
    </section>
  );
}

/** The line under the title: the fact that most needs the estimator's attention. */
function finding(takeoff: Takeoff): string {
  const plans = takeoff.sheets.filter((s) => s.kind === "plan");
  const over = takeoff.systems.filter((s) => s.system !== UNKNOWN && verdict(s.measured_m, s.spec_m).isOver);
  const unknown = takeoff.systems.find((s) => s.system === UNKNOWN)?.measured_m ?? 0;
  const parts = [
    over.length > 0
      ? `${over.length} ${over.length === 1 ? "система" : "систем"} сверх спецификации: ${over.slice(0, 3).map((s) => s.system).join(", ")}${over.length > 3 ? "…" : ""}`
      : "Ни одна система не превышает спецификацию",
  ];
  if (unknown > 0) parts.push(`${formatM(unknown)} м не разнесено`);
  parts.push(`${plans.length} ${plans.length === 1 ? "план" : "планов"} из ${takeoff.sheets.length} листов`);
  return parts.join(" · ");
}

export default function TakeoffProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [takeoff, setTakeoff] = useState<Takeoff | null>(null);
  const [notStarted, setNotStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isRunning = !notStarted && (takeoff === null || takeoff.status === "RUNNING");

  useEffect(() => {
    api.getProject(projectId).then(setProject).catch(() => undefined);
  }, [projectId]);

  useEffect(() => {
    if (!isRunning) return;
    let isCancelled = false;
    const poll = () =>
      api
        .getTakeoff(projectId)
        .then((t) => !isCancelled && setTakeoff(t))
        .catch((e: Error) => {
          if (isCancelled) return;
          if (/no takeoff/i.test(e.message)) setNotStarted(true);
          else setError(e.message);
        });
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      isCancelled = true;
      clearInterval(timer);
    };
  }, [projectId, isRunning]);

  async function start() {
    setError(null);
    try {
      setTakeoff(await api.startTakeoff(projectId));
      setNotStarted(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const done = takeoff?.status === "COMPLETED" ? takeoff : null;

  return (
    <div>
      <nav className="crumbs" aria-label="Путь">
        <Link href="/takeoff">Проекты</Link> <span>/</span>
      </nav>
      <div className="page-head">
        <div className="min-w-0">
          <h1 className="truncate">{project?.name ?? "Проект"}</h1>
          <p>{done ? finding(done) : notStarted ? "Расчёт ещё не запускался." : "Идёт расчёт ведомости."}</p>
        </div>
        <div className="actions">
          {(done || takeoff?.status === "FAILED") && (
            <button className="btn btn-secondary" onClick={start}>Пересчитать</button>
          )}
          {done && <a className="btn btn-primary" href={takeoffExportUrl(done.id)}>Ведомость XLSX</a>}
          {notStarted && <button className="btn btn-primary" onClick={start}>Посчитать</button>}
        </div>
      </div>

      {error && (
        <p className="panel p-4 mb-4 text-sm">
          <span className="error-line">Не удалось загрузить расчёт: {error}.</span>{" "}
          <button className="btn btn-text" onClick={() => setError(null)}>Повторить</button>
        </p>
      )}
      {takeoff?.status === "FAILED" && (
        <p className="panel p-4 mb-4 text-sm error-line">{takeoff.error ?? "Расчёт не удался."}</p>
      )}
      {notStarted && (
        <p className="empty">Нажмите «Посчитать», чтобы измерить планы альбома и сверить их со спецификацией.</p>
      )}
      {takeoff && takeoff.status === "RUNNING" && <Progress takeoff={takeoff} />}
      {done && <ProjectOverview projectId={projectId} takeoff={done} />}
    </div>
  );
}
