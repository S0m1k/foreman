"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { api } from "@/lib/api";

type Slot = {
  label: string;
  hint: string;
  type: "DRAWING" | "SPECIFICATION";
  accept: string;
  formats: string;
};

const SLOTS: Slot[] = [
  {
    label: "DRAWINGS",
    hint: "Plans / layout sheets — one or many",
    type: "DRAWING",
    accept: ".pdf,.dxf,.dwg,application/pdf",
    formats: "PDF · DXF · DWG",
  },
  {
    label: "SPECIFICATIONS",
    hint: "Equipment schedules / bills of materials — one or many",
    type: "SPECIFICATION",
    accept: ".pdf,application/pdf",
    formats: "PDF",
  },
];

function UploadZone({
  slot,
  files,
  onAdd,
  onRemove,
}: {
  slot: Slot;
  files: File[];
  onAdd: (f: File[]) => void;
  onRemove: (index: number) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  return (
    <div
      className={`card p-6 transition-colors ${
        dragOver ? "border-[var(--accent)]" : ""
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        onAdd(Array.from(e.dataTransfer.files ?? []));
      }}
    >
      <p className="mono text-xs font-bold tracking-widest text-[var(--muted)] mb-3 text-center">
        {slot.label}
      </p>

      {files.length > 0 && (
        <ul className="mb-3 space-y-1">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex items-center justify-between gap-2 text-sm"
            >
              <span className="text-[var(--ok)] truncate">✓ {file.name}</span>
              <button
                className="text-[var(--muted)] hover:text-[var(--high)] shrink-0"
                title="Remove"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(index);
                }}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <div
        className="text-center cursor-pointer py-2"
        onClick={() => input.current?.click()}
      >
        <p className="font-semibold mb-1">
          {files.length === 0 ? "Upload files" : "+ Add more"}
        </p>
        <p className="text-xs text-[var(--muted)]">{slot.hint}</p>
        <p className="text-xs text-[var(--muted)] mt-2 opacity-70 mono">
          {slot.formats}
        </p>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        accept={slot.accept}
        className="hidden"
        onChange={(e) => {
          onAdd(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </div>
  );
}

export default function NewCheck() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<string, File[]>>({
    DRAWING: [],
    SPECIFICATION: [],
  });
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ready =
    files.DRAWING.length > 0 && files.SPECIFICATION.length > 0 && !busy;

  function addFiles(type: string, added: File[]) {
    if (added.length === 0) return;
    setFiles((prev) => {
      const existing = prev[type];
      const fresh = added.filter(
        (f) => !existing.some((e) => e.name === f.name && e.size === f.size),
      );
      return { ...prev, [type]: [...existing, ...fresh] };
    });
  }

  async function start() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(
        name.trim() || files.DRAWING[0].name.replace(/\.(pdf|dxf|dwg)$/i, ""),
      );
      const uploads: Array<["DRAWING" | "SPECIFICATION", File]> = [
        ...files.DRAWING.map((f) => ["DRAWING", f] as ["DRAWING", File]),
        ...files.SPECIFICATION.map(
          (f) => ["SPECIFICATION", f] as ["SPECIFICATION", File],
        ),
      ];
      for (let i = 0; i < uploads.length; i++) {
        const [type, file] = uploads[i];
        setProgress(`Uploading ${i + 1}/${uploads.length}: ${file.name}`);
        await api.uploadDocument(project.id, type, file);
      }
      setProgress(null);
      await api.startAnalysis(project.id);
      router.push(`/checks/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      setProgress(null);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">New document check</h1>

      <label className="block mb-6">
        <span className="text-sm text-[var(--muted)]">Check name (optional)</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Block A — HVAC, revision 3"
          className="mt-1 w-full card px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
        />
      </label>

      <div className="grid sm:grid-cols-2 gap-4 mb-6 items-start">
        {SLOTS.map((slot) => (
          <UploadZone
            key={slot.type}
            slot={slot}
            files={files[slot.type]}
            onAdd={(added) => addFiles(slot.type, added)}
            onRemove={(index) =>
              setFiles((prev) => ({
                ...prev,
                [slot.type]: prev[slot.type].filter((_, i) => i !== index),
              }))
            }
          />
        ))}
      </div>

      {error && (
        <p className="text-sm text-[var(--high)] mb-4">Error: {error}</p>
      )}

      <button
        className="btn btn-primary w-full justify-center"
        disabled={!ready}
        onClick={start}
      >
        {busy ? progress ?? "Uploading…" : "Start analysis"}
      </button>
    </div>
  );
}
