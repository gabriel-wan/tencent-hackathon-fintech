"use client";

import { useRef, type ReactNode } from "react";

import { AmbientBackground } from "@/components/login/ambient-background";
import { HeroIllustration } from "@/components/login/hero-illustration";
import { usePointerMotion } from "@/lib/use-pointer-motion";

/** The sign-in page's top section: the given content on the left, the answer card on the right, and the motion. */
export function LoginHero({ children }: { children: ReactNode }) {
  const area = useRef<HTMLElement>(null);
  const card = useRef<HTMLDivElement>(null);
  usePointerMotion(area, card);
  return (
    <section
      ref={area}
      className="relative isolate grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)] lg:py-10"
    >
      <AmbientBackground />
      {children}
      <div className="hidden sm:block">
        <HeroIllustration cardRef={card} />
      </div>
    </section>
  );
}
