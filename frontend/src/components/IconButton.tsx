import type { ReactNode } from "react";

/** How a tooltip looks: a small dark label under the button, shown on hover or keyboard focus of the `group` around it. */
export const TOOLTIP_CLASS =
  "pointer-events-none absolute top-full right-0 z-30 mt-1.5 rounded-md bg-[var(--text-h)] px-2 py-1 text-[11px] font-medium whitespace-nowrap text-[var(--bg)] opacity-0 shadow-lg transition-opacity delay-100 group-focus-within:opacity-100 group-hover:opacity-100";

/** The same tooltip, centred under its button instead of lined up with the button's right edge: for buttons that are not at the edge. */
export const TOOLTIP_CENTERED_CLASS = TOOLTIP_CLASS.replace("right-0", "left-1/2 -translate-x-1/2");

/** A round icon-only button whose name appears in a tooltip on hover or keyboard focus. The name is also the accessible label, so
 * a screen reader announces it, and the tooltip itself is hidden from it (it would only say the same thing twice). */
export function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        onClick={onClick}
        aria-label={label}
        className="flex h-8 w-8 items-center justify-center rounded-full xl:h-7 xl:w-7 border border-[var(--border)] bg-[var(--bg-alt)] text-[var(--text)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none"
      >
        {children}
      </button>
      <span
        aria-hidden="true"
        className={TOOLTIP_CLASS}
      >
        {label}
      </span>
    </span>
  );
}
