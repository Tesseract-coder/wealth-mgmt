import { lazy, Suspense, type ComponentProps, type ComponentType } from "react";
import { Loading, Skeleton } from "../components/ui";

/**
 * The chart components, loaded on first use. The chart libraries (Recharts and
 * lightweight-charts, ~570 KB together) stay out of the first page load; each page
 * fetches them only when it draws a chart. Same props as the real components.
 */
function deferred<C extends ComponentType<any>>(load: () => Promise<C>, label: string, height: string) {
  const Lazy = lazy(() => load().then((default_) => ({ default: default_ })));
  return function Deferred(props: ComponentProps<C>) {
    return (
      <Suspense
        fallback={
          <Loading label={label}>
            <Skeleton className={`${height} w-full`} />
          </Loading>
        }
      >
        <Lazy {...props} />
      </Suspense>
    );
  };
}

const priceChart = () => import("./PriceChart");
const portfolioCharts = () => import("./PortfolioCharts");

export const PriceChart = deferred(() => priceChart().then((m) => m.PriceChart), "the price chart", "h-96");
export const AllocationDonut = deferred(() => portfolioCharts().then((m) => m.AllocationDonut), "the chart", "h-64");
export const SectorBars = deferred(() => portfolioCharts().then((m) => m.SectorBars), "the chart", "h-64");
export const ComparisonLine = deferred(() => portfolioCharts().then((m) => m.ComparisonLine), "the chart", "h-60");
