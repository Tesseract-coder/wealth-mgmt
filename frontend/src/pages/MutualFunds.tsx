import { Link, useParams } from "react-router-dom";
import { FundHoldings, FundReportView } from "../components/FundView";

/** Your funds with Continue / Review / Switch signals, and a detail view per scheme. */
export function MutualFunds() {
  const { code } = useParams();
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Mutual funds</h1>
        <p className="text-sm text-slate-500">
          Returns, risk, cost and overlap for each fund, against its category benchmark, with a Continue / Review / Switch signal and the reasons.
        </p>
      </div>
      {code ? (
        <>
          <Link to="/mutual-funds" className="text-sm underline">
            ← all funds
          </Link>
          <FundReportView code={code} />
        </>
      ) : (
        <FundHoldings />
      )}
    </div>
  );
}
