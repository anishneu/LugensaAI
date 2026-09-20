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
} from "@heroicons/react/24/outline";
import { AnswerPreview } from "../components/landing/AnswerPreview";
import { Faq } from "../components/landing/Faq";
import { UseCases } from "../components/landing/UseCases";
import landingMap from "../assets/landing-map.webp";

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

  // A question picked below goes with the visitor into the app, where it waits in the question box until a place is chosen.
  function open(question?: string) {
    navigate("/app", { state: { question: question ?? null } });
  }

  return (
    <div className="min-h-screen scroll-smooth bg-[#07060f] text-white antialiased">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#07060f]">
        <div className="flex h-16 w-full items-center justify-between gap-6 px-5 sm:px-8">
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
        {/* Hero: a street map behind the words, a still image rendered once from OpenStreetMap data (a live map here could
            come up blank on a refresh, and it is decoration). Searching happens in the app itself. */}
        <section className="relative overflow-hidden">
          <img
            src={landingMap}
            alt=""
            width={1440}
            height={810}
            fetchPriority="high"
            decoding="async"
            className="pointer-events-none absolute inset-0 h-full w-full object-cover"
            aria-hidden="true"
          />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#07060f]/70 via-[#07060f]/62 to-[#07060f]" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_45%_at_50%_0%,rgba(124,58,237,0.32),transparent)]" />

          <div className="relative mx-auto flex max-w-4xl flex-col items-center gap-7 px-6 pt-20 pb-28 text-center md:pt-28">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.08] px-4 py-1.5 text-xs font-medium text-white/75">
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
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/[0.06] px-6 py-3 text-[15px] font-semibold text-white no-underline transition hover:bg-white/10"
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

        <section id="use-cases" className="scroll-mt-20 px-6 py-24 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
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
            <UseCases onTry={open} />
          </div>
        </section>

        {/* Numbers that are true of the design, not of a customer base. */}
        <section className="border-y border-white/10 bg-gradient-to-b from-violet-500/[0.08] to-transparent px-6 py-20 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
          <div className="mx-auto grid max-w-5xl gap-10 md:grid-cols-3">
            {STATS.map((stat) => (
              <div key={stat.value} className="flex flex-col gap-3 text-center md:text-left">
                <span className={`text-6xl font-semibold tracking-tight ${ACCENT_TEXT}`}>{stat.value}</span>
                <span className="text-[15px] leading-relaxed text-white/60">{stat.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section id="how-it-works" className="scroll-mt-20 px-6 py-28 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
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

        <section id="principles" className="scroll-mt-20 border-t border-white/10 px-6 py-28 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
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

        <section id="faq" className="scroll-mt-20 border-t border-white/10 px-6 py-28 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
          <div className="mx-auto mb-12 flex max-w-2xl flex-col items-center gap-4 text-center">
            <p className={EYEBROW}>FAQ</p>
            <h2 className={SECTION_TITLE}>Straight answers</h2>
          </div>
          <Faq />
        </section>

        <section className="px-6 pb-28 [content-visibility:auto] [contain-intrinsic-size:auto_720px]">
          <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl border border-white/12 bg-gradient-to-br from-violet-600/30 via-indigo-600/20 to-transparent px-8 py-16 text-center">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_100%_100%,rgba(217,70,239,0.2),transparent_45%)]" />
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
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 text-center text-xs text-white/40 sm:flex-row sm:text-left">
          <span className="text-sm font-bold text-white/70">
            Lugensa<span className="text-violet-300">AI</span>
          </span>
          <div className="flex flex-col gap-1 sm:items-end">
            <span>© {new Date().getFullYear()} Anish Kuila. All rights reserved.</span>
            <span>Maps and place data come from open and licensed sources, including OpenStreetMap contributors.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
