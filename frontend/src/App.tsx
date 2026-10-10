import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Holdings } from "./pages/Holdings";
import { Import } from "./pages/Import";
import { Placeholder } from "./pages/Placeholder";
import { Status } from "./pages/Status";
import { Technical } from "./pages/Technical";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Status />} />
        <Route path="import" element={<Import />} />
        <Route path="holdings" element={<Holdings />} />
        <Route path="analysis" element={<Technical />} />
        <Route path="analysis/:ticker" element={<Technical />} />
        <Route path="technical/*" element={<LegacyTechnical />} />
        <Route path="mutual-funds" element={<Placeholder title="Mutual Funds" phase={8} />} />
        <Route path="screener" element={<Placeholder title="Screener" phase={9} />} />
        <Route path="watchlist" element={<Placeholder title="Watchlist" phase={9} />} />
        <Route path="settings" element={<Placeholder title="Settings" phase={8} />} />
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
