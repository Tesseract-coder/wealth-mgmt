import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
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
        <Route path="holdings" element={<Placeholder title="Holdings" phase={8} />} />
        <Route path="technical" element={<Technical />} />
        <Route path="technical/:ticker" element={<Technical />} />
        <Route path="mutual-funds" element={<Placeholder title="Mutual Funds" phase={8} />} />
        <Route path="screener" element={<Placeholder title="Screener" phase={9} />} />
        <Route path="watchlist" element={<Placeholder title="Watchlist" phase={9} />} />
        <Route path="settings" element={<Placeholder title="Settings" phase={8} />} />
        <Route path="*" element={<Placeholder title="Not found" phase={0} />} />
      </Route>
    </Routes>
  );
}
