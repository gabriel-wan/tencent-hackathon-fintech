import type { ReactNode } from "react";

/** A full-page message (page not found, something broke): the icon, a title, a line, and what to do next. */
export function SystemPage({ title, children, actions }: { title: string; children: ReactNode; actions: ReactNode }) {
  return (
    <main id="main" tabIndex={-1} className="grid flex-1 place-items-center px-4 py-16 outline-none">
      <div className="grid max-w-md justify-items-center gap-4 text-center">
        <img src="/icon.svg" width={48} height={48} alt="" aria-hidden="true" />
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="leading-relaxed text-muted-foreground">{children}</p>
        <div className="flex flex-wrap justify-center gap-2">{actions}</div>
      </div>
    </main>
  );
}
