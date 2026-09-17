/** Defense-in-depth cleanup for evidence text. The backend already strips
 * most markdown/nav noise from live search results (see
 * app/tools/tavily_tools.py::_clean_text), but this keeps the UI safe
 * against anything that slips through or against future tool sources that
 * don't clean as aggressively. */
export function cleanDisplayText(text: string): string {
  return text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // markdown images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // markdown links -> link text
    .replace(/^#{1,6}\s*/gm, "") // heading hashes
    .replace(/^(?:[^\n|]*\|){3,}[^\n]*$/gm, "") // nav-menu-style lines
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
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
 * presenting the pipeline's fetch time as if it were a real publish date. */
export function formatFeedTimestamp(publishedAt: string | null, retrievedAt: string): string {
  if (publishedAt) return relativeTimeFrom(publishedAt);
  return `retrieved ${relativeTimeFrom(retrievedAt)}`;
}
