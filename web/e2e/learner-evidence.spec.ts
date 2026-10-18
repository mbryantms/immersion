import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

const profile = { goal: "listen", level: "unknown", script: "source", interests: [] };

test("learning preferences are optional, editable, and accessible on mobile", async ({ page }, info) => {
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/learner-profile", async (route) => {
    if (route.request().method() === "PUT") saved = route.request().postDataJSON();
    await route.fulfill({ json: saved ?? profile });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings");
  await page.getByRole("combobox", { name: "Practice goal" }).selectOption("read");
  await page.getByRole("combobox", { name: "Starting level" }).selectOption("beginner");
  await page.getByRole("textbox", { name: "Topics or series titles" }).fill("Travel, cooking");
  await page.getByRole("button", { name: "Save learning preferences" }).click();
  await expect(page.getByText("Learning preferences saved", { exact: true })).toBeVisible();
  expect(saved).toEqual({ ...profile, goal: "read", level: "beginner", interests: ["Travel", "cooking"] });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("learner-profile-mobile.png"), fullPage: true });
});

test("home distinguishes indexed words, encounters, and recommendation uncertainty", async ({ page }, info) => {
  const requests: string[] = [];
  await page.route("**/api/stats/dashboard**", async (route) => {
    const population = new URL(route.request().url()).searchParams.get("population"); requests.push(population ?? "");
    await route.fulfill({ json: { weeks: [], totals: { lookups: 1, sentences_played: 30, saves: 1 }, recurring_unknowns: population === "encountered" ? [] : [{ lexeme_id: 1, simplified: "的", pinyin: "de5", occurrences: 20, items: 2 }], review_due: 1, graduated_waiting: 0, anki: { last_import: null, last_export: null }, practice_evidence: [{ task: "reading_recall", method: "self_report", assistance: "none_reported", attempts: 3, mean_score: 0.67 }] } });
  });
  await page.route("**/api/recommendations", async (route) => {
    await route.fulfill({ json: { band: { low: .88, high: .985 }, fallback: true, items: [{ item_id: 1, title: "Travel sample", kind: "video", series_title: "Travel", thumb_url: "/media/thumbs/1.jpg", coverage: .7, unknown_lexemes: 20, unknowns_per_minute: 5, dense_unknowns_30s: 8, subtitle_characters_per_minute: 200, subtitle_source: "whisper", source_warning: true, reasons: ["5 unfamiliar token occurrences/min", "8 unfamiliar tokens in the densest 30-second cue-start window"], uncertainty: "Estimated from vocabulary marks and subtitle timing; grammar, audio clarity and actual comprehension are unmeasured." }] } });
  });
  await page.goto("/");
  await expect(page.getByText("20 indexed occurrences in 2 sources")).toBeVisible();
  await page.getByRole("button", { name: "You have encountered", exact: true }).click();
  await expect(page.getByText(/No words in this population yet/)).toBeVisible();
  await page.getByRole("button", { name: "In your library", exact: true }).click();
  await expect(page.getByText("20 indexed occurrences in 2 sources")).toBeVisible();
  expect(requests).toContain("encountered");
  await page.getByText("Why this sample?", { exact: true }).click();
  await expect(page.getByText(/actual comprehension are unmeasured/)).toBeVisible();
  await expect(page.getByText(/Automatic or unverified source/)).toBeVisible();
  await expect(page.getByText("67% average reported recall", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("recommendations-mobile.png"), fullPage: true });
});

test("difficulty feedback preserves task and recovers from a failed save", async ({ page }) => {
  const submitted: Record<string, unknown>[] = [];
  await page.route("**/api/items/1/difficulty", async (route) => {
    submitted.push(route.request().postDataJSON());
    await route.fulfill({ status: submitted.length === 1 ? 503 : 200, json: { saved: true } });
  });
  await page.goto("/watch/1");
  await page.getByRole("radio", { name: "Listen", exact: true }).click();
  await page.getByText("How difficult is this sample?", { exact: true }).click();
  await page.getByRole("button", { name: "Too hard", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Rating could not be saved");
  await page.getByRole("button", { name: "Too hard", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Rating saved for listening");
  expect(submitted[1]).toMatchObject({ rating: "too_hard", goal: "listen" });
  await page.getByRole("radio", { name: "Read", exact: true }).click();
  await expect(page.getByRole("button", { name: "Too hard", exact: true })).toHaveAttribute("aria-pressed", "false");
});

test("word evidence separates selected meaning recall from exposure", async ({ page }, info) => {
  await page.route("**/api/lexemes/1", async (route) => {
    await route.fulfill({ json: { lexeme_id: 1, simplified: "学习", traditional: "學習", pinyin: "xue2 xi2", hsk: 1, is_dict: true, senses: [{ py: "xue2 xi2", defs: ["study"] }], state: "familiar", state_source: "derived", saved_item_id: 1, stats: { encounters: 100, lookups: 2, distinct_items: 3 }, evidence: { exposure: { independent_encounters: 12, items: 3, days: 5, policy: "At most one encounter per word/source/UTC day; exposure only" }, recent_retrieval: [{ task: "reading_recall", method: "self_report", assistance: "none_reported", score: 1, ts: "2026-10-18T10:00:00Z", scope: { reading: "xue2 xi2", meaning: "study", delayed: true } }], unassessed: ["pronunciation", "spontaneous_production"], limitation: "Vocabulary signals do not measure listening comprehension." } } });
  });
  await page.goto("/word/1");
  await expect(page.getByText("12 independent encounters · 3 sources · 5 days")).toBeVisible();
  await expect(page.getByText(/Selected scope: xue2 xi2 study/)).toBeVisible();
  await expect(page.getByText(/Pronunciation and spontaneous production have not been assessed/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("word-evidence-mobile.png"), fullPage: true });
});
