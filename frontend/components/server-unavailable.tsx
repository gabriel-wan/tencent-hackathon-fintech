import { ServerCrash } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

// Shown when the backend cannot be reached. Deliberately not a redirect to
// /login: that would suggest the user had been signed out.
export function ServerUnavailable() {
  return (
    <Alert variant="destructive">
      <ServerCrash aria-hidden="true" />
      <AlertTitle>Can&apos;t reach the server</AlertTitle>
      <AlertDescription>
        <p>
          The assistant&apos;s server is not responding. Please{" "}
          <a href="" className="font-medium underline underline-offset-4">
            try again
          </a>{" "}
          in a moment.
        </p>
      </AlertDescription>
    </Alert>
  );
}
