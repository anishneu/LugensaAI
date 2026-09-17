import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./LandingPage.css";

interface DemoExample {
  location: string;
  question: string;
  stages: string[];
  answer: string;
  sources: string[];
}

// Illustrative only — a scripted walkthrough of the real pipeline stages, not
// a live query. Every question/location here is also usable as a real
// example chip below, so nothing shown here is a claim this app can't back.
const DEMO_EXAMPLES: DemoExample[] = [
  {
    location: "Starbucks, Cambridge, MA",
    question: "Is it safe nearby, and is there a bar close by?",
    stages: ["Resolving location", "Planning: safety, nightlife", "Retrieving evidence", "Verifying claims", "Synthesizing answer"],
    answer:
      "Recent sources checked show Cambridge's overall crime rate near the state average, with no reported incidents near this address in the past week. Several bars are within a short walk.",
    sources: ["cambridgepolice.gov", "yelp.com", "tripadvisor.com"],
  },
  {
    location: "Harvard Square, Cambridge, MA",
    question: "Would this be a good place for a college student?",
    stages: ["Resolving location", "Planning: housing, nightlife, transit", "Retrieving evidence", "Verifying claims", "Synthesizing answer"],
    answer:
      "Reviewers consistently highlight walkability and a dense nightlife scene. Rent nearby runs above the city median, per two independent listings sites.",
    sources: ["apartments.com", "reddit.com/r/cambridgema", "mbta.com"],
  },
  {
    location: "A cafe near Savin Hill, Boston, MA",
    question: "How is the cafe, and how close is it to the subway?",
    stages: ["Resolving location", "Planning: reviews, transit", "Retrieving evidence", "Verifying claims", "Synthesizing answer"],
    answer:
      "Customer reviews describe the coffee and service positively; the nearest Red Line station is roughly a 3-minute walk, per transit mapping data.",
    sources: ["tripadvisor.com", "mbta.com"],
  },
];

const TYPE_SPEED_MS = 28;
const STAGE_STEP_MS = 550;
const ANSWER_HOLD_MS = 4200;

function usePipelineDemo() {
  const [exampleIndex, setExampleIndex] = useState(0);
  const [typedQuestion, setTypedQuestion] = useState("");
  const [activeStage, setActiveStage] = useState(-1);
  const [showAnswer, setShowAnswer] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    const example = DEMO_EXAMPLES[exampleIndex];
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    setTypedQuestion("");
    setActiveStage(-1);
    setShowAnswer(false);

    let charIndex = 0;
    const typeNext = () => {
      charIndex += 1;
      setTypedQuestion(example.question.slice(0, charIndex));
      if (charIndex < example.question.length) {
        timers.current.push(window.setTimeout(typeNext, TYPE_SPEED_MS));
      } else {
        example.stages.forEach((_, i) => {
          timers.current.push(
            window.setTimeout(() => setActiveStage(i), 400 + i * STAGE_STEP_MS),
          );
        });
        const afterStages = 400 + example.stages.length * STAGE_STEP_MS + 400;
        timers.current.push(window.setTimeout(() => setShowAnswer(true), afterStages));
        timers.current.push(
          window.setTimeout(
            () => setExampleIndex((i) => (i + 1) % DEMO_EXAMPLES.length),
            afterStages + ANSWER_HOLD_MS,
          ),
        );
      }
    };
    timers.current.push(window.setTimeout(typeNext, 300));

    return () => timers.current.forEach(window.clearTimeout);
  }, [exampleIndex]);

  return { example: DEMO_EXAMPLES[exampleIndex], typedQuestion, activeStage, showAnswer };
}

