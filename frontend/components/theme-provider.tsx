"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

// Adds the `dark` class to <html> before first paint, so dark systems see no
// light flash. The choice (System / Light / Dark) is a per-browser preference
// kept in localStorage by next-themes; it is not app data.
export function ThemeProvider(props: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    />
  );
}
