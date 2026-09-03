"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Project } from "@/lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <div>
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Document checks</h1>
          <p className="text-sm text-[var(--muted)] mt-1">
            Drawing ↔ specification consistency, with evidence for every finding
          </p>
        </div>
        <Link href="/checks/new" className="btn btn-primary">
          + New check
        </Link>
      </div>

      {error && (
        <div className="card p-4 text-sm text-[var(--high)]">
          API unavailable: {error}
        </div>
      )}
      {!error && projects === null && (
        <p className="text-sm text-[var(--muted)]">Loading…</p>
      )}
      {projects !== null && projects.length === 0 && (
        <div className="card p-10 text-center">
          <p className="text-lg font-semibold mb-1">No checks yet</p>
          <p className="text-sm text-[var(--muted)] mb-5">
            Upload a drawing PDF and a specification PDF to run the first check.
          </p>
          <Link href="/checks/new" className="btn btn-primary">
            Create the first check
          </Link>
        </div>
      )}

      <div className="grid gap-3">
        {projects?.map((project) => (
          <Link
            key={project.id}
            href={`/checks/${project.id}`}
            className="card card-hover p-4 flex items-center justify-between"
          >
            <div>
              <p className="font-semibold">{project.name}</p>
              <p className="text-xs text-[var(--muted)] mt-0.5 mono">
                {new Date(project.created_at).toLocaleString()} ·{" "}
                {project.document_count} document(s)
              </p>
            </div>
            <div className="flex items-center gap-4">
              {project.analysis_status === "ANALYSIS_COMPLETED" && (
                <span className="text-sm">
                  <span className="font-bold text-[var(--accent)]">
                    {project.finding_count}
                  </span>{" "}
                  <span className="text-[var(--muted)]">findings</span>
                </span>
              )}
              {project.analysis_status === "ANALYSIS_STARTED" && (
                <span className="chip chip-review">RUNNING</span>
              )}
              {project.analysis_status === "ANALYSIS_FAILED" && (
                <span className="chip chip-high">FAILED</span>
              )}
              <span className="text-[var(--muted)]">→</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
