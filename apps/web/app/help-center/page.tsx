import { redirect } from "next/navigation";

export default async function HelpCenterAlias({ searchParams }: { searchParams: Promise<{ topic?: string | string[] }> }) {
  const params = await searchParams;
  const topic = Array.isArray(params.topic) ? params.topic[0] : params.topic;
  redirect(topic ? `/help?topic=${encodeURIComponent(topic)}` : "/help");
}
