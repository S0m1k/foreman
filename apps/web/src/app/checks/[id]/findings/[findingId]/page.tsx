"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { SeverityChip, StatusChip, typeLabel } from "@/components/chips";
import {
  api,
  evidenceImageUrl,
  pageImageUrl,
  type EvidenceInfo,
  type Finding,
} from "@/lib/api";

function EvidencePanel({
  title,
  evidence,
  findingId,
  side,
}: {
  title: string;
  evidence: EvidenceInfo | null | undefined;
  findingId: string;
  side: "drawing" | "spec";
}) {
  const [cropFailed, setCropFailed] = useState(false);
  return (
    <div className="card p-4">
      <p className="mono text-xs font-bold tracking-widest text-[var(--muted)] mb-3">
        {title}
      </p>
      {evidence ? (
        <>
          {evidence.crop_path && !cropFailed ? (
            <img
              src={evidenceImageUrl(findingId, side)}
              alt={`${title} evidence`}
              className="rounded border border-[var(--line)] bg-white max-h-72 object-contain"
              onError={() => setCropFailed(true)}
            />
          ) : (
            <img
              src={pageImageUrl(evidence.document_id, evidence.page)}
              alt={`${title} page ${evidence.page}`}
              className="rounded border border-[var(--line)] bg-white max-h-72 object-contain"
            />
          )}
          <p className="text-xs text-[var(--muted)] mt-3 mono">
            {evidence.document_filename ?? evidence.document_id} / page {evidence.page}
          </p>
          {evidence.snippet && (
            <p className="text-xs mt-2 p-2 rounded bg-[var(--surface-2)] mono whitespace-pre-wrap">
              {evidence.snippet}
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-[var(--muted)] py-8 text-center">
          Not found in this document
        </p>
      )}
    </div>
  );
}

export default function FindingPage() {
  const { id, findingId } = useParams<{ id: string; findingId: string }>();
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getFinding(findingId)
      .then(setFinding)
      .catch((e: Error) => setError(e.message));
  }, [findingId]);

  async function mark(action: "confirm" | "false-positive") {
    if (!finding) return;
    setBusy(true);
    try {
      const updated =
        action === "confirm"
          ? await api.confirmFinding(finding.id)
          : await api.falsePositive(finding.id);
      setFinding(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p className="text-sm text-[var(--high)]">{error}</p>;
  if (!finding) return <p className="text-sm text-[var(--muted)]">Loading…</p>;

  return (
    <div>
      <div className="mb-6">
        <Link
          href={`/checks/${id}`}
          className="text-xs text-[var(--muted)] hover:text-[var(--text)]"
        >
          ← All findings
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <SeverityChip severity={finding.severity} />
          <StatusChip status={finding.status} />
          <h1 className="text-2xl font-bold mono">{finding.entity}</h1>
          <span className="text-[var(--muted)]">{typeLabel(finding.type)}</span>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <EvidencePanel
          title="DRAWING"
          evidence={finding.drawing_evidence}
          findingId={finding.id}
          side="drawing"
        />
        <EvidencePanel
          title="SPECIFICATION"
          evidence={finding.specification_evidence}
          findingId={finding.id}
          side="spec"
        />
      </div>

      <div className="card p-5 mb-6">
        <p className="mono text-xs font-bold tracking-widest text-[var(--muted)] mb-3">
          WHY THIS WAS FLAGGED
        </p>
        <p className="text-sm leading-relaxed mb-4">{finding.explanation}</p>
        {(finding.drawing_value || finding.specification_value) && (
          <div className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm max-w-sm">
            <span className="text-[var(--muted)]">Drawing:</span>
            <span className="mono font-semibold">
              {finding.drawing_value?.display ?? "—"}
            </span>
            <span className="text-[var(--muted)]">Specification:</span>
            <span className="mono font-semibold">
              {finding.specification_value?.display ?? "—"}
            </span>
          </div>
        )}
        <p className="text-xs text-[var(--muted)] mt-4 mono">
          confidence {(finding.confidence * 100).toFixed(0)}%
          {finding.parameter ? ` · parameter: ${finding.parameter}` : ""}
        </p>
      </div>

      <div className="flex gap-3">
        <button
          className="btn btn-ok"
          disabled={busy || finding.status === "CONFIRMED"}
          onClick={() => mark("confirm")}
        >
          ✓ Confirm discrepancy
        </button>
        <button
          className="btn btn-danger"
          disabled={busy || finding.status === "FALSE_POSITIVE"}
          onClick={() => mark("false-positive")}
        >
          ✕ False positive
        </button>
      </div>
    </div>
  );
}
