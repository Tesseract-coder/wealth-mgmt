import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analysisApi, type StyleKey } from "../api/client";
import { formatDate } from "../lib/format";
import { analysisQuery } from "../lib/links";
import { FreshnessBadge } from "./MarketData";
import { Alert, Card, ErrorState, SkeletonCard } from "./ui";

/** Holdings' Technical view: bullish and bearish reading counts and the main reading each way. */
export function TechnicalHoldings({ style }: { style: StyleKey | null }) {
  const q = useQuery({ queryKey: ["tech-holdings", style], queryFn: () => analysisApi.holdings(style) });
  if (q.isError) return <ErrorState title="Couldn't summarise your holdings" detail={q.error.message} onRetry={() => void q.refetch()} />;
  if (!q.data) return <SkeletonCard label="your holdings" lines={6} />;
  if (q.data.length === 0)
    return (
      <Alert tone="info">
        No stock holdings yet. <Link className="underline" to="/import">Import your Groww file</Link>, or search for any stock with Ctrl+K.
      </Alert>
    );
  return (
    <Card title="Your holdings">
      <p className="mb-3 text-sm text-fg-subtle">
        Uses cached prices only. If a row says Unavailable, run <b>Refresh now</b> in Settings → Data refresh.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-fg-subtle">
            <tr>
              <th className="py-1 pr-2">Stock</th>
              <th className="pr-2">As of</th>
              <th className="pr-2 text-right">▲ Bullish</th>
              <th className="pr-2 text-right">▼ Bearish</th>
              <th className="pr-2">Main readings</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((r) => (
              <tr key={r.ticker} className="border-t border-border align-top">
                <td className="py-1 pr-2">
                  <Link className="underline" to={`/analysis/${encodeURIComponent(r.ticker)}${analysisQuery(style, "technical")}`}>
                    {r.label}
                  </Link>
                  <div className="font-mono text-xs text-fg-subtle">{r.ticker}</div>
                </td>
                <td className="pr-2 whitespace-nowrap">{formatDate(r.as_of)}</td>
                <td className="pr-2 text-right tabular-nums">{r.bullish}</td>
                <td className="pr-2 text-right tabular-nums">{r.bearish}</td>
                <td className="pr-2 text-xs">
                  {r.top_bullish.slice(0, 1).map((t) => (
                    <div key={t}>▲ {t}</div>
                  ))}
                  {r.top_bearish.slice(0, 1).map((t) => (
                    <div key={t}>▼ {t}</div>
                  ))}
                </td>
                <td>
                  <FreshnessBadge f={r.freshness} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
