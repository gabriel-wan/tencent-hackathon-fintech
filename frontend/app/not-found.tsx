import type { Metadata } from "next";
import Link from "next/link";

import { SystemPage } from "@/components/system-page";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Page not found · KnowBuddy" };

// Any unknown URL. Says nothing about whether something exists behind it (INV-5).
export default function NotFound() {
  return (
    <SystemPage
      title="Page not found"
      actions={
        <Button asChild>
          <Link href="/">Back to KnowBuddy</Link>
        </Button>
      }
    >
      There&apos;s no page at this address. Check the link, or go back to asking questions.
    </SystemPage>
  );
}
