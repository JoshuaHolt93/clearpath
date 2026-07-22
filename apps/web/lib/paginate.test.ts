import { describe, expect, it } from "vitest";

import { iterPages } from "./paginate";

/**
 * Expectations hand-derived from Flask-SQLAlchemy's iter_pages with the
 * arguments Flask's template uses (left_edge=1, left_current=2,
 * right_current=2, right_edge=1), not read off this implementation.
 */
describe("iterPages", () => {
  it("lists every page only while the window covers them", () => {
    expect(iterPages(1, 4)).toEqual([1, 2, 3, 4]);
    // At page 1 of 5, page 4 is outside the +2 window and is not the right
    // edge, so Flask elides it: 1 2 3 ... 5. Verified by tracing
    // Flask-SQLAlchemy's iter_pages, not by reading our implementation.
    expect(iterPages(1, 5)).toEqual([1, 2, 3, null, 5]);
    expect(iterPages(3, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("elides only on the right near the start", () => {
    // 1 (edge) + 2,3 (within 2 after current) then a gap, then last.
    expect(iterPages(1, 20)).toEqual([1, 2, 3, null, 20]);
  });

  it("elides both sides in the middle", () => {
    expect(iterPages(10, 20)).toEqual([1, null, 8, 9, 10, 11, 12, null, 20]);
  });

  it("elides only on the left near the end", () => {
    expect(iterPages(20, 20)).toEqual([1, null, 18, 19, 20]);
  });

  it("keeps the first and last page reachable from anywhere", () => {
    for (const page of [1, 4, 9, 15, 20]) {
      const pages = iterPages(page, 20);
      expect(pages, `page ${page}`).toContain(1);
      expect(pages, `page ${page}`).toContain(20);
    }
  });

  it("handles a single page and an empty result set", () => {
    expect(iterPages(1, 1)).toEqual([1]);
    expect(iterPages(1, 0)).toEqual([]);
  });

  it("never emits consecutive ellipses or duplicates", () => {
    for (let total = 1; total <= 30; total += 1) {
      for (let page = 1; page <= total; page += 1) {
        const pages = iterPages(page, total);
        const numbers = pages.filter((p): p is number => p !== null);
        expect(new Set(numbers).size, `dupes at ${page}/${total}`).toBe(numbers.length);
        for (let i = 1; i < pages.length; i += 1) {
          expect(pages[i] === null && pages[i - 1] === null, `double gap at ${page}/${total}`).toBe(false);
        }
        // Ascending order, so the control always reads left to right.
        expect([...numbers].sort((a, b) => a - b)).toEqual(numbers);
      }
    }
  });
});
