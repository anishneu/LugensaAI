import { Disclosure, DisclosureButton, DisclosurePanel } from "@headlessui/react";
import { ChevronRightIcon } from "@heroicons/react/24/outline";
import type { ResearchTraceStep } from "../types";

interface ResearchTraceProps {
  trace: ResearchTraceStep[];
}

/** The agent's own log: every decision it made, in order, so an answer can be audited rather than trusted. */
export function ResearchTrace({ trace }: ResearchTraceProps) {
  return (
    <Disclosure as="section" className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-alt)]">
      <DisclosureButton className="group flex w-full items-center gap-2.5 px-5 py-3.5 text-left text-sm font-semibold text-[var(--text-h)] outline-none data-[focus]:ring-2 data-[focus]:ring-violet-500">
        <ChevronRightIcon className="h-4 w-4 text-[var(--text-muted)] transition-transform group-data-[open]:rotate-90" aria-hidden="true" />
        Research trace
        <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-[11px] font-normal text-[var(--text-muted)]">{trace.length} steps</span>
      </DisclosureButton>
      <DisclosurePanel transition className="origin-top duration-200 ease-out data-[closed]:-translate-y-1 data-[closed]:opacity-0">
        <ol className="m-0 flex list-none flex-col gap-3 border-t border-[var(--border)] px-5 py-4">
          {trace.map((step, i) => (
            <li key={i} className="flex gap-3 text-[13px] leading-relaxed">
              <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-[var(--accent-bg)] text-[10px] font-bold text-[var(--accent)]">
                {i + 1}
              </span>
              <span className="min-w-0">
                <span className="mb-0.5 block text-[10.5px] font-semibold tracking-[0.08em] text-[var(--text-muted)] uppercase">
                  {step.stage.replace(/_/g, " ")}
                </span>
                <span className="text-[var(--text)]" dir="auto">
                  {step.description}
                </span>
              </span>
            </li>
          ))}
        </ol>
      </DisclosurePanel>
    </Disclosure>
  );
}
