/* One outline icon set, 16px at 1.5px stroke, grey by default (currentColor). */
type IconProps = { className?: string };

const base = {
  width: 16, height: 16, viewBox: "0 0 16 16", fill: "none",
  stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const, "aria-hidden": true,
};

export const IconSheets = (p: IconProps) => (
  <svg {...base} {...p}><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" /><path d="M2.5 10.5h11M9.5 10.5v3" /></svg>
);
export const IconUpload = (p: IconProps) => (
  <svg {...base} {...p}><path d="M8 10.5V2.5M5 5.5l3-3 3 3M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" /></svg>
);
export const IconCheck = (p: IconProps) => (
  <svg {...base} {...p}><path d="M3 8.5l3 3 7-7" /></svg>
);
export const IconKit = (p: IconProps) => (
  <svg {...base} {...p}><rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1" /><rect x="9" y="2.5" width="4.5" height="4.5" rx="1" /><rect x="2.5" y="9" width="4.5" height="4.5" rx="1" /><path d="M9 11.25h4.5" /></svg>
);
export const IconBack = (p: IconProps) => (
  <svg {...base} {...p}><path d="M10 3.5L5.5 8 10 12.5" /></svg>
);
