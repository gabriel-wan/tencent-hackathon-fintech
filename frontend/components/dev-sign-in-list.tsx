"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { devSignIn } from "@/lib/api/client";
import type { DevUser } from "@/lib/api/types";

/**
 * DEVELOPMENT ONLY: one button per seeded user (POST /api/dev/session).
 * Names come from the backend as-is; no personas are hard-coded here.
 * After signing in, a full page load (not client navigation) guarantees no
 * state from a previous person survives (SECURITY.md T6).
 */
export function DevSignInList({ users }: { users: DevUser[] }) {
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function signIn(user: DevUser) {
    setPendingId(user.id);
    setError(null);
    try {
      await devSignIn(user.id);
      window.location.assign("/");
    } catch {
      setError(`Could not sign in as ${user.name}. Is the backend running?`);
      setPendingId(null);
    }
  }

  return (
    <div className="grid gap-2">
      {users.map((user) => (
        <Button
          key={user.id}
          variant="outline"
          className="h-auto min-h-11 justify-between px-3 py-2 text-left whitespace-normal"
          disabled={pendingId !== null}
          aria-busy={pendingId === user.id}
          onClick={() => signIn(user)}
        >
          <span>
            <span className="block font-medium">{user.name}</span>
            <span className="block text-xs text-muted-foreground">{user.email}</span>
          </span>
          {user.is_admin ? <Badge variant="secondary">ADMIN</Badge> : null}
        </Button>
      ))}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
