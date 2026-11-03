/** Foreman's mark: the plan symbol of a vertical duct (a section crossed by its diagonals). */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" aria-hidden="true">
      <rect x="2" y="2" width="18" height="18" rx="3" fill="hsl(214 70% 44%)" />
      <path d="M6 6 L16 16 M16 6 L6 16" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
