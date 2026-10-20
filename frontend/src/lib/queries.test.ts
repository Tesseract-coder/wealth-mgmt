import { invalidateData, makeQueryClient } from "./queries";

test("invalidateData marks data queries stale and leaves static ones alone", async () => {
  const qc = makeQueryClient();
  qc.setQueryData(["portfolio-summary"], { total: 1 });
  qc.setQueryData(["checks-holdings", "long_term", "high"], { holdings: [] });
  qc.setQueryData(["config"], { version: 1 });
  expect(qc.getQueryState(["portfolio-summary"])?.isInvalidated).toBe(false);
  await invalidateData(qc);
  expect(qc.getQueryState(["portfolio-summary"])?.isInvalidated).toBe(true);
  expect(qc.getQueryState(["checks-holdings", "long_term", "high"])?.isInvalidated).toBe(true);
  expect(qc.getQueryState(["config"])?.isInvalidated).toBe(false);
});

test("results are reused between pages for a few minutes", () => {
  expect(makeQueryClient().getDefaultOptions().queries?.staleTime).toBe(5 * 60_000);
});
