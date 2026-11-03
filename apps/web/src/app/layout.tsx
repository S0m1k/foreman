import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Shell } from "@/components/ui/Shell";
import "./globals.css";

const plex = IBM_Plex_Sans({
  subsets: ["latin", "cyrillic"],
  weight: ["400", "500", "600"],
  variable: "--font-plex",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin", "cyrillic"],
  weight: ["400"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Foreman — ведомости объёмов по чертежам ОВ",
  description: "Ведомость воздуховодов и элементов по векторным PDF, со сверкой со спецификацией",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className={`${plex.variable} ${plexMono.variable}`}>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
