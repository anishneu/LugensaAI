import { useNavigate } from "react-router-dom";
import "./LandingPage.css";

export function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="landing">
      <div className="landing-glow" aria-hidden="true" />
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
      </div>
    </div>
  );
}
