import { expect, test } from "@playwright/test";
import { buildComparisonMarkdown, buildReportMarkdown, compareRows, comparisonFileName, reportFileName } from "../src/report";
import type { ResearchResponse } from "../src/types";
import { researchResult } from "./fixtures";

// Plain functions, no browser: these run in Node.

const AT = new Date("2026-09-25T12:00:00Z");
const answer = researchResult("Would this be a good place for a college student?") as unknown as ResearchResponse;

test.describe("report", () => {
  test("lists the question, the summary, every claim with the sources it rests on, the limitations and the sources", () => {
    const md = buildReportMarkdown(answer, AT);
    expect(md).toContain("# Harvard Square, Cambridge");
    expect(md).toContain("> Would this be a good place for a college student?");
    expect(md).toContain("Researched by Lugensa AI on 2026-09-25");
    expect(md).toContain("**Supported:** The Red Line stops here. Sources: [Getting around Harvard Square](https://news.example.org/e1).");
    expect(md).toContain("## Limitations\n\n- Only one source was found for this topic.");
    expect(md).toMatch(/## Sources \(1\)\n\n1\. \[Getting around Harvard Square\]\(https:\/\/news\.example\.org\/e1\) — Example Gazette · news · 20\d\d-\d\d-\d\d/);
    expect(md).not.toContain("undefined");
  });

  test("says so when there is nothing, instead of leaving a heading empty", () => {
    const empty = { ...answer, claims: [], evidence: [], limitations: [], key_findings: [], details: "" };
    const md = buildReportMarkdown(empty, AT);
    expect(md).toContain("- None were recorded for this run.");
    expect(md).toContain("_No sources were found._");
    expect(md).not.toContain("## Claims");
    expect(md).not.toContain("## Key findings");
  });

  test("keeps a source with brackets or parentheses in its title or address from breaking its link", () => {
    const tricky = { ...answer, evidence: [{ ...answer.evidence[0], source_title: "Cafe [best] in town", source_url: "https://example.org/a_(b)" }] };
    expect(buildReportMarkdown(tricky, AT)).toContain("[Cafe \\[best\\] in town](https://example.org/a_(b%29)");
  });

  test("names the file after the place, the question and the date", () => {
    expect(reportFileName(answer, AT)).toBe("harvard-square-cambridge-would-this-be-a-good-place-for-a-college-2026-09-25.md");
  });
});

test.describe("comparison", () => {
  const other = researchResult("Would this be a good place for a college student?", "Kendall Square") as unknown as ResearchResponse;
  const richer = { ...other, evidence: [...other.evidence, { ...other.evidence[0], evidence_id: "e2", source_type: "community_forum" }] } as ResearchResponse;

  test("counts what each run found, side by side", () => {
    const rows = Object.fromEntries(compareRows(answer, richer).map((r) => [r.label, [r.a, r.b]]));
    expect(rows["Sources found"]).toEqual(["1", "2"]);
    expect(rows["Kinds of source"]).toEqual(["1", "2"]);
    expect(rows["Supported claims"]).toEqual(["1", "1"]);
    expect(rows["Contradicted claims"]).toEqual(["0", "0"]);
  });

  test("never ranks the two places", () => {
    const md = buildComparisonMarkdown(answer, richer, AT);
    expect(md).toContain("| Sources found | 1 | 2 |");
    expect(md).toContain("does not say which place is better");
    expect(md).not.toMatch(/\b(winner|better than|best place|recommend)/i);
  });

  test("names the file after both places", () => {
    expect(comparisonFileName(answer, richer, AT)).toBe("harvard-square-cambridge-vs-kendall-square-cambridge-2026-09-25.md");
  });
});
