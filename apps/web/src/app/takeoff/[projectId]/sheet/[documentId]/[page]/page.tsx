"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { Overrides } from "@/components/takeoff/model";
import { SheetScreen } from "@/components/takeoff/SheetScreen";
import { api, apiUrl, takeoffExportUrl, type TakeoffSheet } from "@/lib/api";

export default function TakeoffSheetPage() {
  const { projectId, documentId, page } = useParams<{
    projectId: string;
    documentId: string;
    page: string;
  }>();
  const pageNumber = Number(page);
  const [sheet, setSheet] = useState<TakeoffSheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTakeoff(projectId)
      .then((takeoff) => api.getTakeoffSheet(takeoff.id, documentId, pageNumber))
      .then(setSheet)
      .catch((e: Error) => setError(e.message));
  }, [projectId, documentId, pageNumber]);

  const takeoffId = sheet?.takeoff_id;
  // stable identity: SheetScreen debounces saves on it
  const save = useCallback(
    async (overrides: Overrides) => {
      if (!takeoffId) return;
      await api.saveTakeoffOverrides(takeoffId, documentId, pageNumber, { ...overrides });
    },
    [takeoffId, documentId, pageNumber],
  );

  if (error) return <div className="card p-4 text-sm text-[var(--high)]">{error}</div>;
  if (!sheet) return <p className="text-sm text-[var(--muted)]">Загружаю лист…</p>;
  return (
    <SheetScreen
      sheet={sheet}
      imageUrl={apiUrl(sheet.image_url)}
      backHref={`/takeoff/${projectId}`}
      onSave={save}
      exportHref={takeoffExportUrl(sheet.takeoff_id)}
    />
  );
}
