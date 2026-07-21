import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePendingMutations } from "./use-pending-mutations";

/**
 * Workspaces previously shared one `busy` boolean, so saving a category on one
 * transaction disabled every control in the list. These assert the isolation
 * that replaced it.
 */
describe("usePendingMutations", () => {
  it("starts with nothing pending", () => {
    const { result } = renderHook(() => usePendingMutations());
    expect(result.current.anyPending).toBe(false);
    expect(result.current.isPending("POST /api/transactions/1/category")).toBe(false);
  });

  it("keeps concurrent mutations on different rows independent", () => {
    const { result } = renderHook(() => usePendingMutations());
    const rowOne = "POST /api/transactions/1/category";
    const rowTwo = "POST /api/transactions/2/category";

    act(() => result.current.start(rowOne));

    expect(result.current.isPending(rowOne)).toBe(true);
    // The whole point: row 2 stays interactive while row 1 saves.
    expect(result.current.isPending(rowTwo)).toBe(false);
    expect(result.current.isPendingMatching("/transactions/1")).toBe(true);
    expect(result.current.isPendingMatching("/transactions/2")).toBe(false);
    expect(result.current.anyPending).toBe(true);

    act(() => result.current.stop(rowOne));
    expect(result.current.anyPending).toBe(false);
  });

  it("tracks several in-flight mutations at once", () => {
    const { result } = renderHook(() => usePendingMutations());
    act(() => {
      result.current.start("POST /api/transactions/1/category");
      result.current.start("POST /api/transactions/2/category");
    });
    expect(result.current.isPendingMatching("/transactions/1")).toBe(true);
    expect(result.current.isPendingMatching("/transactions/2")).toBe(true);

    act(() => result.current.stop("POST /api/transactions/1/category"));
    expect(result.current.isPendingMatching("/transactions/1")).toBe(false);
    // Row 2 is still saving; clearing row 1 must not clear it.
    expect(result.current.isPendingMatching("/transactions/2")).toBe(true);
    expect(result.current.anyPending).toBe(true);
  });

  it("ignores stopping a key that was never started", () => {
    const { result } = renderHook(() => usePendingMutations());
    act(() => result.current.stop("POST /api/transactions/9/category"));
    expect(result.current.anyPending).toBe(false);
  });
});
