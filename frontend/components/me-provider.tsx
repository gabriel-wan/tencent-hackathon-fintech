"use client";

import { createContext, useContext, type ReactNode } from "react";

import type { Me } from "@/lib/api/types";

// The signed-in user, read once by the (app) layout from GET /api/me.
// For display only (name, admin links): the backend makes every decision.
const MeContext = createContext<Me | null>(null);

export function MeProvider({ me, children }: { me: Me; children: ReactNode }) {
  return <MeContext.Provider value={me}>{children}</MeContext.Provider>;
}

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe() must be used inside the (app) layout");
  return me;
}
