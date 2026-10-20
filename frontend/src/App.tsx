import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";
import { SkeletonCard } from "./components/ui";

/** Every page but the Overview loads on first visit, so the app opens with less to download. */
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K, label: string) {
  const Lazy = lazy<ComponentType>(() => load().then((m) => ({ default: m[name] })));
  return function Page() {
    return (
      <Suspense fallback={<SkeletonCard label={label} lines={6} />}>
        <Lazy />
      </Suspense>
    );
  };
}

const Onboarding = page(() => import("./pages/Onboarding"), "Onboarding", "setup");
const Import = page(() => import("./pages/Import"), "Import", "the import page");
const Holdings = page(() => import("./pages/Holdings"), "Holdings", "your holdings");
const Technical = page(() => import("./pages/Technical"), "Technical", "the stock page");
const MutualFunds = page(() => import("./pages/MutualFunds"), "MutualFunds", "the mutual funds page");
const Screener = page(() => import("./pages/Screener"), "Screener", "the screener");
const Watchlist = page(() => import("./pages/Watchlist"), "Watchlist", "your watchlist");
const Compare = page(() => import("./pages/Compare"), "Compare", "the compare page");
const Settings = page(() => import("./pages/Settings"), "Settings", "settings");
const DevComponents = page(() => import("./pages/DevComponents"), "DevComponents", "component preview");

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="onboarding" element={<Onboarding />} />
        <Route path="import" element={<Import />} />
        <Route path="holdings" element={<Holdings />} />
        <Route path="analysis" element={<Technical />} />
        <Route path="analysis/:ticker" element={<Technical />} />
        <Route path="technical/*" element={<LegacyTechnical />} />
        <Route path="mutual-funds" element={<MutualFunds />} />
        <Route path="mutual-funds/:code" element={<MutualFunds />} />
        <Route path="screener" element={<Screener />} />
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="compare" element={<Compare />} />
        <Route path="settings" element={<Settings />} />
        <Route path="dev/components" element={<DevComponents />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

/** Phase 4 links pointed at /technical; keep them working. */
function LegacyTechnical() {
  const { pathname, search } = useLocation();
  const p = new URLSearchParams(search);
  if (!p.has("view")) p.set("view", "technical");
  return <Navigate replace to={`${pathname.replace(/^\/technical/, "/analysis")}?${p.toString()}`} />;
}
