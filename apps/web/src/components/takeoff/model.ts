import data from "@/data/demo-sheet.json";

export type Run = (typeof data.runs)[number];
export type SystemName = "П1" | "В1" | "ДВ1";
export const SYSTEMS: SystemName[] = ["П1", "В1", "ДВ1"];
export const EXCLUDED = "excluded";
export const UNKNOWN = "не определено";

export const SYSTEM_COLOUR: Record<string, string> = {
  П1: "#f0564a",
  В1: "#6aa9ff",
  ДВ1: "#3ecf8e",
  [UNKNOWN]: "#8b98a5",
};

export type Overrides = Readonly<Record<number, string>>;

export interface Group {
  key: string;
  system: string;
  section: string;
  insulated: boolean;
  lengthM: number;
  runIds: number[];
}

export interface SystemSummary {
  system: string;
  measuredM: number;
  specM: number | null;
  groups: Group[];
}

export const sheet = data;

export function effectiveSystem(run: Run, overrides: Overrides): string {
  return overrides[run.id] ?? run.system ?? UNKNOWN;
}

export function sectionLabel(run: Run): string {
  return run.section ?? (run.widthMm ? `${run.widthMm}x?` : "?");
}

export function summarise(overrides: Overrides): SystemSummary[] {
  const groups = new Map<string, Group>();
  for (const run of sheet.runs) {
    const system = effectiveSystem(run, overrides);
    if (system === EXCLUDED) continue;
    const section = sectionLabel(run);
    const key = `${system}|${section}|${run.insulated}`;
    const prev = groups.get(key);
    groups.set(key, {
      key,
      system,
      section,
      insulated: run.insulated,
      lengthM: (prev?.lengthM ?? 0) + run.lengthM,
      runIds: [...(prev?.runIds ?? []), run.id],
    });
  }
  const spec = sheet.specM as Record<string, number>;
  const names = [...SYSTEMS, UNKNOWN].filter(
    (name) => name !== UNKNOWN || [...groups.values()].some((g) => g.system === name),
  );
  return names.map((system) => {
    const own = [...groups.values()].filter((g) => g.system === system);
    return {
      system,
      measuredM: own.reduce((sum, g) => sum + g.lengthM, 0),
      specM: spec[system] ?? null,
      groups: own.sort((a, b) => b.lengthM - a.lengthM),
    };
  });
}

const fmt = (value: number) => value.toFixed(1).replace(".", ",");
export const formatM = fmt;

export function toRuCsv(summary: SystemSummary[]): string {
  const lines = ["Система;Сечение;Изоляция;Длина, м"];
  for (const system of summary) {
    for (const g of system.groups) {
      lines.push(`${g.system};${g.section};${g.insulated ? "Да" : "Нет"};${fmt(g.lengthM)}`);
    }
  }
  return "﻿" + lines.join("\r\n");
}
