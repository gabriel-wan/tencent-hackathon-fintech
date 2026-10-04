import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppHeader } from "@/components/app-header";
import { MockBadge } from "@/components/mock-badge";
import { ThemeProvider } from "@/components/theme-provider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Internal Brain",
};

// System font stack (Tailwind's default font-sans): no web-font download.
// suppressHydrationWarning: next-themes sets the class on <html> before React hydrates.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col">
        <ThemeProvider>
          <AppHeader actions={<MockBadge />} />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
