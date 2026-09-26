import { expect, test } from "@playwright/test";
import { googleNewsSearchUrl } from "../src/maps";
import { flattenMap } from "../src/mapFlat";
import { placeSubtitle } from "../src/textUtils";
import { finishRun, mockBackend, openWorkspace, researchResult } from "./fixtures";

test.describe("search page backdrop", () => {
  const current = 'div[data-slide="current"] img.map-drift';
  const moves = (page: import("@playwright/test").Page) =>
    page.locator(current).evaluate((el) => ({ dx: Number(el.style.getPropertyValue("--dx")), dy: Number(el.style.getPropertyValue("--dy")) }));

  test("is a still image that drifts, there with the page, with no live map behind it", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/app");
    const map = page.locator(current);
    await expect(map).toBeVisible();
    await expect(map).toHaveCSS("animation-name", "map-drift");
    // The image has loaded (it is not waiting on tiles), and no map canvas is drawing a second one.
    await expect.poll(() => map.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 1000)).toBe(true);
    await expect(page.locator("canvas")).toHaveCount(0);
    // Already moving, at a real pace (about 5 px a second): not a crawl that takes seconds to get going.
    const { dx, dy } = await moves(page);
    const before = await map.evaluate((el) => new DOMMatrix(getComputedStyle(el).transform));
    await page.waitForTimeout(2000);
    const after = await map.evaluate((el) => new DOMMatrix(getComputedStyle(el).transform));
    if (dx !== 0) expect(Math.abs(after.e - before.e)).toBeGreaterThan(5);
    if (dy !== 0) expect(Math.abs(after.f - before.f)).toBeGreaterThan(5);
    await expect(page.getByRole("link", { name: /OpenStreetMap contributors/ })).toBeVisible();
  });

  test("changes to another city by itself, with the next map already loaded, and drifts across, up and down, and on both diagonals", async ({ page }) => {
    await page.clock.install();
    await mockBackend(page);
    await page.goto("/app");
    await expect(page.locator(current)).toBeVisible();
    const first = await page.locator(current).getAttribute("src");

    const kinds = new Set<string>();
    const cities = new Set<string>([first ?? ""]);
    let previous = "";
    for (let slide = 0; slide < 5; slide++) {
      const { dx, dy } = await moves(page);
      const kind = dy === 0 ? "across" : dx === 0 ? "up and down" : dy > 0 ? "diagonal down" : "diagonal up";
      expect(kind, "two maps in a row never drift the same way").not.toBe(previous);
      previous = kind;
      kinds.add(kind);
      // The next map is fetched while this one shows: give it a moment, then change.
      await page.waitForTimeout(1500);
      await page.clock.runFor(26_500);
      const src = (await page.locator(current).getAttribute("src")) ?? "";
      cities.add(src);
      // It is on screen already loaded: no wait, no blank.
      expect(await page.locator(current).evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 1000)).toBe(true);
      await expect(page.locator('div[data-slide="leaving"]')).toHaveCount(1); // fading out underneath, so the page is never bare
      await page.clock.runFor(3_000);
      await expect(page.locator('div[data-slide="leaving"]')).toHaveCount(0);
    }
    expect(cities.size, "a different city each time").toBe(6);
    expect(kinds, "every kind of movement comes round").toEqual(new Set(["across", "up and down", "diagonal down", "diagonal up"]));
  });

  test("is a different city on different visits", async ({ page }) => {
    test.setTimeout(90_000); // several page loads, and the machine is often busy with the other tests
    await mockBackend(page);
    const seen = new Set<string>();
    for (let visit = 0; visit < 6; visit++) {
      await page.goto("/app");
      const map = page.locator(current);
      await expect(map).toBeVisible();
      await expect.poll(() => map.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 1000)).toBe(true);
      const src = (await map.getAttribute("src")) ?? "";
      expect(src).toMatch(/(paris|cairo|nairobi|sao-paulo|sydney|istanbul|mumbai|berlin|tokyo|chicago|san-francisco)/);
      seen.add(src);
    }
    expect(seen.size).toBeGreaterThan(1);
  });

  test("stands still, on one map, for someone who asked for reduced motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.clock.install();
    await mockBackend(page);
    await page.goto("/app");
    const map = page.locator(current);
    await expect(map).toHaveCSS("animation-name", "none");
    const first = await map.getAttribute("src");
    await page.clock.runFor(90_000);
    expect(await map.getAttribute("src")).toBe(first);
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
    // In the right-hand corner of the feed, not the left.
    const feed = (await page.locator("aside", { hasText: "Live feed" }).boundingBox())!;
    const box = (await link.boundingBox())!;
    expect(box.x + box.width).toBeGreaterThan(feed.x + feed.width - 40);
    expect(box.x).toBeGreaterThan(feed.x + feed.width / 3);
  });
});

