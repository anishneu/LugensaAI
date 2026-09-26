import { expect, test } from "@playwright/test";
import { feedItem, mockBackend, openWorkspace, researchResult } from "./fixtures";

const step = (description: string, stage = "retrieval") => ({ stage, description, timestamp: new Date().toISOString(), details: {} });

test.describe("landing page", () => {
  test("opens the app from the top bar", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Ask about any place");
    await page.getByRole("button", { name: "Open the app" }).first().click();
    await expect(page).toHaveURL(/\/app$/);
    await expect(page.getByText("Where should the agent investigate?")).toBeVisible();
  });
});

test.describe("workspace", () => {
  test("picking a suggested place opens the workspace for it", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await expect(page.getByText("Harvard Square, Cambridge").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Ask/ })).toBeVisible();
  });
});

test.describe("live feed", () => {
  test("says there is nothing when there is nothing, and shows the blinking dot", async ({ page }) => {
    await mockBackend(page, { feed: [] });
    await openWorkspace(page);
    await expect(page.getByRole("heading", { name: /Live feed/ })).toBeVisible();
    await expect(page.getByRole("img", { name: "Live" })).toBeVisible();
    await expect(page.getByText("Nothing new in the last 30 days.")).toBeVisible();
  });

  test("groups items under Now and a date, labels their kind and place, and filters by kind", async ({ page }) => {
    await mockBackend(page, {
      feed: [
        feedItem("a", "Road closed after crash on Massachusetts Avenue", 10, { feed_category: "Accidents & traffic" }),
        feedItem("b", "New bookshop opens beside the Square", 60 * 24 * 3, { feed_category: "Business", feed_scope: "city", feed_place: "Cambridge" }),
      ],
    });
    await openWorkspace(page);

    await expect(page.getByRole("heading", { name: "Now" })).toBeVisible();
    await expect(page.getByText("Road closed after crash on Massachusetts Avenue")).toBeVisible();
    await expect(page.getByText("Near Harvard Square")).toBeVisible();
    await expect(page.getByText("New bookshop opens beside the Square")).toBeVisible();

    await page.getByRole("button", { name: /^Business/ }).click();
    await expect(page.getByText("New bookshop opens beside the Square")).toBeVisible();
    await expect(page.getByText("Road closed after crash on Massachusetts Avenue")).toHaveCount(0);
  });
});

test.describe("research progress", () => {
  const ask = async (page: import("@playwright/test").Page, question: string) => {
    await page.getByPlaceholder("Would this be a good place for…?").fill(question);
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
  };

  test("shows each step the agent takes while it is still working, then the answer", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await ask(page, "Is it a good place to visit as a tourist?");

    // The request carries the place and the question.
    const sent = JSON.parse(await page.evaluate(() => window.__sse.body));
    expect(sent.question).toBe("Is it a good place to visit as a tourist?");
    expect(sent.latitude).toBeCloseTo(42.3736, 3);

    const steps = page.getByTestId("research-steps");
    await expect(steps).toHaveCount(0); // nothing has been reported yet: no invented progress

    await page.evaluate((s) => window.__sse.send("step", s), step("Resolved 'Harvard Square' to Harvard Square, Cambridge, MA", "location_resolution"));
    await expect(steps).toContainText("Resolved 'Harvard Square'");

    await page.evaluate((s) => window.__sse.send("step", s), step("Selected community search for 'community_sentiment'", "tool_selection"));
    // What shows is what it is doing now; the step before it is one click away, not on the screen.
    await expect(steps).toContainText("Selected community search");
    await expect(steps).not.toContainText("Resolved 'Harvard Square'");
    await steps.getByRole("button", { name: "Show all 2 steps" }).click();
    await expect(steps.getByRole("listitem")).toHaveCount(2);
    await expect(steps).toContainText("Resolved 'Harvard Square'");
    await steps.getByRole("button", { name: "Hide the steps" }).click();
    await expect(steps.getByRole("listitem")).toHaveCount(0);

    await page.evaluate((r) => window.__sse.send("result", r), researchResult("Is it a good place to visit as a tourist?"));
    await page.evaluate(() => window.__sse.close());

    await expect(steps).toHaveCount(0);
    for (const tab of ["Overview", "Community", "Claims", "Evidence", "Details"]) {
      await expect(page.getByRole("tab", { name: new RegExp(`^${tab}`) })).toBeVisible();
    }
    await expect(page.getByText("A lively, walkable area with plenty to do.")).toBeVisible();
  });

  test("shows an error event's message instead of an answer", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await ask(page, "Is it safe?");

    await page.evaluate(() => window.__sse.send("error", { status: 500, detail: "The research run failed. The server log has the details." }));
    await page.evaluate(() => window.__sse.close());

    await expect(page.getByText("The research run failed. The server log has the details.")).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Overview/ })).toHaveCount(0);
  });

  test("says so when the stream ends without an answer", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await ask(page, "Is it safe?");

    await page.evaluate(() => window.__sse.close());

    await expect(page.getByText("The research stream ended before an answer arrived.")).toBeVisible();
  });
});
