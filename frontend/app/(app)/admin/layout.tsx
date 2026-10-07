import { redirect, unstable_rethrow } from "next/navigation";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { getMe } from "@/lib/api/server";

/**
 * Admin pages: non-admins are sent back to the chat.
 *
 * UX only, not security. ADR-007 limits the audit log and boundary to the
 * admin role, and every admin API route checks is_admin itself and returns
 * 403. The parent (app) layout has already handled "signed
 * out" and "backend down".
 */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  await connection();
  let isAdmin = false;
  try {
    isAdmin = (await getMe()).is_admin;
  } catch (error) {
    unstable_rethrow(error);
  }
  if (!isAdmin) redirect("/");
  return children;
}
