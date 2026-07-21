import type { Metadata } from "next";

import { PolicyView } from "../(legal)/policy-view";
import { PRIVACY_POLICY } from "@/lib/legal-content";

export const metadata: Metadata = { title: "Privacy Policy | ClearPath Finance" };

export default function PrivacyPage() {
  return <PolicyView policy={PRIVACY_POLICY} />;
}
