import type { Metadata } from "next";
import type { ReactNode } from "react";

import { SkipLink } from "@/components/skip-link";
import { ThemeProvider } from "@/components/theme-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Internal Brain",
};

// Route groups (folder names in brackets do not appear in URLs):
//   app/(app)/     signed-in pages, behind the session gate in (app)/layout.tsx
//   app/(public)/  /login and /status, no session needed
// System font stack (Tailwind's default font-sans): no web-font download.
// suppressHydrationWarning: next-themes sets the class on <html> before React hydrates.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col">
        <SkipLink />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
