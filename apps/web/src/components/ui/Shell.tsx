"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { IconCheck, IconKit, IconSheets, IconUpload } from "./icons";
import { Mark } from "./Mark";

const NAV = [
  { group: "Ведомости", items: [
    { href: "/takeoff", label: "Проекты", icon: IconSheets, match: (p: string) => p === "/takeoff" || /^\/takeoff\/prj_/.test(p) },
    { href: "/takeoff/new", label: "Загрузить альбом", icon: IconUpload, match: (p: string) => p === "/takeoff/new" },
  ] },
  { group: "Проверки", items: [
    { href: "/", label: "Чертёж и спецификация", icon: IconCheck, match: (p: string) => p === "/" || p.startsWith("/checks") },
  ] },
];

/** The sheet editor uses the whole sheet; every other screen gets the canvas padding. */
const isFullBleed = (path: string) => /^\/takeoff\/[^/]+\/sheet\//.test(path) || path === "/takeoff/demo";

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname() ?? "/";
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Навигация">
        <Link href="/takeoff" className="sidebar-brand">
          <Mark /> Foreman
        </Link>
        {NAV.map((section) => (
          <nav key={section.group} aria-label={section.group}>
            <div className="nav-group">{section.group}</div>
            {section.items.map(({ href, label, icon: Icon, match }) => (
              <Link key={href} href={href} className="nav-item" aria-current={match(path) ? "page" : undefined}>
                <Icon /> {label}
              </Link>
            ))}
          </nav>
        ))}
        <div className="mt-auto">
          <Link href="/ui" className="nav-item" aria-current={path === "/ui" ? "page" : undefined}>
            <IconKit /> Дизайн-система
          </Link>
        </div>
      </aside>
      <div className="min-w-0 flex flex-col">
        <div className="phone-bar">
          <Mark size={20} /> Foreman
          <nav aria-label="Разделы">
            <Link href="/takeoff" className="btn btn-text">Проекты</Link>
            <Link href="/takeoff/new" className="btn btn-text">Загрузить</Link>
          </nav>
        </div>
        <main className="sheet flex-1">
          <div className={isFullBleed(path) ? "sheet-body-full" : "sheet-body"}>{children}</div>
        </main>
      </div>
    </div>
  );
}
