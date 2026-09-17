import type { ResearchResponse } from "./types";

export type VerdictTone = "positive" | "mixed" | "insufficient" | "unknown";

export interface Verdict {
  tone: VerdictTone;
  label: string;
  ratio: number;
}

/** Derived client-side from structured claim data, not by pattern-matching
 * the prose — so it holds up whether the backend used the template-based
 * synthesizer or the LLM-backed one (their wording differs). */
export function computeVerdict(response: ResearchResponse): Verdict {
  const totalTopics = response.topics.length;
  if (totalTopics === 0) {
    return { tone: "unknown", label: "No topics planned", ratio: 0 };
  }

  const supportedTopics = new Set(
    response.claims.filter((c) => c.status === "supported").map((c) => c.claim_type),
  );
  const ratio = supportedTopics.size / totalTopics;

  if (ratio === 0) {
    return { tone: "insufficient", label: "Insufficient evidence", ratio };
  }
  if (ratio >= 0.7) {
    return { tone: "positive", label: "Generally supportive evidence", ratio };
  }
  return { tone: "mixed", label: "Mixed / partial evidence", ratio };
}
