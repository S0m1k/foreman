"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
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
    <div className="card p-6 max-w-xl">
      <p className="font-semibold">{p ? STEP_LABEL[p.step] ?? p.step : "Ставлю в очередь"}</p>
      {p && (
        <p className="text-sm text-[var(--muted)] mt-1">
          {p.step !== "spec" && <span className="mono">{p.done} из {p.total}</span>}
          {p.document && <span> · {p.document}</span>}
        </p>
      )}
      <div className="h-1.5 rounded-full bg-[var(--surface-2)] mt-4 overflow-hidden">
        <div className="h-full bg-[var(--accent)] transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-[var(--muted)] mt-3">Альбом на сотню листов считается около минуты.</p>
    </div>
  );
}

export default function TakeoffProjectPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [takeoff, setTakeoff] = useState<Takeoff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isRunning = takeoff === null || takeoff.status === "RUNNING";

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
        .catch((e: Error) => !isCancelled && setError(e.message));
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      isCancelled = true;
      clearInterval(timer);
    };
  }, [projectId, isRunning]);

  async function retry() {
    setError(null);
    try {
      setTakeoff(await api.startTakeoff(projectId));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <Link href="/takeoff/new" className="text-sm text-[var(--muted)] hover:text-[var(--text)]">
          ← новый расчёт
        </Link>
        <h1 className="text-2xl font-bold mt-2">{project?.name ?? "Ведомость воздуховодов"}</h1>
      </div>

      {error && <div className="card p-4 mb-4 text-sm text-[var(--high)]">{error}</div>}
      {takeoff?.status === "FAILED" && (
        <div className="card p-4 mb-4 text-sm">
          <p className="text-[var(--high)]">{takeoff.error ?? "Расчёт не удался."}</p>
          <button className="btn btn-ghost mt-3" onClick={retry}>
            Повторить
          </button>
        </div>
      )}
      {takeoff && takeoff.status === "RUNNING" && <Progress takeoff={takeoff} />}
      {takeoff?.status === "COMPLETED" && (
        <ProjectOverview projectId={projectId} takeoff={takeoff} exportHref={takeoffExportUrl(takeoff.id)} />
      )}
    </div>
  );
}
