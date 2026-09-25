import { cleanDisplayText } from "./textUtils";
import type { Claim, Evidence, ResearchResponse } from "./types";

/** Markdown for an answer and for a comparison of two answers. Everything in a report comes from the response it was built
 * from: no sentence is written here about a place, and nothing is ranked. Pure functions, so they can be tested without a browser. */

const STATUS_LABEL: Record<Claim["status"], string> = {
  supported: "Supported",
  contradicted: "Contradicted",
  insufficient_evidence: "Insufficient evidence",
};

export function placeTitle(response: ResearchResponse): string {
  const { name, city } = response.location;
  return city && city !== name ? `${name}, ${city}` : name;
}

function oneLine(text: string): string {
  return cleanDisplayText(text).replace(/\s+/g, " ").trim();
}

function linkTitle(title: string): string {
  return oneLine(title).replace(/([[\]])/g, "\\$1") || "Untitled source";
}

function linkUrl(url: string): string {
  return url.replace(/\s/g, "%20").replace(/\)/g, "%29");
}

function day(iso: string | null): string | null {
  return iso ? iso.slice(0, 10) : null;
}

function sourceLink(item: Evidence): string {
  return `[${linkTitle(item.source_title)}](${linkUrl(item.source_url)})`;
}

function sourceLine(item: Evidence): string {
  const parts = [item.publisher, item.source_type.replace(/_/g, " "), day(item.published_at) ?? `retrieved ${day(item.retrieved_at)}`];
  return `${sourceLink(item)} — ${parts.filter(Boolean).join(" · ")}`;
}

function paragraphs(text: string): string {
  return cleanDisplayText(text)
    .split("\n\n")
    .map((p) => p.trim())
    .filter(Boolean)
    .join("\n\n");
}

function longDate(at: Date): string {
  return at.toISOString().slice(0, 10);
}

function claimsSection(response: ResearchResponse): string[] {
  const byId = new Map(response.evidence.map((e) => [e.evidence_id, e]));
  return response.claims.map((claim) => {
    const cited = claim.supporting_evidence_ids.map((id) => byId.get(id)).filter((e): e is Evidence => Boolean(e));
    const sources = cited.length ? ` Sources: ${cited.map(sourceLink).join(", ")}.` : "";
    return `- **${STATUS_LABEL[claim.status]}:** ${oneLine(claim.text)}${sources}`;
  });
}

/** The full answer as Markdown: what was asked, what was found, what each claim rests on, and what could not be confirmed. */
export function buildReportMarkdown(response: ResearchResponse, at: Date = new Date()): string {
  const lines: string[] = [
    `# ${placeTitle(response)}`,
    "",
    `> ${oneLine(response.question)}`,
    "",
    `_Researched by Lugensa AI on ${longDate(at)} from public sources. Every claim below names the evidence it rests on, and the limitations say what could not be confirmed. This is a research summary, not advice._`,
    "",
    "## Summary",
    "",
    paragraphs(response.summary) || "_No summary was produced._",
  ];
  if (response.key_findings.length) {
    lines.push("", "## Key findings", "", ...response.key_findings.map((f) => `- ${oneLine(f)}`));
  }
  if (response.details.trim()) {
    lines.push("", "## Details", "", paragraphs(response.details));
  }
  if (response.claims.length) {
    lines.push("", "## Claims and what they rest on", "", ...claimsSection(response));
  }
  lines.push("", "## Limitations", "");
  lines.push(...(response.limitations.length ? response.limitations.map((l) => `- ${oneLine(l)}`) : ["- None were recorded for this run."]));
  lines.push("", `## Sources (${response.evidence.length})`, "");
  lines.push(...(response.evidence.length ? response.evidence.map((e, i) => `${i + 1}. ${sourceLine(e)}`) : ["_No sources were found._"]));
  return lines.join("\n") + "\n";
}

export interface CompareRow {
  label: string;
  a: string;
  b: string;
}

