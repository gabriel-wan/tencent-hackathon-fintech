/**
 * Faint brand-coloured light drifting behind the sign-in page, leaning a little toward the pointer (the `--px`
 * and `--py` that usePointerMotion writes on the hero). Decorative: hidden from screen readers, never clickable.
 * Fixed to the viewport, so it can never make the page scroll sideways. Still for reduced motion (the global rule
 * in globals.css stops the drift; the hook never writes the pointer).
 */
export function AmbientBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 transition-transform duration-700 ease-out [transform:translate3d(calc(var(--px,0)*28px),calc(var(--py,0)*28px),0)]">
        <div className="absolute -top-24 right-[-10%] size-[34rem] rounded-full bg-primary/15 blur-3xl animate-[kb-drift_26s_ease-in-out_infinite_alternate] dark:bg-primary/10" />
        <div className="absolute top-1/3 left-[-12%] size-[28rem] rounded-full bg-brand-buddy/15 blur-3xl animate-[kb-drift_32s_ease-in-out_-8s_infinite_alternate-reverse] dark:bg-brand-buddy/10" />
        <div className="absolute right-[20%] bottom-[-18%] size-[26rem] rounded-full bg-brand-know/10 blur-3xl animate-[kb-drift_38s_ease-in-out_-16s_infinite_alternate] dark:bg-brand-know/15" />
      </div>
    </div>
  );
}
