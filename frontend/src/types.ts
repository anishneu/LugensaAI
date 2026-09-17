export interface Location {
  name: string;
  city: string | null;
  region: string | null;
  country: string | null;
  slug: string;
  latitude: number | null;
  longitude: number | null;
  raw_query: string;
}

export type SourceType =
  | "news"
  | "local_government"
  | "business_directory"
  | "review_aggregator"
  | "community_forum"
  | "academic"
  | "blog"
  | "other";

export interface Evidence {
  evidence_id: string;
  source_url: string;
  source_title: string;
  publisher: string | null;
  source_type: SourceType;
  retrieved_at: string;
  published_at: string | null;
  location_scope: string;
  text: string;
  topic: string;
  metadata: Record<string, string>;
  relevance_score: number | null;
  quality_score: number | null;
  recency_days: number | null;
  image_url: string | null;
}

export type ClaimStatus = "supported" | "contradicted" | "insufficient_evidence";

export interface Claim {
  claim_id: string;
  text: string;
  claim_type: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  status: ClaimStatus;
  limitations: string[];
}

export type Priority = "high" | "medium" | "low";

export interface ResearchTopic {
  topic_id: string;
  reason: string;
  search_queries: string[];
  preferred_source_types: string[];
  expected_evidence: string;
  priority: Priority;
  completion_criteria: string;
}

export interface ResearchTraceStep {
  stage: string;
  description: string;
  timestamp: string;
  details: Record<string, string>;
}

export interface ResearchResponse {
  location: Location;
  question: string;
  summary: string;
  recommendation: string;
  topics: ResearchTopic[];
  claims: Claim[];
  evidence: Evidence[];
  limitations: string[];
  research_trace: ResearchTraceStep[];
}

export interface ResearchRequest {
  location: string;
  question: string;
  // Set together when the caller already committed to one exact place (a
  // specific POI picked from live search) — skips server-side text
  // resolution, which could otherwise land on a different same-named place.
  latitude?: number | null;
  longitude?: number | null;
  city?: string | null;
  region?: string | null;
  country?: string | null;
}

export interface LocationSuggestion {
  name: string;
  city: string | null;
  region: string | null;
  country: string | null;
  raw_query: string;
  aliases: string[];
  latitude: number | null;
  longitude: number | null;
}

/** A real point-of-interest candidate from a live search (e.g. one specific
 * Starbucks among several) — see GET /api/places/search. */
export interface PlaceCandidate {
  name: string;
  display_name: string;
  category: string;
  city: string | null;
  region: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}

/** The location currently being researched in the workspace. May start out
 * unresolved (free-text search, no coordinates yet) and get refined once a
 * real ResearchResponse comes back with a fully resolved Location. */
export interface ActiveLocation {
  rawQuery: string;
  displayName: string;
  city: string | null;
  region: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
}

/** One asked-and-answered question, kept in the session's chat history. */
export interface QuerySession {
  id: string;
  question: string;
  askedAt: string;
  status: "loading" | "done" | "error";
  response: ResearchResponse | null;
  error: string | null;
}
