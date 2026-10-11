import { Menu, Moon, Sun, X } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";
import { BackendStatus } from "./BackendStatus";
import { Disclaimer } from "./Disclaimer";
import { ErrorBoundary } from "./ErrorBoundary";
import { FreshnessBar } from "./FreshnessBar";
import { Logo } from "./Logo";

export const NAV = [
  { to: "/", label: "Overview" },
  { to: "/import", label: "Import" },
  { to: "/holdings", label: "Holdings" },
  { to: "/analysis", label: "Analysis" },
  { to: "/mutual-funds", label: "Mutual Funds" },
  { to: "/screener", label: "Screener" },
  { to: "/watchlist", label: "Watchlist" },
  { to: "/compare", label: "Compare" },
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
  const ThemeIcon = theme === "dark" ? Sun : Moon;
  const themeLabel = theme === "dark" ? "Light mode" : "Dark mode";
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-control focus:bg-surface focus:px-3 focus:py-1 focus:text-sm"
      >
        Skip to content
      </a>
      <BackendStatus />
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
          <Link to="/" className="flex items-center gap-2 rounded-control font-semibold text-fg">
            <Logo className="size-7" />
            Portfolio Analyzer
          </Link>
          <button
            type="button"
            className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-control border border-border-strong px-2.5 text-sm text-fg md:hidden"
            aria-expanded={open}
            aria-controls="main-nav"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X aria-hidden className="size-4" /> : <Menu aria-hidden className="size-4" />}
            {open ? "Close" : "Menu"}
          </button>
          <nav
            id="main-nav"
            className={`${open ? "flex" : "hidden"} w-full flex-col gap-0.5 text-sm md:flex md:w-auto md:flex-row md:flex-wrap`}
            aria-label="Main"
          >
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) =>
                  `rounded-control px-2.5 py-1.5 font-medium transition-colors ${
                    isActive ? "bg-accent-soft text-accent-text" : "text-fg-muted hover:bg-surface-2 hover:text-fg"
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
            aria-label={themeLabel}
            title={themeLabel}
            className={`${open ? "inline-flex" : "hidden"} size-9 items-center justify-center rounded-control border border-border-strong text-fg-muted hover:bg-surface-2 hover:text-fg md:ml-auto md:inline-flex`}
          >
            <ThemeIcon aria-hidden className="size-4" />
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
