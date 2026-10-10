import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Holdings } from "./pages/Holdings";
import { Import } from "./pages/Import";
import { MutualFunds } from "./pages/MutualFunds";
import { Onboarding } from "./pages/Onboarding";
import { Overview } from "./pages/Overview";
import { Placeholder } from "./pages/Placeholder";
import { Screener } from "./pages/Screener";
import { Settings } from "./pages/Settings";
import { Technical } from "./pages/Technical";
import { Watchlist } from "./pages/Watchlist";

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
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Placeholder title="Not found" phase={0} />} />
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
