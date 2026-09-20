import { Disclosure, DisclosureButton, DisclosurePanel } from "@headlessui/react";
import { ChevronDownIcon } from "@heroicons/react/24/outline";

const FAQ: { q: string; a: string }[] = [
  {
    q: "What does it cost?",
    a: "Nothing per question. The reasoning runs on a local model on your own machine (Ollama), and the web search uses a free tier. No billed model API is involved and no model provider ever sees your questions; only the search queries it writes go to the search service.",
  },
  {
    q: "How long does an answer take?",
    a: "Minutes, not seconds: a few to about ten on a laptop, depending on your hardware. The first question after starting is slower because the models load. The app shows a live timer and an honest range while it works.",
  },
  {
    q: "Which places and languages does it cover?",
    a: "Any real place worldwide that a map knows: a neighborhood, a specific business, an address or a Google Maps plus code. For about 60 countries it also searches in the local language and translates what it finds to English, labeled as machine-translated with the original one click away.",
  },
  {
    q: "Where does the evidence come from?",
    a: "Live web search, Google Maps (ratings, hours and reviews for a specific business, when a Google key is connected), OpenStreetMap for what's nearby, Wikipedia and Wikivoyage, and forums and communities such as Reddit and each country's own.",
  },
  {
    q: "Can I trust the answer?",
    a: "You can check it, which is the point. Every claim links to the passage behind it, and a fixed non-AI checker decides whether the sources support it: the model that proposes a claim never approves it. Sentences in the overview that no source backs are flagged as the model's own inference.",
  },
  {
    q: "What can't it do?",
    a: "It can't read pages behind a login (most of Facebook, Instagram, TikTok and X), and Dcard blocks automated requests, so those posts show \"date unknown\". Search coverage is not complete, and a small place may simply have little written about it. When that happens the answer says so instead of filling the gap.",
  },
];

export function Faq() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3">
      {FAQ.map(({ q, a }) => (
        <Disclosure key={q} as="div" className="rounded-2xl border border-white/10 bg-white/[0.03] transition-colors data-[open]:border-violet-400/40 data-[open]:bg-white/[0.05]">
          <DisclosureButton className="group flex w-full items-center justify-between gap-6 px-6 py-5 text-left text-[16px] font-semibold text-white outline-none data-[focus]:ring-2 data-[focus]:ring-violet-400">
            {q}
            <ChevronDownIcon className="h-5 w-5 flex-shrink-0 text-white/50 transition-transform group-data-[open]:rotate-180" aria-hidden="true" />
          </DisclosureButton>
          <DisclosurePanel transition className="origin-top overflow-hidden px-6 pb-5 text-[15px] leading-relaxed text-white/65 duration-200 ease-out data-[closed]:-translate-y-1 data-[closed]:opacity-0">
            {a}
          </DisclosurePanel>
        </Disclosure>
      ))}
    </div>
  );
}