test.describe("place suggestions", () => {
  test("never list the same place twice", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/app");
    await page.getByPlaceholder(/Try/i).first().fill("germany");
    const options = page.getByRole("option");
    await expect(options.first()).toBeVisible();
    await expect(options).toHaveCount(2); // the two "Germany" rows became one; Berlin is a different place
    await expect(options.filter({ hasText: /^Germany/ })).toHaveCount(1);
    await expect(options.filter({ hasText: "Berlin" })).toHaveCount(1);
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
    await expect(page.getByText("Massachusetts, United States").first()).toBeVisible();
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

test.describe("the top bar", () => {
  test("Saved places and Compare are icons alone, with their names in a tooltip", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    for (const [name, tip] of [[/^Saved places/, /^Saved places/], ["Compare with another place", /^Compare with another place$/]] as const) {
      const button = page.getByRole("button", { name });
      await expect(button).toBeVisible();
      expect((await button.textContent())?.trim(), "an icon, no text").toBe("");
      const tooltip = page.locator("span[aria-hidden=true]", { hasText: tip });
      await expect(tooltip).toHaveCSS("opacity", "0");
      await button.hover();
      await expect(tooltip).toHaveCSS("opacity", "1");
      await page.mouse.move(5, 5);
    }
    // "Change location" keeps its words.
    await expect(page.getByRole("button", { name: "Change location" })).toContainText("Change location");
  });

  test("does not say the city twice: the line under the name leaves out what the name already says", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    const header = page.locator("header");
    await expect(header).toContainText("Harvard Square, Cambridge");
    await expect(header).toContainText("Massachusetts, United States");
    const text = (await header.innerText()).replace(/\s+/g, " ");
    expect(text.match(/Cambridge/g)).toHaveLength(1);
  });
});

test.describe("placeSubtitle (plain function)", () => {
  test("drops what the name says, and what repeats", () => {
    expect(placeSubtitle("Chi-Joan How, Boston", ["Boston", "Massachusetts", "United States"])).toBe("Massachusetts, United States");
    expect(placeSubtitle("Harvard Square, Cambridge", ["Cambridge", "Massachusetts", "United States"])).toBe("Massachusetts, United States");
    expect(placeSubtitle("Singapore", ["Singapore", null, "Singapore"])).toBe("");
    expect(placeSubtitle("Shibuya, Tokyo", ["Tokyo", "Tokyo", "Japan"])).toBe("Japan");
  });

  test("keeps what is different, and matches whole words only", () => {
    expect(placeSubtitle("Boston Common", ["Boston", "Massachusetts", "United States"])).toBe("Massachusetts, United States");
    expect(placeSubtitle("Bostonian Hotel", ["Boston", "Massachusetts", "United States"])).toBe("Boston, Massachusetts, United States");
    expect(placeSubtitle("Kyoto Station", [null, undefined, "Japan"])).toBe("Japan");
  });

  test("copes with names that have punctuation and other scripts", () => {
    expect(placeSubtitle("St. John's, Newfoundland", ["St. John's", "Newfoundland and Labrador", "Canada"])).toBe("Newfoundland and Labrador, Canada");
    expect(placeSubtitle("渋谷区, 東京", ["東京", "日本"])).toBe("日本");
  });
});

test.describe("flat pin map (plain function)", () => {
  const fakeMap = (types: string[]) => {
    const layers = types.map((type, i) => ({ id: `${type}-${i}`, type }));
    const removed: string[] = [];
    return { removed, map: { getStyle: () => ({ layers }), removeLayer: (id: string) => void removed.push(id) } };
  };

  test("removes the extruded 3D building layers and nothing else", () => {
    const { map, removed } = fakeMap(["background", "fill", "line", "fill-extrusion", "symbol", "fill-extrusion"]);
    expect(flattenMap(map)).toBe(2);
    expect(removed).toEqual(["fill-extrusion-3", "fill-extrusion-5"]);
  });

  test("leaves a style with no 3D layers alone", () => {
    const { map, removed } = fakeMap(["background", "fill", "line", "symbol"]);
    expect(flattenMap(map)).toBe(0);
    expect(removed).toEqual([]);
    expect(flattenMap({ getStyle: () => ({}), removeLayer: () => undefined })).toBe(0);
  });
});

test.describe("left sidebar", () => {
  test("leaves room below the last suggested question, even when the column has to scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 620 }); // short, so the left column scrolls
    await mockBackend(page);
    await openWorkspace(page);
    const column = page.locator("aside").first();
    const last = page.getByRole("button", { name: "Is it safe, and easy to get around?" });
    await last.scrollIntoViewIfNeeded();
    await column.evaluate((el) => el.scrollTo(0, el.scrollHeight));
    const columnBox = (await column.boundingBox())!;
    const lastBox = (await last.boundingBox())!;
    expect(columnBox.y + columnBox.height - (lastBox.y + lastBox.height), "space under the last suggestion").toBeGreaterThanOrEqual(16);
  });
});

