import type { ReactNode } from "react";
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@headlessui/react";
import { ChevronDownIcon } from "@heroicons/react/24/outline";

export interface BrowserTabItem {
  id: string;
  label: string;
  icon: ReactNode;
  /** Shown beside the name (a rating, a count), so the tab says what it holds without being opened. Hidden when the panel is
   * too narrow for it and the name together; the alert dot below is not. */
  badge?: ReactNode;
  /** A pulsing dot on the tab that stays visible at any width: something on this tab changed and hasn't been looked at. */
  alert?: boolean;
  content: ReactNode;
}

interface BrowserTabsProps {
  tabs: BrowserTabItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Tabs drawn as a browser window's: rounded tops, and the selected tab flowing into the panel under it (the shape is in
 * index.css). It is a different look from the answer's underlined tabs and the live feed's pills on purpose, since this is
 * a different kind of thing: sources for the place itself, not sections of one answer. The chevron at the end folds the
 * panel away; every tab's content stays mounted, so a folded or unselected tab keeps loading and keeps its badge current.
 */
export function BrowserTabs({ tabs, selectedId, onSelect, open, onOpenChange }: BrowserTabsProps) {
  const selectedIndex = Math.max(0, tabs.findIndex((tab) => tab.id === selectedId));

  return (
    <div className="browser-tabs @container overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--tab-strip)]">
      <TabGroup
        selectedIndex={selectedIndex}
        onChange={(index) => {
          onSelect(tabs[index].id);
          onOpenChange(true);
        }}
      >
        <div className="flex items-end gap-0.5 pt-2 pr-2 pl-3">
          <TabList className="flex min-w-0 flex-1 items-end gap-0.5">
            {tabs.map((tab) => (
              <Tab
                key={tab.id}
                // Picking the tab that is already selected while the panel is folded opens it.
                onClick={() => onOpenChange(true)}
                className="browser-tab flex min-w-0 items-center gap-2 px-3.5 py-2 text-[12.5px] font-medium text-[var(--text-muted)] outline-none data-[focus]:ring-2 data-[focus]:ring-violet-500 data-[focus]:ring-inset data-[hover]:text-[var(--text-h)] data-[selected]:text-[var(--text-h)]"
              >
                <span className="flex-shrink-0" aria-hidden="true">
                  {tab.icon}
                </span>
                <span className="whitespace-nowrap">{tab.label}</span>
                {tab.alert && (
                  <span className="relative flex h-2 w-2 flex-shrink-0" role="status" aria-label="Updated">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent)] opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent)]" />
                  </span>
                )}
                {tab.badge && <span className="hidden flex-shrink-0 items-center gap-1.5 text-[11px] font-normal text-[var(--text-muted)] @lg:flex">{tab.badge}</span>}
              </Tab>
            ))}
          </TabList>
          <button
            type="button"
            onClick={() => onOpenChange(!open)}
            aria-expanded={open}
            aria-label={open ? "Fold this panel" : "Open this panel"}
            title={open ? "Fold" : "Open"}
            className="mb-1 flex-shrink-0 rounded-full p-1.5 text-[var(--text-muted)] transition hover:bg-black/10 hover:text-[var(--text-h)] focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:outline-none dark:hover:bg-white/10"
          >
            <ChevronDownIcon className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
          </button>
        </div>

        <TabPanels className={open ? "block border-t border-[var(--border)] bg-[var(--tab-active)]" : "hidden"}>
          {tabs.map((tab) => (
            <TabPanel key={tab.id} unmount={false} className="p-4 outline-none">
              {tab.content}
            </TabPanel>
          ))}
        </TabPanels>
      </TabGroup>
    </div>
  );
}
