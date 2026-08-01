import type { AgentAction } from "./types";

/**
 * Billable spend is any action that cost money, whatever it was labelled.
 * `flag` is proceedable — the provider was called and the charge is real — so
 * filtering to `allow` understates spend exactly when it matters most.
 */
export function sumBillableCost(rows: AgentAction[]): number {
  let total = 0;
  for (const a of rows) if (a.cost_usd) total += Number(a.cost_usd);
  return total;
}
