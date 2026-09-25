import { expect, test } from "@playwright/test";
import type { ResearchResponse } from "../src/types";
import { buildComparisonHtml, buildReportHtml } from "../src/report";
import { finishRun, mockBackend, openWorkspace, researchResult } from "./fixtures";

const AT = new Date("2026-09-25T12:00:00Z");
const answer = researchResult("Is it safe?") as unknown as ResearchResponse;

test.describe("printable report (plain functions)", () => {
  test("has the same parts as the Markdown report", () => {
    const html = buildReportHtml(answer, AT);
    expect(html).toContain("<h1>Harvard Square, Cambridge</h1>");
    expect(html).toContain("<blockquote>Is it safe?</blockquote>");
    expect(html).toContain("Researched by Lugensa AI on 2026-09-25");
    expect(html).toContain('<span class="status">Supported:</span> The Red Line stops here. Sources: <a href="https://news.example.org/e1">Getting around Harvard Square</a>.');
    expect(html).toContain("<h2>Limitations</h2><ul><li>Only one source was found for this topic.</li></ul>");
    expect(html).toContain("<h2>Sources (1)</h2><ol>");
    expect(html).not.toContain("undefined");
  });

  test("escapes what other people wrote, so a source cannot put markup or script in the page", () => {
    const hostile = {
      ...answer,
      summary: "Fine <script>alert(1)</script> & more",
      evidence: [{ ...answer.evidence[0], source_title: '<img src=x onerror=alert(1)> "quoted"', source_url: 'https://example.org/?a="b"&c=<d>' }],
      limitations: ["<b>bold</b> limitation"],
    };
    const html = buildReportHtml(hostile, AT);
    expect(html).not.toMatch(/<script|<img|onerror=alert|<b>bold/i);
    expect(html).toContain("&amp; more");
    expect(html).toContain('href="https://example.org/?a=&quot;b&quot;&amp;c=&lt;d&gt;"');
  });

  test("the comparison page counts what each run found and never ranks", () => {
    const other = researchResult("Is it safe?", "Kendall Square") as unknown as ResearchResponse;
    const html = buildComparisonHtml(answer, other, AT);
    expect(html).toContain("<h1>Harvard Square, Cambridge and Kendall Square, Cambridge</h1>");
    expect(html).toContain('<th scope="row">Sources found</th><td>1</td><td>1</td>');
    expect(html).toContain("does not say which place is better");
    expect(html).not.toMatch(/\b(winner|better than|best place|recommend)/i);
  });
});

test.describe("print button", () => {
  test("puts the report in a hidden frame and asks the browser to print it", async ({ page }) => {
    await mockBackend(page);
    // Printing is stubbed in every frame, so the test needs no print dialog and can see that it was asked for.
    await page.addInitScript(() => {
      (window as unknown as { __printed: number }).__printed = 0;
      window.print = () => {
        (window.top as unknown as { __printed: number }).__printed += 1;
      };
    });
    await openWorkspace(page);
    await page.getByPlaceholder("Would this be a good place for…?").fill("Is it safe?");
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
    await finishRun(page, researchResult("Is it safe?"));

    await page.getByRole("button", { name: "Print / Save as PDF" }).click();

    const frame = page.locator("iframe#print-frame");
    await expect(frame).toHaveAttribute("srcdoc", /<h1>Harvard Square, Cambridge<\/h1>/);
    await expect(frame).toHaveAttribute("srcdoc", /Only one source was found for this topic\./);
    await page.waitForFunction(() => (window as unknown as { __printed: number }).__printed >= 1);
  });
});
