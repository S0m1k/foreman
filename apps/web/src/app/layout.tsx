import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Foreman — AI Drawing Checker",
  description:
    "Automatic consistency checking between construction drawings and specifications",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-[var(--line)] bg-[color-mix(in_srgb,var(--surface)_82%,transparent)] backdrop-blur sticky top-0 z-20">
          <div className="mx-auto max-w-6xl px-6 py-3 flex items-center gap-3">
            <Link href="/" className="flex items-center gap-2.5 group">
              <span className="mono text-[15px] font-bold tracking-wide">
                <span className="text-[var(--accent)]">▙</span> FOREMAN
              </span>
              <span className="text-xs text-[var(--muted)] border-l border-[var(--line)] pl-2.5 hidden sm:inline">
                AI drawing checker
              </span>
            </Link>
            <nav className="ml-auto flex items-center gap-5 text-sm">
              <Link href="/" className="text-[var(--muted)] hover:text-[var(--text)]">
                Проверки
              </Link>
              <Link href="/takeoff/new" className="text-[var(--muted)] hover:text-[var(--text)]">
                Ведомость воздуховодов
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
