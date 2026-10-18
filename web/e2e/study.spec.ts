import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

test("video supports explicit listening hints and dictation without leaking text", async ({ page }) => {
  await page.goto("/watch/1");
  await expect(page.getByRole("radio", { name: "Read", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Listen", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Let your ears lead" })).toBeVisible();
  await expect(page.locator(".subtitle-primary")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Interactive transcript" })).toHaveCount(0);
  await page.getByRole("button", { name: "Reveal transcript as a hint" }).click();
  await expect(page.getByText("Transcript hint is visible")).toBeVisible();
  await page.getByRole("button", { name: "Hide text again" }).click();
  await expect(page.getByRole("heading", { name: "Interactive transcript" })).toHaveCount(0);
  await page.getByRole("radio", { name: "Dictate", exact: true }).click();
  const answer = page.getByRole("textbox", { name: "Dictation answer for sentence 1" });
  await answer.fill("学习，再学习。");
  await answer.press("Enter");
  await expect(page.getByLabel("100 percent character accuracy")).toBeVisible();
  await expect(page.locator(".subtitle-primary")).toHaveCount(0);
});

test("review masks repeated targets, explains answers, and sends only one pending grade", async ({ page }) => {
  let submitted = 0;
  await page.route("**/api/review/1/outcome", async (route) => {
    submitted++;
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.fulfill({ json: { result: "pass", rung: 0, graduated: false, already_in_anki: false, suggest_drop: false, next_due_days: 1 } });
  });
  await page.goto("/review");
  await expect(page.getByLabel("missing word")).toHaveCount(2);
  await expect(page.getByText("to study; to learn")).toHaveCount(0);
  expect(await page.locator("audio").evaluate((audio: HTMLAudioElement) => audio.paused)).toBe(true);
  await page.getByRole("button", { name: "Reveal answer" }).click();
  await expect(page.getByText("to study; to learn")).toBeVisible();
  await page.getByRole("button", { name: "Recalled", exact: true }).click();
  await expect(page.getByRole("button", { name: "Saving…" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Session complete" })).toBeVisible();
  expect(submitted).toBe(1);
});

test("failed review preserves the card and reuses its request UUID", async ({ page }) => {
  const ids: string[] = [];
  await page.route("**/api/review/1/outcome", async (route) => {
    ids.push(route.request().postDataJSON().request_uuid);
    await route.fulfill({ status: ids.length === 1 ? 503 : 200, json: { result: "pass", rung: 0, graduated: false, already_in_anki: false, suggest_drop: false, next_due_days: 1 } });
  });
  await page.goto("/review");
  await page.getByRole("button", { name: "Reveal answer" }).click();
  await page.getByRole("button", { name: "Recalled", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("could not be confirmed");
  await page.getByRole("button", { name: "Recalled", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Session complete" })).toBeVisible();
  expect(ids[0]).toBe(ids[1]);
});

test("gloss traps focus, closes with Escape, and restores the selected word", async ({ page }) => {
  await page.goto("/watch/1");
  // Keep the locator on the transcript: the video overlay can mount after metadata arrives.
  const word = page.locator('[data-sentence-id="1"]').last().getByRole("button", { name: "Look up 学习" }).first();
  await word.click();
  const dialog = page.getByRole("dialog", { name: "Definition for 学习" });
  await expect(dialog).toBeVisible();
  await dialog.evaluate(async (element) => { await Promise.all(element.getAnimations({ subtree: true }).map((animation) => animation.finished.catch(() => {}))); });
  const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(accessibility.violations.map((item) => ({ id: item.id, targets: item.nodes.map((node) => node.target) }))).toEqual([]);
  for (let i = 0; i < 14; i++) await page.keyboard.press("Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(word).toBeFocused();
});

for (const width of [320, 390, 768, 1440]) {
  test(`study surface is usable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/watch/1");
    await page.getByRole("radio", { name: "Listen", exact: true }).click();
    await expect(page.getByRole("button", { name: "Reveal transcript as a hint" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`listen-${width}.png`), fullPage: true });
  });
}

for (const path of ["/", "/library", "/series/1", "/review", "/saved", "/search", "/settings", "/admin", "/watch/1"]) {
  test(`WCAG scan ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeVisible();
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(result.violations.map(({ id, nodes }) => ({ id, targets: nodes.map((node) => node.target) }))).toEqual([]);
  });
}

test("study selector works from the keyboard and a new audio item starts a fresh session", async ({ page }) => {
  await page.goto("/watch/1");
  await page.getByRole("radio", { name: "Read", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "Listen", exact: true })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByRole("radio", { name: "Listen", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "Next episode" }).click();
  await expect(page).toHaveURL(/\/watch\/2$/);
  await expect(page.getByRole("radio", { name: "Read", exact: true })).toBeChecked();
  await expect(page.locator("audio")).toHaveCount(1);
  await page.getByRole("radio", { name: "Dictate", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Dictation answer for sentence 1" })).toBeVisible();
});

for (const path of ["/", "/library", "/series/1", "/review", "/saved", "/search", "/settings", "/admin"]) {
  test(`mobile layout ${path}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeVisible();
    if (path === "/review") await page.getByRole("button", { name: "Reveal answer" }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("mobile.png"), fullPage: true });
  });
}

test("dictation permits only explicitly enabled script variants", async ({ page }) => {
  await page.goto("/watch/1");
  await page.getByRole("radio", { name: "Dictate", exact: true }).click();
  await page.getByRole("combobox", { name: "Character script" }).selectOption("equivalent");
  const answer = page.getByRole("textbox", { name: "Dictation answer for sentence 1" });
  await answer.fill("學習，再學習。");
  await answer.press("Enter");
  await expect(page.getByLabel("100 percent character accuracy")).toBeVisible();
  await page.getByRole("combobox", { name: "Character script" }).selectOption("source");
  await expect(page.getByLabel("100 percent character accuracy")).toBeVisible();
});

test("lookup saves a specific meaning, reading, and source occurrence", async ({ page }, info) => {
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/saved-items", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill({ json: { id: 2, created: true } });
  });
  await page.goto("/watch/1");
  await page.getByRole("button", { name: "Look up 学习", exact: true }).last().click();
  await page.getByRole("radio", { name: "Learn meaning 2: to learn", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: info.outputPath("selected-meaning-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Save selected meaning" }).click();
  await expect.poll(() => saved?.selected_meaning).toBe("to learn");
  expect(saved?.selected_reading).toBe("xue2 xi2");
  expect(saved?.occurrence_start).toBe(4);
});

test("source selection distinguishes repeated words and ignores ruby", async ({ page }) => {
  let requested: { start: number; end: number } | undefined;
  await page.route("**/api/lookup", async (route) => {
    requested = route.request().postDataJSON();
    await route.fulfill({ json: { span: "学习", candidates: [] } });
  });
  await page.goto("/watch/1");
  await page.getByRole("button", { name: "Look up 学习", exact: true }).last().evaluate((token) => {
    const spans = token.querySelectorAll("span[class^=t]");
    const range = document.createRange();
    range.setStart(spans[0].firstChild!, 0);
    range.setEnd(spans[1].firstChild!, 1);
    const selection = window.getSelection()!;
    selection.removeAllRanges(); selection.addRange(range);
    token.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  await expect.poll(() => requested).toMatchObject({ start: 4, end: 6 });
});
