import { expect, test } from "@playwright/test";
import { googleNewsSearchUrl } from "../src/maps";
import { finishRun, mockBackend, openWorkspace, researchResult } from "./fixtures";

test.describe("search page backdrop", () => {
  test("is a still image that drifts on a diagonal, there with the page, with no live map behind it", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/app");
    const map = page.locator("img.map-drift");
    await expect(map).toBeVisible();
    await expect(map).toHaveCSS("animation-name", "map-drift");
    // The image has loaded (it is not waiting on tiles), and no map canvas is drawing a second one.
    await expect.poll(() => map.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 1000)).toBe(true);
    await expect(page.locator("canvas")).toHaveCount(0);
    // A diagonal: it moves along both axes at once.
    const a = await map.evaluate((el) => new DOMMatrix(getComputedStyle(el).transform));
    await page.waitForTimeout(2000);
    const b = await map.evaluate((el) => new DOMMatrix(getComputedStyle(el).transform));
    // Already moving, at a real pace (about 5 px a second): not a crawl that takes seconds to get going.
    expect(Math.abs(b.e - a.e)).toBeGreaterThan(5);
    expect(Math.abs(b.f - a.f)).toBeGreaterThan(5);
    await expect(page.getByRole("link", { name: /OpenStreetMap contributors/ })).toBeVisible();
  });

  test("stands still for someone who asked for reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockBackend(page);
    await page.goto("/app");
    await expect(page.locator("img.map-drift")).toHaveCSS("animation-name", "none");
  });
});

test.describe("live feed", () => {
  test("no longer says 'No politics', and links to Google News' own results for the place", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await expect(page.getByText("Nothing new in the last 30 days.")).toBeVisible();
    await expect(page.getByText(/No politics/)).toHaveCount(0);
    const link = page.getByRole("link", { name: "See more on Google News" });
    await expect(link).toBeVisible();
    const href = (await link.getAttribute("href")) ?? "";
    expect(href).toContain("https://news.google.com/search?q=");
    expect(decodeURIComponent(href)).toContain('"Harvard Square" Cambridge when:30d');
  });
});

test("the Google News address quotes the name, adds the city and the 30-day window", () => {
  const href = googleNewsSearchUrl({ displayName: "Massachusetts Avenue, Cambridge", city: "Cambridge" });
  expect(decodeURIComponent(href)).toContain('q="Massachusetts Avenue" Cambridge when:30d');
  expect(decodeURIComponent(googleNewsSearchUrl({ displayName: "Hunts Bank", city: null }))).toContain('q="Hunts Bank" when:30d');
});

test.describe("answer toolbar", () => {
  test("print, download and copy are icons on the right of the tabs, each with a tooltip", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockBackend(page);
    await openWorkspace(page);
    await page.getByPlaceholder("Would this be a good place for…?").fill("Is it safe?");
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
    await finishRun(page, researchResult("Is it safe?"));

    const download = page.getByRole("button", { name: "Download report" });
    await expect(download).toBeVisible();
    expect((await download.textContent())?.trim()).toBe(""); // an icon, no text

    // On the same row as the tabs, to their right.
    const tab = await page.getByRole("tab", { name: /^Details/ }).boundingBox();
    const icon = await download.boundingBox();
    expect(Math.abs((icon!.y + icon!.height) - (tab!.y + tab!.height))).toBeLessThan(40);
    expect(icon!.x).toBeGreaterThan(tab!.x + tab!.width);

    const tooltip = page.locator("span[aria-hidden=true]", { hasText: /^Download report$/ });
    await expect(tooltip).toHaveCSS("opacity", "0");
    await download.hover();
    await expect(tooltip).toHaveCSS("opacity", "1");
    await page.mouse.move(5, 5);
    await expect(tooltip).toHaveCSS("opacity", "0");
    // The keyboard gets it too.
    await download.focus();
    await expect(tooltip).toHaveCSS("opacity", "1");
  });
});

test.describe("saved places menu", () => {
  test("lists what was saved, from the workspace, and opens one", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await page.getByRole("button", { name: /^Saved places/ }).click();
    await page.getByRole("button", { name: "Save this place" }).click();
    await page.keyboard.press("Escape");

    // Move to another place, then come back through the list.
    await page.getByRole("button", { name: "Change location" }).click();
    const search = page.getByPlaceholder(/Try/i).first();
    await search.fill("Kendall");
    await page.getByRole("option").first().click();
    await expect(page.getByText("Kendall Square, Cambridge").first()).toBeVisible();

    await page.getByRole("button", { name: /^Saved places/ }).click();
    await expect(page.getByRole("button", { name: "Save this place" })).toBeVisible(); // Kendall is not saved
    await page.getByRole("button", { name: "Harvard Square, Cambridge", exact: true }).click();
    await expect(page.getByText("Cambridge, Massachusetts, United States").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /^Saved places \(1\)/ })).toBeVisible();
  });
});

test.describe("compare dialog", () => {
  test("opens in the middle of the page, not against the top", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockBackend(page);
    await openWorkspace(page);
    await page.getByRole("button", { name: "Compare with another place" }).click();
    const panel = page.getByRole("dialog").locator("> div").first();
    await expect(page.getByRole("dialog").getByText("Compare two places")).toBeVisible();
    await page.waitForTimeout(400); // the opening transition
    const box = (await page.getByRole("dialog").getByText("Compare two places").locator("xpath=ancestor::*[contains(@class,'rounded-3xl')][1]").boundingBox())!;
    void panel;
    const middle = box.y + box.height / 2;
    expect(Math.abs(middle - 450)).toBeLessThan(70);
    expect(box.y).toBeGreaterThan(60);
  });
});

test.describe("what the agent is doing", () => {
  test("shows one current step, timing on one line, and no long list under it", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    await page.getByPlaceholder("Would this be a good place for…?").fill("Is it safe?");
    await page.getByRole("button", { name: "Ask →" }).click();
    await page.waitForFunction(() => window.__sse.started);
    for (const [stage, description] of [
      ["location_resolution", "Using pre-resolved location Harvard Square"],
      ["research_planning", "Working out which topics the question needs"],
      ["tool_selection", "Selected community search for 'community_sentiment'"],
    ]) {
      await page.evaluate((s) => window.__sse.send("step", s), { stage, description, timestamp: new Date().toISOString(), details: {} });
    }
    const steps = page.getByTestId("research-steps");
    await expect(steps).toContainText("Selected community search");
    await expect(steps.getByRole("listitem")).toHaveCount(0);
    await expect(page.getByText(/elapsed/)).toBeVisible();
    // The old panel's extra paragraphs are gone.
    await expect(page.getByText(/Reasoning locally via Ollama/)).toHaveCount(0);
    await expect(page.locator("[class*='animate-[slide']")).toHaveCount(0);
  });
});
