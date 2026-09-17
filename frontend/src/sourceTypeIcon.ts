import type { SourceType } from "./types";

/** A visual placeholder for cards that don't have a real sourced image —
 * distinguishes card types by sight instead of everything looking like the
 * same bare text block. Never shown in place of a real image, only instead
 * of a blank space when none is available. */
export const SOURCE_TYPE_ICON: Record<SourceType, string> = {
  news: "📰",
  local_government: "🏛️",
  business_directory: "🏢",
  review_aggregator: "⭐",
  community_forum: "💬",
  academic: "🎓",
  blog: "📝",
  other: "🌐",
};
