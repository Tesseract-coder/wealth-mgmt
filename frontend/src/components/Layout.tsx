import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";
import { BackendStatus } from "./BackendStatus";
import { Disclaimer } from "./Disclaimer";
import { ErrorBoundary } from "./ErrorBoundary";
import { FreshnessBar } from "./FreshnessBar";

export const NAV = [
  { to: "/", label: "Overview" },
  { to: "/import", label: "Import" },
  { to: "/holdings", label: "Holdings" },
  { to: "/analysis", label: "Analysis" },
  { to: "/mutual-funds", label: "Mutual Funds" },
  { to: "/screener", label: "Screener" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/settings", label: "Settings" },
] as const;

export function Layout() {
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const [lastPath, setLastPath] = useState(pathname);
  if (pathname !== lastPath) {
    // Close the mobile menu after navigating.
    setLastPath(pathname);
    setOpen(false);
  }
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-1 focus:text-sm dark:focus:bg-slate-900">
        Skip to content
      </a>
      <BackendStatus />
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold">Portfolio Analyzer</span>
          <button
            type="button"
            className="ml-auto rounded border border-slate-300 px-2 py-1 text-sm md:hidden dark:border-slate-700"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? "✕ Close" : "☰ Menu"}
          </button>
          <nav
            id="main-nav"
            className={`${open ? "flex" : "hidden"} w-full flex-col gap-1 text-sm md:flex md:w-auto md:flex-row md:flex-wrap`}
            aria-label="Main"
          >
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `rounded px-2 py-1 ${
                    isActive
                      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <button
            type="button"
            onClick={toggle}
            className={`${open ? "block" : "hidden"} rounded border border-slate-300 px-2 py-1 text-sm md:ml-auto md:block dark:border-slate-700`}
          >
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
        <div className="mx-auto max-w-7xl px-4 pb-2">
          <FreshnessBar />
        </div>
      </header>
      <main id="main" className="mx-auto w-full min-w-0 max-w-7xl flex-1 px-4 py-6">
        <ErrorBoundary resetKey={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <Disclaimer />
    </div>
  );
}
