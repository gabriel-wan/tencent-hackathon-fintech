/**
 * The cookie that remembers whether the sidebar is collapsed. In lib/, not in the "use client" sidebar file:
 * a server component importing a constant from a client file gets a reference, not the string.
 */
export const SIDEBAR_COOKIE = "kb_sidebar";
