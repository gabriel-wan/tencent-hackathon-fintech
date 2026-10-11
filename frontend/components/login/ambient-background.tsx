/**
 * Brand-coloured light flowing behind the sign-in page. Three soft, oval shapes wander, turn and swell on their
 * own, on loops of different lengths so the pattern never visibly repeats; each also shifts with the pointer by a
 * different amount and direction (`--px`, `--py`, from usePointerMotion), so they slide past each other like
 * layers; and a soft glow trails the pointer (`--mx`, `--my`, `--glow`). Only transform and opacity move.
 * Decorative: hidden from screen readers, never clickable. Fixed to the viewport, so it can never make the page
 * scroll sideways. Still for reduced motion (the global rule in globals.css stops the flow; the hook never writes
 * the pointer).
 */
export function AmbientBackground() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -top-32 right-[-12%] [transform:translate3d(calc(var(--px,0)*-60px),calc(var(--py,0)*-40px),0)]">
        <div className="h-[30rem] w-[40rem] rounded-full bg-primary/15 blur-3xl animate-[kb-flow-a_18s_ease-in-out_infinite] dark:bg-primary/10" />
      </div>
      <div className="absolute top-1/4 left-[-14%] [transform:translate3d(calc(var(--px,0)*80px),calc(var(--py,0)*60px),0)]">
        <div className="h-[34rem] w-[26rem] rounded-full bg-brand-buddy/15 blur-3xl animate-[kb-flow-b_23s_ease-in-out_-6s_infinite] dark:bg-brand-buddy/10" />
      </div>
      <div className="absolute right-[15%] bottom-[-22%] [transform:translate3d(calc(var(--px,0)*40px),calc(var(--py,0)*-70px),0)]">
        <div className="h-[26rem] w-[36rem] rounded-full bg-brand-know/10 blur-3xl animate-[kb-flow-c_29s_ease-in-out_-12s_infinite] dark:bg-brand-know/15" />
      </div>
      <div className="absolute top-0 left-0 size-[26rem] rounded-full bg-primary/10 opacity-[var(--glow,0)] blur-3xl transition-opacity duration-700 [transform:translate3d(calc(var(--mx,50vw)-50%),calc(var(--my,50vh)-50%),0)] dark:bg-primary/10" />
    </div>
  );
}
