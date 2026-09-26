import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { finishRun, mockBackend, openWorkspace, researchResult } from "./fixtures";

const step = (description: string, stage = "retrieval") => ({ stage, description, timestamp: new Date().toISOString(), details: {} });
const QUESTION_BOX = "Would this be a good place for…?";

test.describe("saved places", () => {
  test("a saved place waits on the search page, opens from there, and can be removed", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);

    // The star opens the saved-places menu: save this place from there, and see the list.
    await page.getByRole("button", { name: /^Saved places/ }).click();
    await page.getByRole("button", { name: "Save this place" }).click();
    await expect(page.getByRole("button", { name: "Remove this place from saved" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /^Saved places \(1\)/ })).toBeVisible();
    await expect(page.getByRole("list").getByText("Harvard Square, Cambridge")).toBeVisible();
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Change location" }).click();
    const saved = page.getByRole("region", { name: "Saved places" });
    await expect(saved.getByRole("button", { name: "Harvard Square, Cambridge", exact: true })).toBeVisible();

    // It survives a reload: it is kept in this browser.
    await page.reload();
    await expect(page.getByRole("region", { name: "Saved places" })).toBeVisible();

    await page.getByRole("region", { name: "Saved places" }).getByRole("button", { name: "Harvard Square, Cambridge", exact: true }).click();
    await expect(page.getByPlaceholder(QUESTION_BOX)).toBeVisible();
    await page.getByRole("button", { name: /^Saved places/ }).click();
    await expect(page.getByRole("button", { name: "Remove this place from saved" })).toBeVisible(); // still marked as saved
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Change location" }).click();
    await page.getByRole("button", { name: "Remove Harvard Square, Cambridge from saved places" }).click();
    await expect(page.getByRole("region", { name: "Saved places" })).toHaveCount(0);
  });
});

test.describe("export", () => {
  test("downloads the answer as Markdown with its claims, limitations and sources", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await page.getByPlaceholder(QUESTION_BOX).fill("Is it good for tourists?");
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
    await finishRun(page, researchResult("Is it good for tourists?"));

    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download report" }).click()]);
    expect(download.suggestedFilename()).toMatch(/^harvard-square-cambridge-is-it-good-for-tourists-\d{4}-\d{2}-\d{2}\.md$/);

    const markdown = readFileSync((await download.path()) as string, "utf8");
    expect(markdown).toContain("# Harvard Square, Cambridge");
    expect(markdown).toContain("> Is it good for tourists?");
    expect(markdown).toContain("**Supported:** The Red Line stops here.");
    expect(markdown).toContain("[Getting around Harvard Square](https://news.example.org/e1)");
    expect(markdown).toContain("Only one source was found for this topic.");
  });
});

test.describe("compare two places", () => {
  async function pickSecondPlace(page: import("@playwright/test").Page, question: string) {
    await page.getByRole("button", { name: "Compare with another place" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Compare two places")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Compare", exact: true })).toBeDisabled();
    await dialog.getByPlaceholder("Search a place to compare with…").fill("Kendall");
    await page.getByRole("option").first().click();
    await expect(dialog.getByText("Picked: Kendall Square, Cambridge")).toBeVisible();
    await dialog.getByLabel("Question, asked of both").fill(question);
    await dialog.getByRole("button", { name: "Compare", exact: true }).click();
    return dialog;
  }

  test("runs the question for each place in turn, shows both, counts what each found, and exports the comparison", async ({ page }) => {
    const question = "Would this be a good place for a college student?";
    await mockBackend(page);
    await openWorkspace(page);
    const dialog = await pickSecondPlace(page, question);

    // The first run is Harvard Square's, and the second waits for it.
    await page.waitForFunction(() => window.__sse.count === 1);
    expect(JSON.parse(await page.evaluate(() => window.__sse.body)).latitude).toBeCloseTo(42.3736, 3);
    await expect(dialog.getByText("Waiting for Harvard Square, Cambridge to finish.")).toBeVisible();
    await page.evaluate((s) => window.__sse.send("step", s), step("Selected community search for Harvard Square", "tool_selection"));
    await expect(dialog.getByTestId("research-steps")).toContainText("Selected community search for Harvard Square");
    await finishRun(page, researchResult(question, "Harvard Square"));

    // Then Kendall Square's, from its own coordinates.
    await page.waitForFunction(() => window.__sse.count === 2);
    expect(JSON.parse(await page.evaluate(() => window.__sse.body)).latitude).toBeCloseTo(42.3629, 3);
    await finishRun(page, researchResult(question, "Kendall Square"));

    await expect(dialog.getByText("Harvard Square is a lively, walkable area with plenty to do.")).toBeVisible();
    await expect(dialog.getByText("Kendall Square is a lively, walkable area with plenty to do.")).toBeVisible();

    const table = dialog.getByRole("table");
    await expect(table.getByRole("row", { name: /Sources found/ })).toContainText("1");
    await expect(table.getByRole("row", { name: /Supported claims/ })).toContainText("1");
    await expect(dialog.getByText(/not how good either place is/)).toBeVisible();

    const [download] = await Promise.all([page.waitForEvent("download"), dialog.getByRole("button", { name: "Download the comparison" }).click()]);
    expect(download.suggestedFilename()).toMatch(/^harvard-square-cambridge-vs-kendall-square-cambridge-\d{4}-\d{2}-\d{2}\.md$/);
    const markdown = readFileSync((await download.path()) as string, "utf8");
    expect(markdown).toContain("# Harvard Square, Cambridge and Kendall Square, Cambridge");
    expect(markdown).toContain("| Sources found | 1 | 1 |");
  });

  test("one place failing does not stop the other, and no comparison table is shown", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    const dialog = await pickSecondPlace(page, "Is it safe?");

    await page.waitForFunction(() => window.__sse.count === 1);
    // An error event ends that run at once, and the app moves straight on to the second place.
    await page.evaluate(() => window.__sse.send("error", { status: 500, detail: "The research run failed. The server log has the details." }));

    await page.waitForFunction(() => window.__sse.count === 2);
    await finishRun(page, researchResult("Is it safe?", "Kendall Square"));

    await expect(dialog.getByText("The research run failed. The server log has the details.")).toBeVisible();
    await expect(dialog.getByText("Kendall Square is a lively, walkable area with plenty to do.")).toBeVisible();
    await expect(dialog.getByRole("table")).toHaveCount(0);
  });
});
