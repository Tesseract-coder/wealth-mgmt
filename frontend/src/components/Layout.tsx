import { NavLink, Outlet } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";
import { Disclaimer } from "./Disclaimer";

export const NAV = [
  { to: "/", label: "Overview" },
  { to: "/import", label: "Import" },
  { to: "/holdings", label: "Holdings" },
  { to: "/mutual-funds", label: "Mutual Funds" },
  { to: "/screener", label: "Screener" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/settings", label: "Settings" },
] as const;

export function Layout() {
  const { theme, toggle } = useTheme();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold">Portfolio Analyzer</span>
          <nav className="flex flex-wrap gap-1 text-sm" aria-label="Main">
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
            className="ml-auto rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-700"
          >
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <Disclaimer />
    </div>
  );
}
