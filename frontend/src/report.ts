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
