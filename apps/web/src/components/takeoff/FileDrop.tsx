"use client";

import { useRef, useState } from "react";
import { IconUpload } from "@/components/ui/icons";

interface Props {
  label: string;
  hint: string;
  files: File[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
  isMain?: boolean;
}

const sizeMb = (bytes: number) => (bytes / 1048576).toFixed(1).replace(".", ",");

export function FileDrop({ label, hint, files, onAdd, onRemove, isMain }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [isOver, setIsOver] = useState(false);
  const pdfs = (list: FileList | null) =>
    Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));

  return (
    <div className="field">
      <span>{label}</span>
      <div
        className={`rounded-[var(--radius-card)] border border-dashed transition-colors ${
          isOver ? "border-[var(--text)] bg-[var(--raised)]" : "border-[var(--control)]"
        }`}
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
        {files.length > 0 && (
          <ul>
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 px-4 h-11 border-b border-[var(--rule)] text-sm">
                <span className="truncate">{file.name}</span>
                <span className="num muted ml-auto flex-none">{sizeMb(file.size)} МБ</span>
                <button className="btn btn-text flex-none" onClick={() => onRemove(index)} aria-label={`Убрать ${file.name}`}>
                  Убрать
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className={`w-full flex items-center gap-3 px-4 text-left ${isMain && files.length === 0 ? "h-28" : "h-14"}`}
          onClick={() => input.current?.click()}
        >
          <IconUpload className="muted flex-none" />
          <span>
            <span className="font-medium">{files.length === 0 ? "Выберите PDF или перетащите сюда" : "Добавить ещё файл"}</span>
            <span className="block text-xs muted mt-0.5">{hint}</span>
          </span>
        </button>
      </div>
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
