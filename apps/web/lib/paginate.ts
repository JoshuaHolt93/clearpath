/**
 * Port of Flask-SQLAlchemy's `iter_pages`, which Flask's transactions template
 * calls as iter_pages(left_edge=1, right_edge=1, left_current=2,
 * right_current=2) (templates/transactions/index.html:747).
 *
 * Yields page numbers to display, with `null` marking an elided run rendered
 * as an ellipsis. Always keeps the first and last page reachable so you can
 * jump to either end regardless of where you are.
 */
export function iterPages(
  page: number,
  totalPages: number,
  { leftEdge = 1, leftCurrent = 2, rightCurrent = 2, rightEdge = 1 } = {},
): (number | null)[] {
  const out: (number | null)[] = [];
  let last = 0;
  for (let num = 1; num <= totalPages; num += 1) {
    const nearStart = num <= leftEdge;
    const nearCurrent = num > page - leftCurrent - 1 && num < page + rightCurrent + 1;
    const nearEnd = num > totalPages - rightEdge;
    if (nearStart || nearCurrent || nearEnd) {
      if (last + 1 !== num) out.push(null);
      out.push(num);
      last = num;
    }
  }
  return out;
}
