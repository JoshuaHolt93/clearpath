import { describe, expect, it } from "vitest";

import { returnLabel, safeLocalReturnUrl } from "./safe-return-url";

describe("safeLocalReturnUrl", () => {
  it("keeps same-origin paths, including query and hash", () => {
    expect(safeLocalReturnUrl("/monthly-plan?section=budgets")).toBe("/monthly-plan?section=budgets");
    expect(safeLocalReturnUrl("/transactions#transaction-21")).toBe("/transactions#transaction-21");
  });

  it("rejects anything that could leave the origin", () => {
    // return_to comes from the query string, so these are the open-redirect cases.
    for (const hostile of [
      "https://evil.com/steal",
      "http://evil.com",
      "//evil.com",
      "/\\evil.com",
      "/path\\..\\evil",
      "javascript:alert(1)",
      "mailto:a@b.c",
    ]) {
      expect(safeLocalReturnUrl(hostile), hostile).toBe("");
    }
  });

  it("falls back for empty, missing, or relative values", () => {
    expect(safeLocalReturnUrl(null)).toBe("");
    expect(safeLocalReturnUrl(undefined)).toBe("");
    expect(safeLocalReturnUrl("   ")).toBe("");
    expect(safeLocalReturnUrl("monthly-plan")).toBe("");
    expect(safeLocalReturnUrl("", "/dashboard")).toBe("/dashboard");
  });
});

describe("returnLabel", () => {
  it("names the budget workspace, matching Flask", () => {
    expect(returnLabel("/monthly-plan?section=budgets")).toBe("Back to Budgets");
    expect(returnLabel("/budgets")).toBe("Back to Budgets");
  });

  it("is generic for anywhere else", () => {
    expect(returnLabel("/dashboard")).toBe("Back to previous page");
    expect(returnLabel("/analytics")).toBe("Back to previous page");
  });
});
