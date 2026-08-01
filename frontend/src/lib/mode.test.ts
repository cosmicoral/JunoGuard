import { describe, expect, it } from "vitest";
import { resolveDataSource, resolveJunoMode } from "./mode";
import { sumBillableCost } from "./spend";
import type { AgentAction } from "./types";

describe("resolveDataSource", () => {
  it("prefers Supabase over SSE over mock", () => {
    expect(resolveDataSource(true, true)).toBe("supabase");
    expect(resolveDataSource(false, true)).toBe("sse");
    expect(resolveDataSource(false, false)).toBe("mock");
  });
});

describe("resolveJunoMode", () => {
  it("honours an explicit demo declaration without credentials", () => {
    const resolved = resolveJunoMode("demo", false);
    expect(resolved).toEqual({
      mode: "demo",
      modeIsDeclared: true,
      isMisconfigured: false,
    });
  });

  it("treats declared live without Supabase as a configuration error", () => {
    const resolved = resolveJunoMode("live", false);
    expect(resolved.mode).toBe("live");
    expect(resolved.isMisconfigured).toBe(true);
  });

  it("does not soften a live build when credentials disappear", () => {
    // Removing the variable must not open the dashboard.
    expect(resolveJunoMode("live", false).isMisconfigured).toBe(true);
    expect(resolveJunoMode("live", true).isMisconfigured).toBe(false);
  });

  it("falls back to demo only when the mode is undeclared and unconfigured", () => {
    expect(resolveJunoMode(undefined, false).mode).toBe("demo");
    expect(resolveJunoMode(undefined, true).mode).toBe("live");
  });
});

describe("sumBillableCost", () => {
  it("counts flagged charges toward spend", () => {
    const rows = [
      { cost_usd: 0.1, decision: "allow" },
      { cost_usd: 0.2, decision: "flag" },
      { cost_usd: 0, decision: "block" },
    ] as AgentAction[];
    expect(sumBillableCost(rows)).toBeCloseTo(0.3);
  });
});