function useRevealOnScroll() {
  useEffect(() => {
    const targets = document.querySelectorAll(".reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15 },
    );
    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}

export function LandingPage() {
  const navigate = useNavigate();
  const { example, typedQuestion, activeStage, showAnswer } = usePipelineDemo();
  useRevealOnScroll();

  function tryExample(loc: string) {
    navigate("/app", { state: { seedQuery: loc } });
  }

  return (
    <div className="landing">
      <div className="landing-glow" aria-hidden="true" />
      <div className="landing-hero">
      <div className="landing-content">
        <span className="landing-eyebrow">Agentic AI · Retrieval-Augmented Reasoning</span>
        <h1>
          Lugensa<span className="landing-accent">AI</span>
        </h1>
        <p className="landing-subtitle">An Agentic Location Web Intelligence System</p>
        <p className="landing-description">
          Ask a real question about a real place — <em>"Would this be a good place for a college
          student?"</em> — and watch an autonomous research agent decide what to investigate,
          gather evidence from multiple sources, verify its own claims, and answer with citations
          instead of a guess.
        </p>

        <button type="button" className="get-started-button" onClick={() => navigate("/app")}>
          Get Started
          <span aria-hidden="true">→</span>
        </button>

        <div className="landing-example-chips">
          <span className="example-chips-label">Try it on:</span>
          {DEMO_EXAMPLES.map((ex) => (
            <button key={ex.location} type="button" className="example-chip" onClick={() => tryExample(ex.location)}>
              {ex.location}
            </button>
          ))}
        </div>

        <div className="landing-features">
          <div className="feature-card">
            <span className="feature-icon">🧭</span>
            <h3>Adaptive planning</h3>
            <p>Decomposes your question into the research topics that actually matter for it.</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">📎</span>
            <h3>Cited evidence</h3>
            <p>Every claim links back to a real source — nothing asserted without a passage behind it.</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">⚖️</span>
            <h3>Honest verification</h3>
            <p>Flags contradictions, stale sources, and gaps instead of hiding them.</p>
          </div>
        </div>

        <div className="scroll-cue" aria-hidden="true">
          <span>See it in action</span>
          <span className="scroll-cue-arrow">↓</span>
        </div>
      </div>
      </div>

      <section className="landing-section reveal">
        <div className="section-inner">
          <span className="section-eyebrow">See it in action</span>
          <h2>Watch the agent think</h2>
          <p className="section-lede">
            An illustrative walkthrough of the real pipeline stages — not a live query, but the
            same sequence and honesty standard every real question goes through.
          </p>

          <div className="demo-panel">
            <div className="demo-panel-top">
              <span className="demo-location-pin">📍 {example.location}</span>
            </div>
            <p className="demo-question">
              “{typedQuestion}
              <span className="demo-cursor" aria-hidden="true">▍</span>
              ”
            </p>

            <div className="demo-stages">
              {example.stages.map((stage, i) => (
                <div
                  key={stage}
                  className={`demo-stage ${i <= activeStage ? "active" : ""} ${i === activeStage ? "current" : ""}`}
                >
                  <span className="demo-stage-dot" />
                  {stage}
                </div>
              ))}
            </div>

            <div className={`demo-answer ${showAnswer ? "visible" : ""}`}>
              <p>{example.answer}</p>
              <div className="demo-sources">
                {example.sources.map((s) => (
                  <span key={s} className="demo-source-chip">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section reveal">
        <div className="section-inner">
          <span className="section-eyebrow">How it works</span>
          <h2>Five stages, every time</h2>
          <div className="how-it-works-grid">
            <div className="how-step">
              <span className="how-step-number">1</span>
              <h3>Resolve</h3>
              <p>Any real place — a neighborhood, a specific business, an address — not just a fixed list.</p>
            </div>
            <div className="how-step">
              <span className="how-step-number">2</span>
              <h3>Plan</h3>
              <p>Your question decides which topics matter — a narrow question skips irrelevant research.</p>
            </div>
            <div className="how-step">
              <span className="how-step-number">3</span>
              <h3>Retrieve</h3>
              <p>Real web search and community sources, scored and filtered for relevance.</p>
            </div>
            <div className="how-step">
              <span className="how-step-number">4</span>
              <h3>Verify</h3>
              <p>A fixed, non-LLM checker decides what's actually supported — never the component that proposed it.</p>
            </div>
            <div className="how-step">
              <span className="how-step-number">5</span>
              <h3>Answer</h3>
              <p>A cited, hedged answer — with what couldn't be confirmed stated plainly, not hidden.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section reveal">
        <div className="section-inner">
          <div className="principles-row">
            <div className="principle-badge">
              <strong>No fabricated facts</strong>
              <span>Every stated fact traces to a real, cited passage.</span>
            </div>
            <div className="principle-badge">
              <strong>Verification isn't optional</strong>
              <span>Claim status is decided deterministically — never assumed.</span>
            </div>
            <div className="principle-badge">
              <strong>Limitations, always shown</strong>
              <span>Gaps and fallbacks are reported, not smoothed over.</span>
            </div>
          </div>
          <button type="button" className="get-started-button secondary" onClick={() => navigate("/app")}>
            Start researching a place
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </section>
    </div>
  );
}
