import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useNavigate } from "react-router-dom";

const EXAMPLE_PLACES = ["Shibuya, Tokyo", "Le Marais, Paris", "Zamalek, Cairo"];

const STEPS = [
  {
    title: "Resolve the place",
    body: "A neighborhood, a specific business, or a street address, anywhere in the world. Names come back in English.",
  },
  {
    title: "Plan the research",
    body: "Your question decides which topics matter. A narrow question skips research it doesn't need.",
  },
  {
    title: "Gather evidence",
    body: "Real web search plus forum and review commentary, filtered for relevance to the exact place. Foreign-language pages are translated, and labeled as translated.",
  },
  {
    title: "Verify the claims",
    body: "A fixed, non-AI checker decides what the evidence actually supports. The part that proposes a claim never gets to approve it.",
  },
  {
    title: "Answer with sources",
    body: "A hedged, cited answer. What couldn't be confirmed is stated plainly, not smoothed over.",
  },
];

const PRINCIPLES = [
  { title: "Every fact has a source", body: "A statement either traces to a passage you can open, or it isn't stated." },
  { title: "Dates are the source's own", body: "A post shows when it was actually published. If the date is unknown, it says so instead of saying “just now.”" },
  { title: "Translation is labeled", body: "Machine-translated text is marked as such, and the original is one click away." },
  { title: "Gaps are reported", body: "Missing coverage, weak sources and disagreements between sources are shown, not hidden." },
];

function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.25 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

const BUTTON =
  "inline-flex items-center gap-2 rounded-md bg-[var(--l-ink)] px-5 py-3 text-[15px] font-semibold text-[var(--l-bg)] transition-opacity hover:opacity-85";

/** What a response contains. Deliberately states nothing about any real place: an earlier version
 * showed an invented sample answer with real-looking sources, which is exactly what this
 * project exists not to do. */
function WhatYouGet() {
  const parts: [string, string][] = [
    ["A direct answer", "Written from the sources found, in plain language."],
    ["Claims, each checked", "Marked supported, contradicted, or insufficient evidence, with the sources behind each."],
    ["The sources themselves", "With real publication dates when the page has one, and translated pages labeled as translated."],
    ["What it could not confirm", "Coverage gaps and weak spots are listed, not smoothed over."],
  ];
  return (
    <figure className="m-0 rounded-lg border border-[var(--l-rule)] bg-[var(--l-card)] p-6 shadow-[0_1px_0_var(--l-rule)]">
      <figcaption className="mb-4 text-[11px] uppercase tracking-[0.12em] text-[var(--l-muted)]">What you get back</figcaption>
      <ol className="m-0 flex list-none flex-col gap-4 p-0">
        {parts.map(([title, body], i) => (
          <li key={title} className="flex gap-3.5">
            <span className="w-4 font-serif text-lg leading-tight text-[var(--l-accent)]">{i + 1}</span>
            <div>
              <p className="m-0 text-[15px] font-semibold text-[var(--l-ink)]">{title}</p>
              <p className="m-0 mt-0.5 text-[13.5px] leading-relaxed text-[var(--l-muted)]">{body}</p>
            </div>
          </li>
        ))}
      </ol>
    </figure>
  );
}

