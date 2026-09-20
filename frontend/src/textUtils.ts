/** Defense-in-depth cleanup for evidence text. The backend already strips
 * most markdown/nav noise from live search results (see
 * app/tools/tavily_tools.py::_clean_text), but this keeps the UI safe
 * against anything that slips through or against future tool sources that
 * don't clean as aggressively. */
export function cleanDisplayText(text: string): string {
  return text
    .replace(/<\/p>\s*<p[^>]*>|<br\s*\/?>/gi, "\n\n") // paragraph breaks some local models emit as HTML
    .replace(/<\/?[a-zA-Z][^>]*>/g, "") // any other stray HTML tag
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // markdown images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // markdown links -> link text
    .replace(/^#{1,6}\s*/gm, "") // heading hashes
    .replace(/^(?:[^\n|]*\|){3,}[^\n]*$/gm, "") // nav-menu-style lines
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** What to show for a piece of evidence: the backend's readable description (whole sentences, no page chrome)
 * when it made one, else the cleaned text. Live feed items carry their description as their text. */
export function evidenceText(item: { text: string; metadata: Record<string, string> }): string {
  return item.metadata.description || cleanDisplayText(item.text);
}

export function relativeTimeFrom(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  const weeks = Math.round(days / 7);
  if (weeks < 5) return `${weeks} week${weeks === 1 ? "" : "s"} ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
  const years = Math.round(months / 12);
  return `${years} year${years === 1 ? "" : "s"} ago`;
}

/** Never fabricates a timestamp: if the source's own publication date is
 * unknown, this says so explicitly (prefixed "retrieved") rather than
 * presenting the pipeline's fetch time as if it were a real publish date.
 * Live feed items always carry a real publication date (the backend drops
 * undated results), so the fallback only applies to other evidence. */
export function formatFeedTimestamp(publishedAt: string | null, retrievedAt: string): string {
  if (publishedAt) return relativeTimeFrom(publishedAt);
  return `retrieved ${relativeTimeFrom(retrievedAt)}`;
}

/** The source's own publication time, spelled out — e.g. "Sep 17, 6:56 PM".
 * Shown alongside the relative time so "2 hours ago" is auditable against
 * the actual moment the post went up. */
export function absoluteTimeFrom(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
    hour: "numeric",
    minute: "2-digit",
  });
}
