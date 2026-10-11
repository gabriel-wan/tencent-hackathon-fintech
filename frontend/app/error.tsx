"use client";

import Link from "next/link";
import { useEffect } from "react";

import { SystemPage } from "@/components/system-page";
import { Button } from "@/components/ui/button";

// Something in a page threw. The error itself stays in the browser console (development) and the server log:
// never on the page, where it could show internals.
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <SystemPage
      title="Something went wrong"
      actions={
        <>
          <Button onClick={reset}>Try again</Button>
          <Button asChild variant="outline">
            <Link href="/">Back to KnowBuddy</Link>
          </Button>
        </>
      }
    >
      This page couldn&apos;t load. Trying again usually works; if it keeps happening, tell your admin
      {error.digest ? ` and quote reference ${error.digest}` : ""}.
    </SystemPage>
  );
}
