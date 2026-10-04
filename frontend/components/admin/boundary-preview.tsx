"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { MOCK_SOURCES, type MockScope } from "@/lib/mock/boundary";

// DEVELOPMENT ONLY design preview of /admin/boundary (ui-plan.md 6.4), shown
// inside <DesignPreview>. Nothing here changes the boundary or syncs: "Sync
// now" is disabled, and confirming a removal only closes the dialog.

export function BoundaryPreview() {
  const [removing, setRemoving] = useState<MockScope | null>(null);
  return (
    <div className="grid gap-4">
      {MOCK_SOURCES.map((source) => (
        <section key={source.source} aria-labelledby={`source-${source.source}`} className="grid gap-3 rounded-lg border bg-card p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 id={`source-${source.source}`} className="font-medium">
                {source.label}
              </h2>
              <p className="text-xs text-muted-foreground">Last synced: not built yet</p>
            </div>
            <Button variant="outline" size="sm" disabled>
              <RefreshCw aria-hidden="true" />
              Sync now
            </Button>
          </div>
          <ul className="grid gap-2">
            {source.scopes.map((scope) => {
              const id = `scope-${source.source}-${scope.scopeId}`;
              return (
                <li key={scope.scopeId} className="flex min-h-11 items-center gap-3">
                  <Checkbox
                    id={id}
                    checked={scope.inBoundary}
                    onCheckedChange={() => (scope.inBoundary ? setRemoving(scope) : undefined)}
                  />
                  <label htmlFor={id} className="flex min-h-11 flex-1 flex-wrap items-center gap-x-2 text-sm">
                    <span className="font-medium">{scope.title}</span>
                    <span className="text-xs text-muted-foreground">
                      {scope.detail}
                      {scope.inBoundary ? "" : " · available, not in the boundary"}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <AlertDialog open={removing !== null} onOpenChange={(open) => !open && setRemoving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {removing?.title} from the boundary?</AlertDialogTitle>
            <AlertDialogDescription>
              Its content stops appearing in answers immediately, for everyone. The change is recorded in the
              audit trail.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction>Remove (preview: does nothing)</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
