export function SeverityChip({ severity }: { severity: string }) {
  const cls =
    severity === "HIGH"
      ? "chip chip-high"
      : severity === "MEDIUM"
        ? "chip chip-medium"
        : "chip chip-low";
  return <span className={cls}>{severity}</span>;
}

export function StatusChip({ status }: { status: string }) {
  if (status === "NEEDS_REVIEW")
    return <span className="chip chip-review">NEEDS REVIEW</span>;
  if (status === "CONFIRMED") return <span className="chip chip-ok">CONFIRMED</span>;
  if (status === "FALSE_POSITIVE")
    return <span className="chip chip-low">FALSE POSITIVE</span>;
  return null;
}

export function typeLabel(type: string): string {
  switch (type) {
    case "PARAMETER_MISMATCH":
      return "Parameter mismatch";
    case "QUANTITY_MISMATCH":
      return "Quantity mismatch";
    case "MISSING_IN_SPECIFICATION":
      return "Missing in specification";
    case "MISSING_ON_DRAWING":
      return "Missing on drawing";
    case "IDENTIFICATION_MISMATCH":
      return "Identification mismatch";
    default:
      return type;
  }
}
