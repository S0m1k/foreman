"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { FileDrop } from "@/components/takeoff/FileDrop";
import { api } from "@/lib/api";

type Slot = "DRAWING" | "SPECIFICATION";

function addUnique(existing: File[], added: File[]): File[] {
  return [...existing, ...added.filter((f) => !existing.some((e) => e.name === f.name && e.size === f.size))];
}

export default function NewTakeoff() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<Slot, File[]>>({ DRAWING: [], SPECIFICATION: [] });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isBusy = status !== null;
  const canStart = files.DRAWING.length > 0 && !isBusy;

  const add = (slot: Slot, added: File[]) =>
    setFiles((prev) => ({ ...prev, [slot]: addUnique(prev[slot], added) }));
  const remove = (slot: Slot, index: number) =>
    setFiles((prev) => ({ ...prev, [slot]: prev[slot].filter((_, i) => i !== index) }));

  async function start() {
    if (!canStart) return;
    setError(null);
    try {
      setStatus("Создаю проект…");
      const project = await api.createProject(name.trim() || files.DRAWING[0].name.replace(/\.pdf$/i, ""));
      const uploads: Array<[Slot, File]> = [
        ...files.DRAWING.map((f): [Slot, File] => ["DRAWING", f]),
        ...files.SPECIFICATION.map((f): [Slot, File] => ["SPECIFICATION", f]),
      ];
      for (const [i, [slot, file]] of uploads.entries()) {
        setStatus(`Загружаю ${i + 1} из ${uploads.length}: ${file.name}`);
        await api.uploadDocument(project.id, slot, file);
      }
      setStatus("Запускаю расчёт…");
      await api.startTakeoff(project.id);
      router.push(`/takeoff/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
      setStatus(null);
    }
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Новая ведомость</h1>
          <p>Альбом ОВ в PDF: планы найдутся по штампу, воздуховоды измерятся по геометрии, итог сверится со спецификацией.</p>
        </div>
      </div>

      {/* 1fr + 16 + 360: the form beside what it produces */}
      <div className="grid grid-cols-[minmax(0,1fr)_360px] max-[1000px]:grid-cols-1 gap-4 items-start">
        <section className="panel">
          <div className="panel-body !pt-5 space-y-5">
            <label className="field">
              <span>Название</span>
              <input
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Корпус 18 — вентиляция, изм. 3"
                aria-describedby="name-hint"
              />
              <small id="name-hint">Необязательно: по умолчанию — имя файла альбома.</small>
            </label>
            <FileDrop
              label="Альбом ОВ"
              hint="Планы, схемы и спецификация — одним или несколькими PDF"
              files={files.DRAWING}
              onAdd={(f) => add("DRAWING", f)}
              onRemove={(i) => remove("DRAWING", i)}
              isMain
            />
            <FileDrop
              label="Спецификация отдельным файлом"
              hint="Только если её нет в альбоме"
              files={files.SPECIFICATION}
              onAdd={(f) => add("SPECIFICATION", f)}
              onRemove={(i) => remove("SPECIFICATION", i)}
            />
            {error && <p className="text-sm error-line">{error}</p>}
            <div className="flex items-center gap-4">
              <button className="btn btn-primary btn-lg" disabled={!canStart} onClick={start}>
                Посчитать
              </button>
              {status && <span className="text-sm muted" role="status">{status}</span>}
            </div>
          </div>
        </section>

        <aside className="panel">
          <header className="panel-head"><h2>Что получится</h2></header>
          <ul className="panel-body space-y-3 text-sm">
            <li><span className="font-medium">Ведомость воздуховодов</span> — система, сечение, изоляция, длина по каждому плану.</li>
            <li><span className="font-medium">Решётки и клапаны</span> — счёт по подписям на планах.</li>
            <li><span className="font-medium">Сверка со спецификацией</span> — где измерено больше, чем заложено на всё здание.</li>
            <li><span className="font-medium">Правки на чертеже</span> — перенос участков между системами, выгрузка в Excel.</li>
            <li><Link href="/takeoff/demo" className="btn btn-secondary mt-1">Открыть демо-лист</Link></li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
