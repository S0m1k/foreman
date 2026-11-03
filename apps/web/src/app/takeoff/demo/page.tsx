import type { Metadata } from "next";
import { SheetScreen } from "@/components/takeoff/SheetScreen";
import demo from "@/data/demo-sheet.json";
import type { TakeoffSheet } from "@/lib/api";

export const metadata: Metadata = { title: "Лист ОВ — демо" };

// Rebuilt by scripts/build_demo_takeoff.py from a synthetic album.
// The demo's scale is shown as read off the drawing, never settled.
const sheet = { ...demo, detected_scale: demo.scale, scale_confirmed: false } as TakeoffSheet;

export default function TakeoffDemoPage() {
  return <SheetScreen sheet={sheet} imageUrl={sheet.image_url} backHref="/takeoff/new" isDemo />;
}
