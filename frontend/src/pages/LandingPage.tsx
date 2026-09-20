import { lazy, Suspense, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRightIcon,
  ChatBubbleLeftRightIcon,
  ClipboardDocumentCheckIcon,
  ClockIcon,
  DocumentMagnifyingGlassIcon,
  ExclamationTriangleIcon,
  GlobeAltIcon,
  LanguageIcon,
  MagnifyingGlassCircleIcon,
  MapPinIcon,
  ShieldCheckIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { AnswerPreview } from "../components/landing/AnswerPreview";
import { Faq } from "../components/landing/Faq";
import { UseCases } from "../components/landing/UseCases";
import { LocationSearchInput } from "../components/LocationSearchInput";
import type { ActiveLocation } from "../types";

// The map library is large and the backdrop is decoration: load it after the page is usable, in its own chunk.
const MapBackdrop = lazy(() => import("../components/MapBackdrop"));

const EXAMPLE_PLACES = ["Shibuya, Tokyo", "Le Marais, Paris", "Zamalek, Cairo"];

// Named as text, not as logos: these are where the evidence comes from, not endorsements.
const SOURCES = ["Google Maps", "OpenStreetMap", "Wikipedia", "Wikivoyage", "Reddit", "TripAdvisor", "Local forums", "News"];

const STEPS = [
  { Icon: MapPinIcon, title: "Resolve the place", body: "A neighborhood, a business or an address, anywhere. Names come back in English." },
  { Icon: ClipboardDocumentCheckIcon, title: "Plan the research", body: "Your question decides which topics matter. A narrow question skips research it doesn't need." },
  {
    Icon: DocumentMagnifyingGlassIcon,
    title: "Gather evidence",
    body: "Web search plus forums and reviews, filtered to the exact place. Foreign pages are translated and labeled.",
  },
  { Icon: ShieldCheckIcon, title: "Verify the claims", body: "A fixed, non-AI checker decides what the evidence supports. The part that proposes never approves." },
  { Icon: ChatBubbleLeftRightIcon, title: "Answer with sources", body: "A hedged, cited answer. What couldn't be confirmed is stated plainly." },
];

const STATS = [
  { value: "~60", label: "countries searched in the local language, then translated to English" },
  { value: "5", label: "steps on every question, so an answer is never a model's best guess" },
  { value: "$0", label: "per question: a local model and a free search tier, no billed model API" },
];

const PRINCIPLES = [
  { Icon: MagnifyingGlassCircleIcon, title: "Every fact has a source", body: "A statement either traces to a passage you can open, or it isn't stated." },
  { Icon: LanguageIcon, title: "Translation is labeled", body: "Machine-translated text is marked as such, and the original is one click away." },
  { Icon: ClockIcon, title: "Dates are the source's own", body: "A post shows when it was actually published. If the date can't be read, it says so instead of “just now.”" },
  { Icon: ExclamationTriangleIcon, title: "Gaps are reported", body: "Missing coverage, weak sources and disagreements between sources are shown, not hidden." },
];

const ACCENT_TEXT = "bg-gradient-to-r from-violet-300 via-fuchsia-300 to-indigo-300 bg-clip-text text-transparent";
const SECTION_TITLE = "m-0 text-[clamp(30px,4.4vw,48px)] leading-[1.08] font-semibold tracking-tight text-white";
const EYEBROW = "m-0 text-xs font-semibold tracking-[0.16em] text-violet-300 uppercase";

export function LandingPage() {
  const navigate = useNavigate();
  const searchBox = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  // A question picked below waits for a place: the workspace opens with it in the question box, never run for you.
  const [question, setQuestion] = useState<string | null>(null);

  function open(state: object = {}) {
    navigate("/app", { state: { ...state, question } });
  }

  function chooseQuestion(text: string) {
    setQuestion(text);
    searchBox.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    searchBox.current?.querySelector("input")?.focus({ preventScroll: true });
  }

  const search = (
    <LocationSearchInput
      value={query}
      onChange={setQuery}
      onSelect={(location: ActiveLocation) => open({ location })}
      onSubmit={(text) => open({ submitQuery: text })}
      placeholder="Search a neighborhood, a business or an address…"
    />
  );

  return (
    <div className="min-h-screen scroll-smooth bg-[#07060f] text-white antialiased">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07060f]/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6">
          <a href="#top" className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-white no-underline">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-violet-400 to-indigo-500">
              <MapPinIcon className="h-4 w-4 text-white" aria-hidden="true" />
            </span>
            <span>
              Lugensa<span className="text-violet-300">AI</span>
            </span>
          </a>
          <nav className="hidden items-center gap-7 text-sm font-medium text-white/65 md:flex" aria-label="Sections">
            {[
              ["How it works", "#how-it-works"],
              ["What you can ask", "#use-cases"],
              ["Principles", "#principles"],
              ["FAQ", "#faq"],
            ].map(([label, href]) => (
              <a key={href} href={href} className="text-white/65 no-underline transition hover:text-white">
                {label}
              </a>
            ))}
          </nav>
          <button
            type="button"
            onClick={() => open()}
            className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-[#0b0a14] transition hover:bg-violet-100 focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:outline-none"
          >
            Open the app
          </button>
        </div>
      </header>

      <main id="top">
        {/* Hero: a real street map behind the words, and the real search box. */}
        <section className="relative overflow-hidden">
          <Suspense fallback={null}>
            <MapBackdrop creditPosition="top-right" />
          </Suspense>
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#07060f]/85 via-[#07060f]/78 to-[#07060f]" />
          <div className="pointer-events-none absolute -top-40 left-1/2 h-[34rem] w-[54rem] -translate-x-1/2 rounded-full bg-violet-600/25 blur-[140px]" />

          <div className="relative mx-auto flex max-w-4xl flex-col items-center gap-7 px-6 pt-20 pb-28 text-center md:pt-28">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-4 py-1.5 text-xs font-medium text-white/75 backdrop-blur">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden="true" />
              Free to run · local model · sources on every claim
            </span>
            <h1 className="m-0 text-[clamp(40px,7vw,76px)] leading-[1.02] font-semibold tracking-tight text-white">
              Ask about any place.
              <br />
              Get an answer you can <span className={ACCENT_TEXT}>check</span>.
            </h1>
            <p className="m-0 max-w-2xl text-lg leading-relaxed text-white/70">
              Lugensa researches a neighborhood, a business or an address across the open web, in dozens of languages, then answers
              your question with a source beside every claim, and tells you what it couldn't confirm.
            </p>

            <div ref={searchBox} className="w-full max-w-xl text-left">
              {search}
              {question && (
                <p className="mt-3 mb-0 flex items-center justify-between gap-3 rounded-xl border border-violet-400/30 bg-violet-400/10 px-4 py-2.5 text-sm text-violet-100">
                  <span>
                    Now pick a place, then ask: <em className="text-white">“{question}”</em>
                  </span>
                  <button type="button" onClick={() => setQuestion(null)} aria-label="Forget this question" className="rounded-full p-1 text-violet-200 hover:bg-white/10">
                    <XMarkIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                </p>
              )}
            </div>

            <p className="m-0 text-sm text-white/45">
              Try:{" "}
              {EXAMPLE_PLACES.map((place, i) => (
                <span key={place}>
                  {i > 0 && " · "}
                  <button
                    type="button"
                    onClick={() => open({ submitQuery: place })}
                    className="cursor-pointer border-none bg-transparent p-0 text-sm text-white/80 underline decoration-white/25 underline-offset-4 transition hover:text-white hover:decoration-white"
                  >
                    {place}
                  </button>
                </span>
              ))}
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => open()}
                className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-[15px] font-semibold text-[#0b0a14] transition hover:bg-violet-100 focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:outline-none"
              >
                Research a place <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
              </button>
              <a
                href="#how-it-works"
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/[0.05] px-6 py-3 text-[15px] font-semibold text-white no-underline backdrop-blur transition hover:bg-white/10"
              >
                See how it works
              </a>
            </div>
          </div>
        </section>

        {/* The shape of an answer, overlapping the hero's foot. */}
        <section className="relative -mt-16 px-6 pb-24">
          <AnswerPreview />
        </section>

        {/* Where evidence comes from. */}
        <section className="border-y border-white/10 bg-white/[0.02] py-10">
          <div className="mx-auto max-w-6xl px-6 text-center">
            <p className="m-0 mb-6 text-xs font-medium tracking-[0.16em] text-white/45 uppercase">Where the evidence comes from</p>
            <ul className="m-0 flex list-none flex-wrap items-center justify-center gap-x-10 gap-y-4 p-0">
              {SOURCES.map((source) => (
                <li key={source} className="text-lg font-semibold tracking-tight text-white/55">
                  {source}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="use-cases" className="scroll-mt-20 px-6 py-24">
          <div className="mx-auto max-w-5xl">
            <div className="mb-12 flex flex-col items-center gap-4 text-center">
              <p className={EYEBROW}>What you can ask</p>
              <h2 className={SECTION_TITLE}>
                Different questions, <span className={ACCENT_TEXT}>different research</span>
              </h2>
              <p className="m-0 max-w-2xl text-[17px] leading-relaxed text-white/60">
                The question decides what gets researched. Asking about the nightlife doesn't cost you a search for hospitals.
              </p>
            </div>
            <UseCases onTry={chooseQuestion} />
          </div>
        </section>

        {/* Numbers that are true of the design, not of a customer base. */}
        <section className="border-y border-white/10 bg-gradient-to-b from-violet-500/[0.08] to-transparent px-6 py-20">
          <div className="mx-auto grid max-w-5xl gap-10 md:grid-cols-3">
            {STATS.map((stat) => (
              <div key={stat.value} className="flex flex-col gap-3 text-center md:text-left">
                <span className={`text-6xl font-semibold tracking-tight ${ACCENT_TEXT}`}>{stat.value}</span>
                <span className="text-[15px] leading-relaxed text-white/60">{stat.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 px-6 py-28">
          <div className="mx-auto max-w-6xl">
            <div className="mb-14 flex flex-col items-center gap-4 text-center">
              <p className={EYEBROW}>How it works</p>
              <h2 className={SECTION_TITLE}>Five steps, every question</h2>
              <p className="m-0 max-w-xl text-[17px] leading-relaxed text-white/60">
                The same sequence runs every time, so an answer is built from evidence rather than guessed.
              </p>
            </div>
            <ol className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-5">
              {STEPS.map(({ Icon, title, body }, i) => (
                <li key={title} className="relative flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 transition hover:border-violet-400/40 hover:bg-white/[0.05]">
                  <div className="flex items-center justify-between">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300">
                      <Icon className="h-6 w-6" aria-hidden="true" />
                    </span>
                    <span className="text-sm font-semibold text-white/30">0{i + 1}</span>
                  </div>
                  <h3 className="m-0 text-[17px] font-semibold text-white">{title}</h3>
                  <p className="m-0 text-sm leading-relaxed text-white/60">{body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="principles" className="scroll-mt-20 border-t border-white/10 px-6 py-28">
          <div className="mx-auto grid max-w-6xl items-start gap-14 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="flex flex-col gap-5">
              <p className={EYEBROW}>What it will and won't do</p>
              <h2 className={SECTION_TITLE}>
                Built to say what it <span className={ACCENT_TEXT}>doesn't know</span>
              </h2>
              <p className="m-0 text-[17px] leading-relaxed text-white/60">
                Most tools answer confidently. This one shows its receipts, marks what it couldn't confirm, and never invents a source,
                a date or a rating to fill a gap.
              </p>
              <div className="mt-2 flex items-start gap-3 rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-5">
                <GlobeAltIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-300" aria-hidden="true" />
                <p className="m-0 text-sm leading-relaxed text-amber-100/80">
                  Honest limits: pages behind a login can't be read, a small place may have little written about it, and an answer takes
                  minutes on a laptop.
                </p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {PRINCIPLES.map(({ Icon, title, body }) => (
                <div key={title} className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-6">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.07] text-violet-300">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <h3 className="m-0 text-base font-semibold text-white">{title}</h3>
                  <p className="m-0 text-sm leading-relaxed text-white/60">{body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="faq" className="scroll-mt-20 border-t border-white/10 px-6 py-28">
          <div className="mx-auto mb-12 flex max-w-2xl flex-col items-center gap-4 text-center">
            <p className={EYEBROW}>FAQ</p>
            <h2 className={SECTION_TITLE}>Straight answers</h2>
          </div>
          <Faq />
        </section>

        <section className="px-6 pb-28">
          <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl border border-white/12 bg-gradient-to-br from-violet-600/30 via-indigo-600/20 to-transparent px-8 py-16 text-center">
            <div className="pointer-events-none absolute -right-24 -bottom-24 h-72 w-72 rounded-full bg-fuchsia-500/20 blur-[100px]" />
            <h2 className={`${SECTION_TITLE} relative mx-auto max-w-2xl`}>Pick a place and ask what you'd actually want to know.</h2>
            <div className="relative mt-8 flex justify-center">
              <button
                type="button"
                onClick={() => open()}
                className="inline-flex items-center gap-2 rounded-full bg-white px-7 py-3.5 text-[15px] font-semibold text-[#0b0a14] transition hover:bg-violet-100 focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:outline-none"
              >
                Research a place <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 text-xs text-white/40 sm:flex-row">
          <span className="text-sm font-bold text-white/70">
            Lugensa<span className="text-violet-300">AI</span>
          </span>
          <span>Map data © OpenStreetMap contributors · Map tiles by OpenFreeMap · Google Maps data shown with attribution</span>
        </div>
      </footer>
    </div>
  );
}
