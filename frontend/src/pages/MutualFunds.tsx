import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { FundHoldings, FundReportView } from "../components/FundView";
import { PageHeader } from "../components/ui";

/** Your funds with Continue / Review / Switch signals and a Score Shape each, and a detail view per scheme. */
export function MutualFunds() {
  const { code } = useParams();
  return (
    <div className="space-y-4">
      {code ? (
        <>
          <Link to="/mutual-funds" className="inline-flex items-center gap-1 text-sm text-fg-muted hover:text-fg">
            <ArrowLeft aria-hidden className="size-4" /> All funds
          </Link>
          <FundReportView code={code} />
        </>
      ) : (
        <>
          <PageHeader
            title="Mutual funds"
            description="Returns, consistency, risk and cost for each fund against its category benchmark, with a Continue / Review / Switch signal and the reasons."
          />
          <FundHoldings />
        </>
      )}
    </div>
  );
}
