import { categoryDeleteInputSchema, categoryUpdateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ categoryId: string }> };
const readCategoryId = async (context: Context) => Number((await context.params).categoryId);

export async function PATCH(request: Request, context: Context) {
  const id = await readCategoryId(context);
  if (!Number.isInteger(id) || id < 1) return NextResponse.json({ message: "Category not found." }, { status: 404 });
  const parsed = categoryUpdateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the category details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/categories/{category_id}", { params: { path: { category_id: id } }, body: { name: parsed.data.name, kind: parsed.data.kind }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that category.") }, { status: response.status });
    return NextResponse.json({ categoryId: data.id, name: data.name });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const id = await readCategoryId(context);
  if (!Number.isInteger(id) || id < 1) return NextResponse.json({ message: "Category not found." }, { status: 404 });
  const parsed = categoryDeleteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Check the replacement category." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/categories/{category_id}", { params: { path: { category_id: id } }, body: { replacement_category_id: parsed.data.replacementCategoryId }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not remove that category.") }, { status: response.status });
    return NextResponse.json({ deletedCategoryId: data.deleted_category_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
