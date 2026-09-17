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
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.round(months / 12)}y ago`;
}
