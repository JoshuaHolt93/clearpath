import type { Metadata } from "next";

import { OnboardingWorkspace } from "./onboarding-workspace";

export const metadata: Metadata = { title: "Setup - ClearPath Finance" };

type PageProps = { searchParams: Promise<{ step?: string }> };

export default async function OnboardingPage({ searchParams }: PageProps) {
  const { step } = await searchParams;
  const initialStep = step === "income" || step === "transactions" ? step : "connect";
  return <OnboardingWorkspace initialStep={initialStep} />;
}
