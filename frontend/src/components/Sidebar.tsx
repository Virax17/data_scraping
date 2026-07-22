"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FilePlus2,
  Settings as SettingsIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Hexagon,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/runs", label: "Dashboard", icon: LayoutDashboard },
  { href: "/upload", label: "New Enrichment", icon: FilePlus2 },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className="flex h-screen shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200 ease-out"
      style={{ width: collapsed ? "var(--sidebar-width-collapsed)" : "var(--sidebar-width)" }}
    >
      <div className="flex h-16 items-center gap-2.5 border-b border-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Hexagon className="h-4.5 w-4.5" strokeWidth={2} />
        </div>
        {!collapsed && (
          <span className="truncate text-[15px] font-medium tracking-tight text-foreground">
            Tritorc Enrich
          </span>
        )}
      </div>

      <nav className="flex-1 space-y-1 px-2.5 py-3">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                "active:scale-[0.98]",
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-2.5">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-[18px] w-[18px]" strokeWidth={1.75} />
          ) : (
            <PanelLeftClose className="h-[18px] w-[18px]" strokeWidth={1.75} />
          )}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
