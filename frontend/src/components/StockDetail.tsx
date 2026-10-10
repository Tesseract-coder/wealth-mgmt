import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { analysisApi, signalApi, type StyleKey } from "../api/client";
import { PriceChart } from "../charts/PriceChart";
import { FundamentalReportView } from "./FundamentalView";
import { StockSignalView } from "./SignalView";

/** One stock: chart with stop/targets and S/R, the signal with reasons and history, and the
 * fundamentals table against sector medians. */
export function StockDetail({ ticker, style, fundamentalLink }: { ticker: string; style: StyleKey | null; fundamentalLink: string }) {
  // Same key as StockSignalView, so the signal is fetched once.
  const sig = useQuery({ queryKey: ["signal", ticker, style, undefined], queryFn: () => signalApi.stock(ticker, style) });
  // After the signal: by then prices are cached and this is quick.
  const tech = useQuery({ queryKey: ["technical", ticker, style], queryFn: () => analysisApi.technical(ticker, style), enabled: sig.isSuccess });
  const daily = tech.data?.timeframes.find((t) => t.interval === "1d");
  const sr = (daily?.analysis.levels.length ? daily.analysis.levels : tech.data?.context.levels) ?? [];
  const isIndex = ticker.startsWith("^");
  return (
    <div className="space-y-4">
      <PriceChart ticker={ticker} levels={sig.data?.levels ?? null} sr={sr} />
      <StockSignalView ticker={ticker} style={style} />
      {!isIndex && (
        <div className="space-y-2">
          <FundamentalReportView ticker={ticker} metricsOnly enabled={sig.isSuccess || sig.isError} />
          <p className="text-xs text-slate-500">
            F-score and all fundamental readings:{" "}
            <Link className="underline" to={fundamentalLink}>
              Fundamental tab
            </Link>
            .
          </p>
        </div>
      )}
    </div>
  );
}
