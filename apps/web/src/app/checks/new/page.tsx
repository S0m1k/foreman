"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { api } from "@/lib/api";

type Slot = {
  label: string;
  hint: string;
  type: "DRAWING" | "SPECIFICATION";
};

const SLOTS: Slot[] = [
  { label: "DRAWING", hint: "Plan / layout sheet, PDF", type: "DRAWING" },
  {
    label: "SPECIFICATION",
    hint: "Equipment schedule / bill of materials, PDF",
    type: "SPECIFICATION",
  },
];

function UploadZone({
  slot,
  file,
  onFile,
}: {
  slot: Slot;
  file: File | null;
  onFile: (f: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  return (
    <div
      className={`card p-6 text-center cursor-pointer transition-colors ${
        dragOver ? "border-[var(--accent)]" : ""
      }`}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const dropped = e.dataTransfer.files?.[0];
        if (dropped) onFile(dropped);
      }}
    >
      <p className="mono text-xs font-bold tracking-widest text-[var(--muted)] mb-3">
        {slot.label}
      </p>
      {file ? (
        <p className="font-semibold text-[var(--ok)]">✓ {file.name}</p>
      ) : (
        <>
          <p className="font-semibold mb-1">Upload PDF</p>
          <p className="text-xs text-[var(--muted)]">{slot.hint}</p>
          <p className="text-xs text-[var(--muted)] mt-2 opacity-70">
            DWG — coming soon
          </p>
        </>
      )}
      <input
        ref={input}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => {
          const chosen = e.target.files?.[0];
          if (chosen) onFile(chosen);
        }}
      />
    </div>
  );
}

export default function NewCheck() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<string, File | null>>({
    DRAWING: null,
    SPECIFICATION: null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = files.DRAWING && files.SPECIFICATION && !busy;

  async function start() {
    if (!files.DRAWING || !files.SPECIFICATION) return;
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(
        name.trim() || files.DRAWING.name.replace(/\.pdf$/i, ""),
      );
      await api.uploadDocument(project.id, "DRAWING", files.DRAWING);
      await api.uploadDocument(project.id, "SPECIFICATION", files.SPECIFICATION);
      await api.startAnalysis(project.id);
      router.push(`/checks/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
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

      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        {SLOTS.map((slot) => (
          <UploadZone
            key={slot.type}
            slot={slot}
            file={files[slot.type]}
            onFile={(f) => setFiles((prev) => ({ ...prev, [slot.type]: f }))}
          />
        ))}
      </div>

      {error && (
        <p className="text-sm text-[var(--high)] mb-4">Error: {error}</p>
      )}

      <button className="btn btn-primary w-full justify-center" disabled={!ready} onClick={start}>
        {busy ? "Uploading…" : "Start analysis"}
      </button>
    </div>
  );
}
