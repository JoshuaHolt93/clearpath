import type { Metadata } from "next";

import { PolicyView } from "../(legal)/policy-view";
import { TERMS_OF_SERVICE } from "@/lib/legal-content";

export const metadata: Metadata = { title: "Terms Of Service | ClearPath Finance" };

export default function TermsPage() {
  return <PolicyView policy={TERMS_OF_SERVICE} />;
}
