import type { Metadata } from "next";

import { TransactionReviewWorkspace, type TransactionQuery } from "./transaction-review-workspace";

export const metadata: Metadata = { title: "Transaction Review | ClearPath Finance" };

function values(value: string | string[] | undefined) {
  return Array.isArray(value) ? value : value ? [value] : [];
}

export default async function TransactionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const query: TransactionQuery = {
    q: typeof params.q === "string" ? params.q : "",
    categoryIds: values(params.category_id),
    categoryNames: typeof params.category_names === "string" ? params.category_names : "",
    accountIds: values(params.account_id),
    minAmount: typeof params.min_amount === "string" ? params.min_amount : "",
    maxAmount: typeof params.max_amount === "string" ? params.max_amount : "",
    month: typeof params.month === "string" ? params.month : "",
    ids: typeof params.ids === "string" ? params.ids : "",
    sort: typeof params.sort === "string" ? params.sort : "date_desc",
    page: typeof params.page === "string" ? params.page : "1",
    importMode: params.import === "csv",
  };
  return <TransactionReviewWorkspace query={query} />;
}
