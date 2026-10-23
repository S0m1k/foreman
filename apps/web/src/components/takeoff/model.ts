import type { TakeoffRun, TakeoffSheet } from "@/lib/api";

export const EXCLUDED = "excluded";
export const UNKNOWN = "не определено";

// run id (as a string, the way the API keys it) -> system | "excluded"
export type Overrides = Readonly<Record<string, string>>;

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
  sheetM: number;
  // this sheet plus every other plan sheet of the project, edits applied
  projectM: number;
  specM: number | null;
  groups: Group[];
}

const FAMILY_RE = /^(ДВ|ПД|ДП|В|П)/;
// supply red, extract blue, smoke exhaust green, smoke supply orange
const FAMILY_HUE: Record<string, number> = { П: 4, В: 214, ДВ: 145, ПД: 30, ДП: 280 };

export function family(system: string): string | null {
  return FAMILY_RE.exec(system)?.[1] ?? null;
}

/** One hue per family, a lightness per system, so В1 and В2 stay tellable apart. */
export function systemColour(system: string): string {
  const fam = family(system);
  if (system === EXCLUDED || fam === null) return "#8b98a5";
  let hash = 0;
  for (const char of system) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const lightness = 48 + (hash % 5) * 6;
  return `hsl(${FAMILY_HUE[fam]} 78% ${lightness}%)`;
}

export const naturalOrder = (a: string, b: string) =>
  a.localeCompare(b, "ru", { numeric: true });

export function effectiveSystem(run: TakeoffRun, overrides: Overrides): string {
  return overrides[String(run.id)] ?? run.system ?? UNKNOWN;
}

export function sectionLabel(run: TakeoffRun): string {
  return run.section ?? (run.width_mm ? `${run.width_mm}x?` : "?");
}

function groupRuns(sheet: TakeoffSheet, overrides: Overrides): Map<string, Group> {
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
      lengthM: (prev?.lengthM ?? 0) + run.length_m,
      runIds: [...(prev?.runIds ?? []), run.id],
    });
  }
  return groups;
}

export function summarise(sheet: TakeoffSheet, overrides: Overrides): SystemSummary[] {
  const groups = [...groupRuns(sheet, overrides).values()];
  const systems = [...new Set(groups.map((g) => g.system))].sort((a, b) =>
    a === UNKNOWN ? 1 : b === UNKNOWN ? -1 : naturalOrder(a, b),
  );
  return systems.map((system) => {
    const own = groups
      .filter((g) => g.system === system)
      .sort((a, b) => b.lengthM - a.lengthM);
    const sheetM = own.reduce((sum, g) => sum + g.lengthM, 0);
    return {
      system,
      sheetM,
      projectM: (sheet.other_sheets_m[system] ?? 0) + sheetM,
      specM: sheet.spec_m[system] ?? null,
      groups: own,
    };
  });
}

/** Systems a group may be moved to: the spec's systems of its own family. */
export function moveTargets(sheet: TakeoffSheet, current: string): string[] {
  const fam = family(current);
  const names = new Set([
    ...Object.keys(sheet.spec_m),
    ...sheet.runs.map((r) => r.system).filter((s): s is string => Boolean(s)),
  ]);
  return [...names]
    .filter((name) => name !== current && (fam === null || family(name) === fam))
    .sort(naturalOrder);
}

const fmt = (value: number) => value.toFixed(1).replace(".", ",");
export const formatM = fmt;

const SPEC_TOLERANCE = 0.03;

export type Verdict = { label: string; tone: string; isOver: boolean };

/**
 * The specification covers the whole building, so it is a ceiling for the
 * project total, not a target for one sheet: going over it is an error, falling
 * short only means the rest is drawn on sheets not measured yet.
 */
export function verdict(projectM: number, specM: number | null): Verdict {
  // 0 m means the system is specified (its equipment is) but none of its ducts are
  if (specM === null || specM === 0) {
    return { label: "нет в спецификации", tone: "chip-medium", isOver: false };
  }
  const delta = projectM - specM;
  if (Math.abs(delta) <= specM * SPEC_TOLERANCE) {
    return { label: "сходится", tone: "chip-ok", isOver: false };
  }
  if (delta > 0) return { label: `+${fmt(delta)} м сверх`, tone: "chip-high", isOver: true };
  return { label: `ещё ${fmt(-delta)} м`, tone: "chip-low", isOver: false };
}

export function toRuCsv(summary: SystemSummary[]): string {
  const lines = ["Система;Сечение;Изоляция;Длина, м"];
  for (const system of summary) {
    for (const g of system.groups) {
      lines.push(`${g.system};${g.section};${g.insulated ? "Да" : "Нет"};${fmt(g.lengthM)}`);
    }
  }
  return "﻿" + lines.join("\r\n");
}
