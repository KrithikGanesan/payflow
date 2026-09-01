import { useEffect, useState, useSyncExternalStore } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Zap,
  Workflow,
  LayoutDashboard,
  ScrollText,
  History as HistoryIcon,
  Inbox,
  Moon,
  Sun,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { getMode, setMode, getLiveStatus, onModeChange } from "@/api";
import type { Mode } from "@/api";

const NAV = [
  { to: "/", label: "Live Run", icon: Zap, end: true },
  { to: "/flow", label: "Decision Flow", icon: Workflow },
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/history", label: "History", icon: HistoryIcon },
  { to: "/exceptions", label: "Exceptions", icon: Inbox },
  { to: "/audit", label: "Audit Trail", icon: ScrollText },
];

function useTheme() {
  const [dark, setDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const el = document.documentElement;
    el.classList.toggle("dark", dark);
    try {
      localStorage.setItem("verdict-theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

function useModeState() {
  const mode = useSyncExternalStore(onModeChange, getMode);
  const live = useSyncExternalStore(onModeChange, getLiveStatus);
  return { mode, live };
}

export function Layout() {
  const { dark, toggle } = useTheme();
  const { mode, live } = useModeState();

  return (
    <div className="flex min-h-screen">
      {/* sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white shadow-sm">
            <CheckCircle2 className="h-5 w-5" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight text-slate-900 dark:text-white">
              PayFlow
            </div>
            <div className="text-[10px] font-medium uppercase tracking-widest text-slate-400">
              Invoice → Decision
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent-soft text-accent dark:bg-accent-softdark/50 dark:text-indigo-200"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                )
              }
            >
              <n.icon className="h-4 w-4" />
              {n.label}
            </NavLink>
          ))}
        </nav>

        <div className="space-y-3 border-t border-slate-200 px-4 py-4 dark:border-slate-800">
          {import.meta.env.DEV && <ModeToggle mode={mode} live={live} />}
          <button
            onClick={toggle}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {dark ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </aside>

      {/* main */}
      <main className="ml-60 flex-1">
        <Outlet />
      </main>
    </div>
  );
}

function ModeToggle({ mode, live }: { mode: Mode; live: string }) {
  const opts: Mode[] = ["auto", "live", "mock"];
  const statusColor =
    live === "live"
      ? "bg-emerald-500"
      : live === "mock"
        ? "bg-amber-500"
        : "bg-slate-400";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Data source
        </span>
        <span className="flex items-center gap-1 text-[10px] text-slate-500 dark:text-slate-400">
          <span className={cn("h-1.5 w-1.5 rounded-full", statusColor)} />
          {live === "live" ? "backend" : live === "mock" ? "mock" : "…"}
        </span>
      </div>
      <div className="flex rounded-lg border border-slate-200 p-0.5 dark:border-slate-700">
        {opts.map((o) => (
          <button
            key={o}
            onClick={() => setMode(o)}
            className={cn(
              "flex-1 rounded-md px-1 py-1 text-[11px] font-medium capitalize transition-colors",
              mode === o
                ? "bg-accent text-white"
                : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
            )}
          >
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}
