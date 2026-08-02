import { describe, expect, it } from "vitest";

import { normalizeBlast } from "./events";

describe("normalizeBlast", () => {
  it("preserves scope provenance for the dashboard", () => {
    expect(
      normalizeBlast({
        credentials_in_scope: ["OPENAI_API_KEY"],
        network_egress: "agent network access (no attempt observed)",
        write_access: "agent workspace (read/write)",
        summary: "provider credential theft",
        scope_source: "client_declared",
        scope_is_attested: false,
      }),
    ).toEqual({
      credentials: ["OPENAI_API_KEY"],
      network_egress: "agent network access (no attempt observed)",
      write_access: "agent workspace (read/write)",
      summary: "provider credential theft",
      scope_source: "client_declared",
      scope_is_attested: false,
    });
  });
});