/** What each run found, side by side. These count what was found, not how good either place is: more sources is not a better place. */
export function compareRows(a: ResearchResponse, b: ResearchResponse): CompareRow[] {
  const count = (r: ResearchResponse, status: Claim["status"]) => r.claims.filter((c) => c.status === status).length;
  const row = (label: string, pick: (r: ResearchResponse) => number): CompareRow => ({ label, a: String(pick(a)), b: String(pick(b)) });
  return [
    row("Sources found", (r) => r.evidence.length),
    row("Kinds of source", (r) => new Set(r.evidence.map((e) => e.source_type)).size),
    row("Topics researched", (r) => r.topics.length),
    row("Topics with evidence", (r) => new Set(r.evidence.map((e) => e.topic)).size),
    row("Supported claims", (r) => count(r, "supported")),
    row("Contradicted claims", (r) => count(r, "contradicted")),
    row("Claims without enough evidence", (r) => count(r, "insufficient_evidence")),
    row("Known limitations", (r) => r.limitations.length),
  ];
}

export function buildComparisonMarkdown(a: ResearchResponse, b: ResearchResponse, at: Date = new Date()): string {
  const nameA = placeTitle(a);
  const nameB = placeTitle(b);
  const lines: string[] = [
    `# ${nameA} and ${nameB}`,
    "",
    `> ${oneLine(a.question)}`,
    "",
    `_Two separate research runs by Lugensa AI on ${longDate(at)}, each from its own public sources. The table counts what each run found; it does not say which place is better, and neither does anything below. This is a research summary, not advice._`,
    "",
    "## What each run found",
    "",
    `| | ${nameA} | ${nameB} |`,
    "|---|---|---|",
    ...compareRows(a, b).map((r) => `| ${r.label} | ${r.a} | ${r.b} |`),
  ];
  for (const response of [a, b]) {
    lines.push("", `## ${placeTitle(response)}`, "", "### Summary", "", paragraphs(response.summary) || "_No summary was produced._");
    if (response.key_findings.length) lines.push("", "### Key findings", "", ...response.key_findings.map((f) => `- ${oneLine(f)}`));
    lines.push("", "### Limitations", "");
    lines.push(...(response.limitations.length ? response.limitations.map((l) => `- ${oneLine(l)}`) : ["- None were recorded for this run."]));
    lines.push("", `### Sources (${response.evidence.length})`, "");
    lines.push(...(response.evidence.length ? response.evidence.map((e, i) => `${i + 1}. ${sourceLine(e)}`) : ["_No sources were found._"]));
  }
  return lines.join("\n") + "\n";
}

function slug(text: string, max: number): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, max)
    .replace(/-+$/g, "");
}

export function reportFileName(response: ResearchResponse, at: Date = new Date()): string {
  return `${slug(placeTitle(response), 40) || "place"}-${slug(response.question, 40) || "report"}-${longDate(at)}.md`;
}

export function comparisonFileName(a: ResearchResponse, b: ResearchResponse, at: Date = new Date()): string {
  return `${slug(placeTitle(a), 30) || "place"}-vs-${slug(placeTitle(b), 30) || "place"}-${longDate(at)}.md`;
}

// ---- The same reports as a printable page (for "Save as PDF"). Every value is escaped: sources are other people's text.

