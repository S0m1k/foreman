"use client";

import { useRef, useState } from "react";

interface Props {
  label: string;
  hint: string;
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
}

export function FileDrop({ label, hint, files, onAdd, onRemove }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [isOver, setIsOver] = useState(false);
  const pdfs = (list: FileList | null) =>
    Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));

  return (
    <div
      className={`card p-5 transition-colors ${isOver ? "border-[var(--accent)]" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setIsOver(false);
        onAdd(pdfs(e.dataTransfer.files));
      }}
    >
      <p className="mono text-xs font-bold tracking-widest text-[var(--muted)] mb-3">{label}</p>
      {files.length > 0 && (
        <ul className="mb-3 space-y-1">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex items-center justify-between gap-2 text-sm">
              <span className="text-[var(--ok)] truncate">✓ {file.name}</span>
              <button
                className="text-[var(--muted)] hover:text-[var(--high)] shrink-0"
                title="Убрать"
                onClick={() => onRemove(index)}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="w-full text-left py-1" onClick={() => input.current?.click()}>
        <span className="font-semibold">{files.length === 0 ? "Выбрать PDF" : "+ ещё файл"}</span>
        <span className="block text-xs text-[var(--muted)] mt-1">{hint}</span>
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={(e) => {
          onAdd(pdfs(e.target.files));
          e.target.value = "";
        }}
      />
    </div>
  );
}
