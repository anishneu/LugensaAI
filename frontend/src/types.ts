export interface Location {
  name: string;
  city: string | null;
  region: string | null;
  country: string | null;
  slug: string;
  latitude: number | null;
  longitude: number | null;
  raw_query: string;
  is_business: boolean;
}

export type SourceType =
  | "news"
  | "local_government"
  | "business_directory"
  | "review_aggregator"
  | "community_forum"
  | "academic"
  | "blog"
  | "reference"
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
  key_findings: string[];
  details: string;
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
  is_business?: boolean;
  is_address?: boolean;
}

/** What the backend has switched on, and roughly how long a run takes as a
 * result — see GET /api/capabilities. */
export interface Capabilities {
  llm_provider: "ollama" | "none";
  llm_model: string | null;
  live_search: boolean;
  /** Whether the live feed has a source: free news and Reddit, or a Tavily key. Older servers do not send it. */
  live_feed?: boolean;
  live_geocoding: boolean;
  estimated_seconds_min: number;
  estimated_seconds_max: number;
  /** True when the local embedding model hasn't been loaded yet this process,
   * so the next run pays a one-time warm-up the following ones won't. */
  first_run_warmup: boolean;
  /** Whether Google Maps ratings and reviews are connected on the server. */
  place_profile: boolean;
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
  is_business: boolean;
  is_address: boolean;
  /** Google's id for the place, when the candidate came from Google Maps. */
  google_place_id?: string | null;
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
  isBusiness: boolean;
  /** A street address or building rather than a named place; the backend looks for a business at it. */
  isAddress: boolean;
  /** Google's id for the pin, when it was picked from a Google result: the link to Google Maps then opens the exact listing.
   * Cleared whenever the pin moves to another place. */
  googlePlaceId?: string | null;
}

/** One asked-and-answered question, kept in the session's chat history. */
export interface QuerySession {
  id: string;
  question: string;
  askedAt: string;
  status: "loading" | "done" | "error";
  /** What the agent has done so far, while the run is going. Dropped once the answer arrives: the response carries the full trace. */
  steps?: ResearchTraceStep[];
  response: ResearchResponse | null;
  error: string | null;
}

export interface NearbyItem {
  name: string;
  kind: string;
  distance_m: number;
  /** What OpenStreetMap knows beyond the name. Absent means "not in the map", never "doesn't have one". */
  latitude?: number | null;
  longitude?: number | null;
  opening_hours?: string | null;
  website?: string | null;
  phone?: string | null;
  cuisine?: string | null;
  address?: string | null;
  wheelchair?: string | null;
}

export interface NearbyGroup {
  label: string;
  total: number;
  nearest: NearbyItem[];
}

export interface NearbyPlaces {
  latitude: number;
  longitude: number;
  radius_m: number;
  groups: NearbyGroup[];
  source: string;
}

export interface PlaceReview {
  author: string | null;
  rating: number | null;
  text: string;
  original_text: string | null;
  original_language: string | null;
  published_at: string | null;
  relative_time: string | null;
}

export interface PlaceProfile {
  place_id: string;
  name: string;
  address: string | null;
  rating: number | null;
  review_count: number | null;
  price_level: string | null;
  summary: string | null;
  review_summary: string | null;
  review_summary_disclosure: string | null;
  review_summary_report_url: string | null;
  open_now: boolean | null;
  opening_hours: string[];
  website: string | null;
  phone: string | null;
  maps_url: string | null;
  reviews: PlaceReview[];
  source: string;
}

/** A well-known place near a pin with Google Maps' own rating (Google's data, shown with attribution). */
export interface PopularPlace {
  name: string;
  category: string;
  rating: number;
  review_count: number | null;
  distance_m: number;
  maps_url: string | null;
  latitude: number;
  longitude: number;
}

/** English for place names and addresses in another script. `translations` lines up with what was sent; null means
 * "already readable, or could not be translated". */
export interface TranslatedTexts {
  available: boolean;
  language: string | null;
  translations: (string | null)[];
}