function esc(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const PRINT_STYLE = `
  body{font:14px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;max-width:760px;margin:24px auto;padding:0 20px}
  h1{font-size:24px;margin:0 0 6px} h2{font-size:17px;margin:26px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px} h3{font-size:14.5px;margin:18px 0 6px}
  blockquote{margin:6px 0 12px;padding-left:12px;border-left:3px solid #999;color:#444;font-style:italic}
  .note{color:#555;font-size:12.5px} li{margin:4px 0} a{color:#3b2bb0;word-break:break-word}
  table{border-collapse:collapse;width:100%;font-size:13.5px} th,td{border:1px solid #ccc;padding:5px 9px;text-align:left} th{background:#f3f3f3}
  .status{font-weight:600} .meta{color:#666} section{break-inside:avoid-page}
  @media print{body{margin:0;max-width:none} a{color:#1a1a1a} a[href^="http"]::after{content:" (" attr(href) ")";font-size:11px;color:#555;word-break:break-all}}
`;

function htmlPage(title: string, body: string): string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${PRINT_STYLE}</style></head><body>${body}</body></html>`;
}

function htmlSourceLink(item: Evidence): string {
  return `<a href="${esc(item.source_url)}">${esc(oneLine(item.source_title) || "Untitled source")}</a>`;
}

function htmlSources(response: ResearchResponse): string {
  if (!response.evidence.length) return "<p><em>No sources were found.</em></p>";
  const items = response.evidence.map((e) => {
    const meta = [e.publisher, e.source_type.replace(/_/g, " "), day(e.published_at) ?? `retrieved ${day(e.retrieved_at)}`].filter(Boolean).join(" · ");
    return `<li>${htmlSourceLink(e)} <span class="meta">— ${esc(meta)}</span></li>`;
  });
  return `<ol>${items.join("")}</ol>`;
}

function htmlList(items: string[], emptyText: string): string {
  return items.length ? `<ul>${items.map((i) => `<li>${esc(oneLine(i))}</li>`).join("")}</ul>` : `<p>${esc(emptyText)}</p>`;
}

function htmlParagraphs(text: string, emptyText: string): string {
  const parts = paragraphs(text).split("\n\n").filter(Boolean);
  return parts.length ? parts.map((p) => `<p>${esc(p)}</p>`).join("") : `<p><em>${esc(emptyText)}</em></p>`;
}

export function buildReportHtml(response: ResearchResponse, at: Date = new Date()): string {
  const byId = new Map(response.evidence.map((e) => [e.evidence_id, e]));
  const claims = response.claims.map((claim) => {
    const cited = claim.supporting_evidence_ids.map((id) => byId.get(id)).filter((e): e is Evidence => Boolean(e));
    const sources = cited.length ? ` Sources: ${cited.map(htmlSourceLink).join(", ")}.` : "";
    return `<li><span class="status">${STATUS_LABEL[claim.status]}:</span> ${esc(oneLine(claim.text))}${sources}</li>`;
  });
  const body = [
    `<h1>${esc(placeTitle(response))}</h1>`,
    `<blockquote>${esc(oneLine(response.question))}</blockquote>`,
    `<p class="note">Researched by Lugensa AI on ${longDate(at)} from public sources. Every claim below names the evidence it rests on, and the limitations say what could not be confirmed. This is a research summary, not advice.</p>`,
    `<h2>Summary</h2>${htmlParagraphs(response.summary, "No summary was produced.")}`,
    response.key_findings.length ? `<h2>Key findings</h2>${htmlList(response.key_findings, "")}` : "",
    response.details.trim() ? `<h2>Details</h2>${htmlParagraphs(response.details, "")}` : "",
    claims.length ? `<h2>Claims and what they rest on</h2><ul>${claims.join("")}</ul>` : "",
    `<h2>Limitations</h2>${htmlList(response.limitations, "None were recorded for this run.")}`,
    `<h2>Sources (${response.evidence.length})</h2>${htmlSources(response)}`,
  ].join("");
  return htmlPage(`${placeTitle(response)}: ${oneLine(response.question)}`, body);
}

export function buildComparisonHtml(a: ResearchResponse, b: ResearchResponse, at: Date = new Date()): string {
  const rows = compareRows(a, b).map((r) => `<tr><th scope="row">${esc(r.label)}</th><td>${esc(r.a)}</td><td>${esc(r.b)}</td></tr>`).join("");
  const place = (response: ResearchResponse) =>
    `<section><h2>${esc(placeTitle(response))}</h2><h3>Summary</h3>${htmlParagraphs(response.summary, "No summary was produced.")}` +
    (response.key_findings.length ? `<h3>Key findings</h3>${htmlList(response.key_findings, "")}` : "") +
    `<h3>Limitations</h3>${htmlList(response.limitations, "None were recorded for this run.")}<h3>Sources (${response.evidence.length})</h3>${htmlSources(response)}</section>`;
  const body = [
    `<h1>${esc(placeTitle(a))} and ${esc(placeTitle(b))}</h1>`,
    `<blockquote>${esc(oneLine(a.question))}</blockquote>`,
    `<p class="note">Two separate research runs by Lugensa AI on ${longDate(at)}, each from its own public sources. The table counts what each run found; it does not say which place is better, and neither does anything below. This is a research summary, not advice.</p>`,
    `<h2>What each run found</h2><table><thead><tr><th></th><th>${esc(placeTitle(a))}</th><th>${esc(placeTitle(b))}</th></tr></thead><tbody>${rows}</tbody></table>`,
    place(a),
    place(b),
  ].join("");
  return htmlPage(`${placeTitle(a)} and ${placeTitle(b)}`, body);
}
