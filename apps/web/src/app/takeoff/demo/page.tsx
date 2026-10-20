import type { Metadata } from "next";
import { SheetScreen } from "@/components/takeoff/SheetScreen";

export const metadata: Metadata = { title: "Лист ОВ — ведомость воздуховодов" };

export default function TakeoffDemoPage() {
  return <SheetScreen />;
}
