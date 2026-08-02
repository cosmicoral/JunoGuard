import { describe, expect, it } from "vitest";

import { PRODUCT_LINKS } from "./Sidebar";

describe("signed-in product navigation", () => {
  it("links directly to each public product section", () => {
    expect(PRODUCT_LINKS).toEqual([
      { href: "/#product", label: "Product overview" },
      { href: "/#how", label: "How it works" },
      { href: "/#architecture", label: "Architecture" },
      { href: "/#install", label: "Install guide" },
    ]);
  });
});