test.describe("saved menu and tooltip", () => {
  test("the button's tooltip is not shown while its menu is open, and is back once it closes", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    const tooltip = page.locator("span[aria-hidden=true]", { hasText: /^Saved places/ });
    const button = page.getByRole("button", { name: /^Saved places/ });

    await button.hover();
    await expect(tooltip).toHaveCSS("opacity", "1");

    await button.click(); // the menu opens and the button keeps focus
    await expect(page.getByRole("button", { name: "Save this place" })).toBeVisible();
    await expect(tooltip, "no tooltip peeking out beside the open menu").toHaveCount(0);

    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Save this place" })).toHaveCount(0);
    await button.hover();
    await expect(page.locator("span[aria-hidden=true]", { hasText: /^Saved places/ })).toHaveCSS("opacity", "1");
  });
});

test.describe("the live feed header: card and app agree", () => {
  const dotIsAfterTheTitle = (title: { x: number; width: number }, dot: { x: number; width: number }) => {
    expect(dot.x, "the red dot comes after the words").toBeGreaterThan(title.x + title.width * 0.6);
  };

  test("in the app, the red dot follows the words 'Live feed'", async ({ page }) => {
    await mockBackend(page);
    await openWorkspace(page);
    const heading = (await page.getByRole("heading", { name: /Live feed/ }).boundingBox())!;
    const dot = (await page.getByRole("img", { name: "Live" }).boundingBox())!;
    dotIsAfterTheTitle(heading, dot);
    // ...and the refresh button is at the far right of the same row.
    const refresh = (await page.getByRole("button", { name: "Refresh the live feed" }).boundingBox())!;
    expect(refresh.x).toBeGreaterThan(dot.x + 40);
  });

  test("on the landing page card, the red dot follows the words too, and the refresh button is at the far right", async ({ page }) => {
    await mockBackend(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    const card = page.locator("figure");
    const title = card.locator("span", { hasText: /^Live feed$/ }).first();
    await title.scrollIntoViewIfNeeded();
    const titleBox = (await title.boundingBox())!;
    const dot = (await card.locator(".live-blink").boundingBox())!;
    dotIsAfterTheTitle(titleBox, dot);
    expect(dot.x + dot.width, "inside the title row, at its end").toBeLessThanOrEqual(titleBox.x + titleBox.width + 1);
  });
});
