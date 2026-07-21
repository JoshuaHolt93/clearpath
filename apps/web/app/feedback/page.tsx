import type { Metadata } from "next";

import { FeedbackWorkspace } from "./feedback-workspace";

export const metadata: Metadata = { title: "Feedback | ClearPath Finance" };

export default function FeedbackPage() {
  return <FeedbackWorkspace />;
}
