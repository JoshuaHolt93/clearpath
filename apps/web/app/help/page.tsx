import type { Metadata } from "next";

import { HelpWorkspace } from "./help-workspace";

export const metadata: Metadata = { title: "Help | ClearPath Finance" };

export default async function HelpPage({ searchParams }: { searchParams: Promise<{ topic?: string | string[] }> }) {
  const params = await searchParams;
  const topic = Array.isArray(params.topic) ? params.topic[0] : params.topic;
  return <HelpWorkspace selectedTopic={topic ?? ""} />;
}
