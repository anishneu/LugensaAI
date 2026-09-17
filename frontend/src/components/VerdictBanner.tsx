import type { ResearchResponse } from "../types";
import { computeVerdict } from "../verdict";

interface VerdictBannerProps {
  response: ResearchResponse;
}

export function VerdictBanner({ response }: VerdictBannerProps) {
  const verdict = computeVerdict(response);
  const coveredTopics = new Set(response.claims.filter((c) => c.status === "supported").map((c) => c.claim_type))
    .size;

  return (
    <div className={`verdict-banner tone-${verdict.tone}`}>
      <div className="verdict-badge">{verdict.label}</div>
      <p className="verdict-recommendation">{response.recommendation}</p>
      <div className="verdict-stats">
        <span>
          {coveredTopics}/{response.topics.length} topics well-supported
        </span>
        <span>{response.evidence.length} sources</span>
        <span>{response.claims.length} claims checked</span>
      </div>
    </div>
  );
}
