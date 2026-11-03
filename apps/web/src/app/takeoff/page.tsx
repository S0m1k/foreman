"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";

// 20.10.2026: short enough to stay on one line in a phone column
const dateFmt = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });

export default function TakeoffProjects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    api.listProjects().then(setProjects).catch((e: Error) => setError(e.message));
  };
  useEffect(load, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Проекты</h1>
          <p>{projects ? `${projects.length} ${projects.length === 1 ? "проект" : "проектов"}` : "Загружаю список…"}</p>
        </div>
        <div className="actions">
          <Link href="/takeoff/new" className="btn btn-primary">Новая ведомость</Link>
        </div>
      </div>

      <section className="panel max-w-[960px]">
        {error ? (
          <div className="panel-body !pt-5 text-sm">
            <span className="error-line">Не удалось загрузить проекты: {error}.</span>{" "}
            <button className="btn btn-text" onClick={load}>Повторить</button>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Проект</th><th className="num">Файлов</th><th className="num">Создан</th></tr>
            </thead>
            <tbody>
              {projects === null &&
                [0, 1, 2].map((i) => (
                  <tr key={i}>
                    <td><span className="skeleton h-4 w-64" /></td>
                    <td className="num"><span className="skeleton h-4 w-6" /></td>
                    <td className="num"><span className="skeleton h-4 w-24" /></td>
                  </tr>
                ))}
              {projects?.map((p) => (
                <tr key={p.id}>
                  <td className="max-w-0 w-2/3">
                    <Link href={`/takeoff/${p.id}`} className="block truncate font-medium hover:underline">{p.name}</Link>
                  </td>
                  <td className="num">{p.document_count}</td>
                  <td className="num whitespace-nowrap">{dateFmt.format(new Date(p.created_at))}</td>
                </tr>
              ))}
              {projects?.length === 0 && (
                <tr><td colSpan={3}><p className="empty my-3">Проектов пока нет. Загрузите альбом ОВ, чтобы начать.</p></td></tr>
              )}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