export function LandingPage() {
  const navigate = useNavigate();

  function tryExample(place: string) {
    navigate("/app", { state: { seedQuery: place } });
  }

  return (
    <div className="landing min-h-screen bg-[var(--l-bg)] text-[var(--l-ink)]">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="font-serif text-xl font-semibold tracking-tight text-[var(--l-ink)]">Lugensa</span>
        <button
          type="button"
          onClick={() => navigate("/app")}
          className="text-sm font-medium text-[var(--l-ink)] underline decoration-[var(--l-rule)] underline-offset-4 hover:decoration-[var(--l-ink)]"
        >
          Open the app
        </button>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 pt-10 pb-24 md:grid-cols-[1.1fr_0.9fr] md:pt-20">
          <div>
            <p className="m-0 mb-5 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--l-accent)]">
              Location research with receipts
            </p>
            <h1 className="m-0 font-serif text-[clamp(38px,6vw,64px)] font-medium leading-[1.05] tracking-tight text-[var(--l-ink)]">
              Ask about any place. Get an answer you can check.
            </h1>
            <p className="mt-6 mb-0 max-w-[34rem] text-[17px] leading-relaxed text-[var(--l-muted)]">
              Lugensa researches a neighborhood, a business, or an address across the open web, in dozens of
              languages, then answers your question with a source next to every claim, and tells you what it couldn't confirm.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
              <button type="button" className={BUTTON} onClick={() => navigate("/app")}>
                Research a place <span aria-hidden="true">→</span>
              </button>
              <a
                href="#how-it-works"
                className="text-[15px] font-medium text-[var(--l-ink)] underline decoration-[var(--l-rule)] underline-offset-4 hover:decoration-[var(--l-ink)]"
              >
                How it works
              </a>
            </div>

            <p className="mt-8 mb-0 text-[13px] text-[var(--l-muted)]">
              Try:{" "}
              {EXAMPLE_PLACES.map((place, i) => (
                <span key={place}>
                  {i > 0 && " · "}
                  <button
                    type="button"
                    onClick={() => tryExample(place)}
                    className="cursor-pointer border-none bg-transparent p-0 text-[13px] text-[var(--l-ink)] underline decoration-[var(--l-rule)] underline-offset-4 hover:decoration-[var(--l-ink)]"
                  >
                    {place}
                  </button>
                </span>
              ))}
            </p>
          </div>

          <WhatYouGet />
        </section>

        <section id="how-it-works" className="border-t border-[var(--l-rule)]">
          <div className="mx-auto grid max-w-6xl gap-10 px-6 py-24 md:grid-cols-[0.8fr_1.2fr]">
            <Reveal>
              <h2 className="m-0 font-serif text-[clamp(28px,4vw,40px)] font-medium leading-tight tracking-tight text-[var(--l-ink)]">
                Five steps, every question
              </h2>
              <p className="mt-4 mb-0 max-w-sm text-[15px] leading-relaxed text-[var(--l-muted)]">
                The same sequence runs every time, so an answer is never just a model's best guess.
              </p>
            </Reveal>

            <ol className="m-0 flex list-none flex-col p-0">
              {STEPS.map((step, i) => (
                <li key={step.title}>
                  <Reveal className="grid grid-cols-[2.25rem_1fr] gap-4 border-t border-[var(--l-rule)] py-6 first:border-t-0 first:pt-0">
                    <span className="font-serif text-lg text-[var(--l-accent)]">{i + 1}</span>
                    <div>
                      <h3 className="m-0 mb-1 text-base font-semibold text-[var(--l-ink)]">{step.title}</h3>
                      <p className="m-0 text-[15px] leading-relaxed text-[var(--l-muted)]">{step.body}</p>
                    </div>
                  </Reveal>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="border-t border-[var(--l-rule)]">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <h2 className="m-0 mb-12 max-w-xl font-serif text-[clamp(28px,4vw,40px)] font-medium leading-tight tracking-tight text-[var(--l-ink)]">
                What it will and won't do
              </h2>
            </Reveal>
            <div className="grid gap-x-10 gap-y-10 sm:grid-cols-2">
              {PRINCIPLES.map((p) => (
                <Reveal key={p.title} className="border-t border-[var(--l-ink)] pt-4">
                  <h3 className="m-0 mb-2 text-base font-semibold text-[var(--l-ink)]">{p.title}</h3>
                  <p className="m-0 text-[15px] leading-relaxed text-[var(--l-muted)]">{p.body}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--l-rule)]">
          <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-6 py-24 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="m-0 max-w-md font-serif text-[clamp(26px,3.6vw,36px)] font-medium leading-tight tracking-tight text-[var(--l-ink)]">
              Pick a place and ask what you'd actually want to know.
            </h2>
            <button type="button" className={BUTTON} onClick={() => navigate("/app")}>
              Research a place <span aria-hidden="true">→</span>
            </button>
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--l-rule)] px-6 py-6 text-center text-xs text-[var(--l-muted)]">
        Map data © OpenStreetMap contributors
      </footer>
    </div>
  );
}
