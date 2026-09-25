import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { feedItem, finishRun, mockBackend, openWorkspace, researchResult } from "./fixtures";

/** No screen may be wider than the phone it is on: a page that scrolls sideways is the most common way a layout breaks. */
async function expectNoSidewaysScroll(page: Page, screen: string) {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }));
  expect(scrollWidth, `${screen} is ${scrollWidth}px wide on a ${innerWidth}px screen`).toBeLessThanOrEqual(innerWidth + 1);
}

for (const width of [320, 375, 768]) {
  test(`no screen scrolls sideways at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await mockBackend(page, { feed: [feedItem("a", "Road closed after crash on Massachusetts Avenue near the Square", 10, { feed_category: "Accidents & traffic" })] });

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expectNoSidewaysScroll(page, "the landing page");

    await page.goto("/app");
    await expect(page.getByText("Where should the agent investigate?")).toBeVisible();
    await expectNoSidewaysScroll(page, "the search page");

    await openWorkspace(page);
    await expectNoSidewaysScroll(page, "the workspace");

    await page.getByPlaceholder("Would this be a good place for…?").fill("Is it a good place to visit as a tourist?");
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
    await page.evaluate(
      (s) => window.__sse.send("step", s),
      { stage: "retrieval", description: "Selected community search for 'community_sentiment' (Reddit, forums, Quora, review sites)", timestamp: new Date().toISOString(), details: {} },
    );
    await expect(page.getByTestId("research-steps")).toBeVisible();
    await expectNoSidewaysScroll(page, "a run in progress");

    await finishRun(page, researchResult("Is it a good place to visit as a tourist?"));
    await expect(page.getByRole("button", { name: "Download report" })).toBeVisible();
    await expectNoSidewaysScroll(page, "an answer");

    await page.getByRole("button", { name: "Compare with another place" }).click();
    await expect(page.getByRole("dialog").getByText("Compare two places")).toBeVisible();
    await expectNoSidewaysScroll(page, "the compare dialog");
  });
}

test("the place's name still shows on a phone, with save, compare and change all reachable", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 844 });
  await mockBackend(page);
  await openWorkspace(page);
  await expect(page.getByText("Harvard Square, Cambridge").first()).toBeVisible();
  for (const name of ["Save this place", "Compare with another place", "Change location"]) {
    await expect(page.getByRole("button", { name })).toBeVisible();
  }
});
