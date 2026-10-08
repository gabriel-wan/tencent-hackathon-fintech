// First thing a keyboard user reaches: jumps past the banner and header to
// the page's <main id="main">. Visible only while focused.
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50"
    >
      Skip to content
    </a>
  );
}
