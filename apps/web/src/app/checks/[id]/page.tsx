"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { SeverityChip, StatusChip, typeLabel } from "@/components/chips";
import {
  api,
  type Analysis,
  type Finding,
  type Project,
  type Stage,
} from "@/lib/api";

const STAGE_LABELS: Record<string, string> = {
  validate_files: "Validating files",
  parse_drawing: "Reading drawing",
  render_drawing_pages: "Rendering drawing pages",
  extract_drawing_text: "Extracting drawing text",
  ocr_drawing: "OCR",
  extract_drawing_entities: "Analyzing drawing",
  parse_specification: "Reading specification",
  extract_specification: "Analyzing specification",
  normalize_entities: "Normalizing entities",
  match_entities: "Matching objects",
  compare: "Comparing objects",
  verify_findings: "Verifying findings",
  save_findings: "Saving results",
};

function StageRow({ stage }: { stage: Stage }) {
  const icon =
    stage.status === "DONE"
      ? "✓"
      : stage.status === "RUNNING"
        ? "…"
        : stage.status === "FAILED"
          ? "✕"
          : stage.status === "SKIPPED"
            ? "–"
            : " ";
  const color =
    stage.status === "DONE"
      ? "text-[var(--ok)]"
      : stage.status === "FAILED"
        ? "text-[var(--high)]"
        : stage.status === "RUNNING"
          ? "text-[var(--accent)]"
          : "text-[var(--muted)]";
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className={stage.status === "PENDING" ? "text-[var(--muted)]" : ""}>
        {STAGE_LABELS[stage.stage] ?? stage.stage}
      </span>
      <span className={`mono ${color}`}>
        {stage.duration != null && stage.status === "DONE"
          ? `${stage.duration.toFixed(1)}s ${icon}`
          : icon}
      </span>
    </div>
  );
}

type Filter = "ALL" | "HIGH" | "MEDIUM" | "LOW" | "CONFIRMED" | "NEEDS_REVIEW";

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <Link
      href={`/checks/${finding.project_id}/findings/${finding.id}`}
      className="card card-hover p-4 block"
    >
      <div className="flex items-center gap-3 mb-2">
        <SeverityChip severity={finding.severity} />
        <StatusChip status={finding.status} />
        <span className="mono font-bold">{finding.entity}</span>
        <span className="text-sm text-[var(--muted)]">{typeLabel(finding.type)}</span>
      </div>
      {(finding.drawing_value || finding.specification_value) && (
        <div className="grid grid-cols-2 gap-2 text-sm mb-2 max-w-md">
          <span className="text-[var(--muted)]">Drawing:</span>
          <span className="mono">{finding.drawing_value?.display ?? "—"}</span>
          <span className="text-[var(--muted)]">Specification:</span>
          <span className="mono">{finding.specification_value?.display ?? "—"}</span>
        </div>
      )}
      <p className="text-xs text-[var(--muted)]">
        {finding.drawing_evidence &&
          `Drawing: ${finding.drawing_evidence.document_filename ?? ""} / p.${finding.drawing_evidence.page}`}
        {finding.drawing_evidence && finding.specification_evidence && "  ·  "}
        {finding.specification_evidence &&
          `Specification: ${finding.specification_evidence.document_filename ?? ""} / p.${finding.specification_evidence.page}`}
      </p>
    </Link>
  );
}

export default function CheckPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [proj, ana] = await Promise.all([
        api.getProject(id),
        api.getAnalysis(id).catch(() => null),
      ]);
      setProject(proj);
      setAnalysis(ana);
      if (ana?.status === "ANALYSIS_COMPLETED") {
        setFindings(await api.listFindings(id));
      }
      return ana?.status;
    } catch (e) {
      setError((e as Error).message);
      return "ERROR";
    }
  }, [id]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const tick = async () => {
      const status = await refresh();
      if (!cancelled && status === "ANALYSIS_STARTED") {
        timer = setTimeout(tick, 1500);
      }
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  const visible = findings?.filter((f) => {
    if (filter === "ALL") return true;
    if (filter === "CONFIRMED" || filter === "NEEDS_REVIEW")
      return f.status === filter;
    return f.severity === filter;
  });

  const filters: Filter[] = ["ALL", "HIGH", "MEDIUM", "LOW", "CONFIRMED", "NEEDS_REVIEW"];

  return (
    <div>
      <div className="mb-6">
        <Link href="/" className="text-xs text-[var(--muted)] hover:text-[var(--text)]">
          ← All checks
        </Link>
        <h1 className="text-2xl font-bold mt-1">{project?.name ?? "…"}</h1>
      </div>

      {error && <p className="text-sm text-[var(--high)]">{error}</p>}

      {analysis?.status === "ANALYSIS_STARTED" && (
        <div className="card p-6 max-w-md">
          <p className="font-semibold mb-3">Analyzing documents…</p>
          {analysis.stages.map((stage) => (
            <StageRow key={stage.stage} stage={stage} />
          ))}
        </div>
      )}

      {analysis?.status === "ANALYSIS_FAILED" && (
        <div className="card p-6 border-[var(--high)]">
          <p className="font-semibold text-[var(--high)] mb-2">Analysis failed</p>
          <p className="mono text-sm text-[var(--muted)]">{analysis.error}</p>
        </div>
      )}

      {analysis?.status === "ANALYSIS_COMPLETED" && findings && (
        <>
          <div className="flex items-center justify-between mb-4">
            <p className="text-lg">
              Analysis complete —{" "}
              <span className="font-bold text-[var(--accent)]">
                {findings.length}
              </span>{" "}
              finding{findings.length === 1 ? "" : "s"}
            </p>
            {analysis.model && (
              <span className="text-xs mono text-[var(--muted)]">
                model: {analysis.model}
              </span>
            )}
          </div>

          <div className="flex gap-1.5 mb-5 flex-wrap">
            {filters.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`btn text-xs py-1.5 px-3 ${
                  filter === f ? "btn-primary" : "btn-ghost"
                }`}
              >
                {f === "NEEDS_REVIEW" ? "Needs review" : f[0] + f.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          {visible?.length === 0 && (
            <div className="card p-8 text-center text-[var(--muted)]">
              {findings.length === 0
                ? "No discrepancies found between the drawing and the specification."
                : "Nothing matches this filter."}
            </div>
          )}
          <div className="grid gap-3">
            {visible?.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
