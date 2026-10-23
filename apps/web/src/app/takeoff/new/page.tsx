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
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold">Ведомость воздуховодов</h1>
      <p className="text-sm text-[var(--muted)] mt-1 mb-6">
        Загрузите альбом ОВ в PDF. Планы будут найдены по штампу и измерены по векторной
        геометрии, итог сверится со спецификацией из того же альбома.{" "}
        <Link href="/takeoff/demo" className="text-[var(--accent)] hover:underline">
          Посмотреть демо
        </Link>
      </p>

      <label className="block mb-5">
        <span className="text-sm text-[var(--muted)]">Название (необязательно)</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Корпус 18 — вентиляция, изм. 3"
          className="mt-1 w-full card px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        />
      </label>

      <div className="grid sm:grid-cols-[3fr_2fr] gap-4 mb-6 items-start">
        <FileDrop
          label="АЛЬБОМ ОВ"
          hint="Планы, схемы и спецификация — одним или несколькими PDF"
          files={files.DRAWING}
          onAdd={(f) => add("DRAWING", f)}
          onRemove={(i) => remove("DRAWING", i)}
        />
        <FileDrop
          label="СПЕЦИФИКАЦИЯ"
          hint="Только если она отдельным файлом"
          files={files.SPECIFICATION}
          onAdd={(f) => add("SPECIFICATION", f)}
          onRemove={(i) => remove("SPECIFICATION", i)}
        />
      </div>

      {error && <div className="card p-3 mb-4 text-sm text-[var(--high)]">{error}</div>}

      <div className="flex items-center gap-4">
        <button className="btn btn-primary" disabled={!canStart} onClick={start}>
          Посчитать
        </button>
        {status && <span className="text-sm text-[var(--muted)]">{status}</span>}
      </div>
    </div>
  );
}
