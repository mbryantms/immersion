import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./fixtures";

import { sceneRoutes } from "./scene-fixture";

test("guided scene hides answers, survives a lost response, and resumes scheduled progress", async ({ page }, info) => {
  const requests = await sceneRoutes(page, { loseReply: true });
  await page.goto("/watch/1");
  await page.getByRole("radio", { name: "Listen", exact: true }).click();
  await page.getByRole("button", { name: "Study a short scene", exact: true }).click();
  expect(requests.find((request) => request.path === "create")?.body.goal).toBe("listen");
  await expect(page).toHaveURL(/\/scenes\/1$/);
  await expect(page.getByRole("heading", { name: "Watch or listen", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue: Clarify", exact: true }).click();
  await page.getByRole("button", { name: "Continue: Less support", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("could not be confirmed");
  await page.getByRole("button", { name: "Retry change", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Less support", exact: true })).toBeVisible();
  await expect(page.getByText("学习，再学习。", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Study, then study again.", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Add or replace a local meaning question", { exact: true })).toHaveCount(0);
  const reduced = requests.filter((request) => request.path === "step" && request.body.stage === "reduce");
  expect(reduced[0].body).toEqual(reduced[1].body);
  await page.setViewportSize({ width: 390, height: 844 });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("guided-listening-mobile.png"), fullPage: true });
  await page.getByRole("button", { name: "Reveal Chinese as a hint" }).click();
  await expect(page.getByText("学习，再学习。", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Continue: Check meaning", exact: true }).click();
  await expect(page.getByText(/There is no reviewed question/)).toBeVisible();
  await page.getByRole("button", { name: "I could explain the meaning", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("self-report");
  await page.getByRole("button", { name: "Finish and schedule a revisit", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Revisit later", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Start due revisit" })).toBeDisabled();
  await page.reload();
  await expect(page.getByText(/The next revisit is 2099-10-19/)).toBeVisible();
  expect(requests.some((request) => request.path === "hint" && request.body.kind === "text")).toBe(true);
});

test("scene vocabulary requires a contextual meaning and an intentional budget override", async ({ page }) => {
  const requests = await sceneRoutes(page, { budgetZero: true });
  await page.goto("/scenes/1");
  await page.getByRole("button", { name: "Continue: Clarify", exact: true }).click();
  const save = page.getByRole("button", { name: "Save this meaning", exact: true });
  await expect(save).toBeDisabled();
  await page.getByRole("combobox", { name: "Reading and meaning for 学习" }).selectOption("0");
  await expect(save).toBeDisabled();
  await page.getByRole("checkbox", { name: "Save this word beyond today's suggestion" }).check();
  await save.click();
  await expect(page.getByRole("button", { name: "Saved for review", exact: true })).toBeDisabled();
  expect(requests.find((request) => request.path === "save")?.body).toMatchObject({ selected_reading: "xue2 xi2", selected_meaning: "to study", sentence_id: 1 });
});

test("a local scene question has explicit review, feedback and suspend recovery", async ({ page }, info) => {
  const requests = await sceneRoutes(page);
  await page.goto("/scenes/1");
  await page.getByText("Add or replace a local meaning question", { exact: true }).click();
  await page.getByRole("textbox", { name: "Question prompt", exact: true }).fill("Which action does this scene describe?");
  await page.getByRole("textbox", { name: "Choice 1", exact: true }).fill("Studying");
  await page.getByRole("textbox", { name: "Choice 2", exact: true }).fill("Sleeping");
  await page.getByRole("textbox", { name: "Explanation for choice 1", exact: true }).fill("It describes studying.");
  await page.getByRole("textbox", { name: "Explanation for choice 2", exact: true }).fill("There is no sleeping in this line.");
  await page.getByRole("radio", { name: "Choice 1", exact: true }).check();
  await expect(page.getByRole("button", { name: "Save reviewed question" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /I checked the source/ }).check();
  await page.getByRole("button", { name: "Save reviewed question" }).click();
  await page.getByRole("button", { name: "Continue: Clarify", exact: true }).click();
  await page.getByRole("button", { name: "Continue: Less support", exact: true }).click();
  await page.getByRole("button", { name: "Continue: Check meaning", exact: true }).click();
  await expect(page.getByText(/not externally validated/)).toBeVisible();
  await page.getByRole("radio", { name: "Sleeping", exact: true }).check();
  await page.getByRole("button", { name: "Check this answer", exact: true }).click();
  await expect(page.getByRole("region", { name: "Meaning answer feedback" })).toContainText("There is no sleeping");
  await page.getByText("Report an ambiguous or incorrect question", { exact: true }).click();
  await page.getByRole("textbox", { name: "Question issue", exact: true }).fill("This scene needs more context.");
  await page.getByRole("button", { name: "Report and suspend question", exact: true }).click();
  await expect(page.getByText("Report an ambiguous or incorrect question", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("earlier keyed results are excluded");
  await expect(page.getByRole("button", { name: "I need more support", exact: true })).toBeVisible();
  expect(requests.find((request) => request.path === "questions")?.body.reviewed).toBe(true);
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("scene-meaning-mobile.png"), fullPage: true });
});

test("changed source disables keyed grading and leaves honest reflection available", async ({ page }) => {
  await sceneRoutes(page, { stale: true });
  await page.goto("/scenes/1");
  await expect(page.getByRole("status")).toContainText("The source changed");
  await page.getByRole("radio", { name: "Study", exact: true }).check();
  await expect(page.getByRole("button", { name: "Check this answer", exact: true })).toBeDisabled();
  await expect(page.locator("video, audio")).toHaveCount(0);
  await page.getByRole("button", { name: "I need more support", exact: true }).click();
  await expect(page.getByText(/Reflection saved: you need more support/)).toBeVisible();
});

test("construction practice preserves retry identity, scopes feedback and suspends ambiguous tasks", async ({ page }, info) => {
  let suspended = false;
  const requests: Record<string, any>[] = [];
  await page.route("**/api/constructions**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/constructions") { await route.fulfill({ json: { version: "fixture-v1", items: [{ id: "ba-bei", title: "不 / 没: negation", note: "没…过 negates a prior experience.", suspended, examples: [{ zh: "他没去过北京。", en: "He has never been to Beijing." }, { zh: "他去过北京。", en: "He has been to Beijing." }], question: { category: "negation", passage: "他没去过北京。", prompt: "Which interpretation preserves negation?", choices: ["He has been to Beijing.", "He has never been to Beijing."] } }] } }); return; }
    if (path.endsWith("/examples")) { await route.fulfill({ json: { candidate_matches: true, items: [{ sentence_id: 3, item_id: 1, zh: "他没去过北京。", en: "He has never been to Beijing.", t0_ms: 0 }] } }); return; }
    if (path.endsWith("/answer")) { requests.push(route.request().postDataJSON()); await route.fulfill({ status: requests.length === 1 ? 503 : 200, json: { correct: true, answer: 1, choice: 1, explanations: ["This drops the negation.", "没…过 denies the prior experience."] } }); return; }
    if (path.endsWith("/report")) suspended = true;
    if (path.endsWith("/restore")) suspended = false;
    await route.fulfill({ json: { suspended } });
  });
  await page.goto("/practice");
  await page.getByRole("button", { name: "Find candidate examples in my library" }).click();
  await expect(page.getByText(/Candidate matches use written markers/)).toBeVisible();
  await page.getByRole("button", { name: "Use a meaning hint" }).click();
  await page.getByRole("radio", { name: "He has never been to Beijing.", exact: true }).check();
  await page.getByRole("button", { name: "Check interpretation", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("could not be confirmed");
  await page.getByRole("button", { name: "Retry same answer", exact: true }).click();
  await expect(page.getByRole("region", { name: "Construction answer feedback" })).toContainText("assisted construction practice");
  expect(requests[0]).toEqual(requests[1]);
  expect(requests[0].version).toBe("fixture-v1");
  await page.setViewportSize({ width: 390, height: 844 });
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo({ top: 0, behavior: "instant" }); });
  await page.screenshot({ path: info.outputPath("construction-practice-mobile.png"), fullPage: true });
  await page.getByText("Report ambiguity and suspend this exercise", { exact: true }).click();
  await page.getByRole("textbox", { name: "Exercise issue", exact: true }).fill("Needs more context.");
  await page.getByRole("button", { name: "Report and suspend exercise", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("exercise is suspended");
  await page.getByRole("checkbox", { name: "I reviewed the ambiguity and want to restore practice" }).check();
  await page.getByRole("button", { name: "Restore reviewed exercise", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Try the contrast", exact: true })).toBeVisible();
});

test("session mining starts with deliberate choices and retains failed saves", async ({ page }) => {
  let attempts = 0;
  await page.route("**/api/lexemes/2", async (route) => { await route.fulfill({ json: { lexeme_id: 2, simplified: "再", traditional: "再", pinyin: "zai4", senses: [{ py: "zai4", defs: ["again"] }], state: "new", state_source: null, saved_item_id: null, stats: { encounters: 1, lookups: 1, distinct_items: 1 } } }); });
  await page.route("**/api/saved-items", async (route) => { if (route.request().method() === "POST") { attempts++; await route.fulfill({ status: attempts === 1 ? 503 : 200, json: { id: 2, created: true } }); } else await route.fulfill({ json: { items: [] } }); });
  await page.goto("/watch/1");
  await page.locator('[data-sentence-id="1"]').last().getByRole("button", { name: "Look up 再", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Definition for 再" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "End session", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Session summary", exact: true });
  await expect(dialog.getByRole("checkbox")).not.toBeChecked();
  await expect(dialog.getByRole("button", { name: "Save 1 word", exact: true })).toHaveCount(0);
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Save 1 word", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Some words could not be saved");
  await expect(dialog.getByRole("checkbox")).toBeChecked();
  await dialog.getByRole("button", { name: "Save 1 word", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(attempts).toBe(2);
});

test("scene playback clamps seeking and records explicit replay without a seek loop", async ({ page }) => {
  const requests = await sceneRoutes(page);
  await page.goto("/scenes/1");
  const video = page.locator("video");
  await expect(video).toHaveJSProperty("readyState", 4);
  await video.evaluate((element: HTMLVideoElement) => { element.currentTime = 3.8; element.dispatchEvent(new Event("timeupdate")); });
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeLessThanOrEqual(3.53);
  await page.getByRole("button", { name: "Replay scene", exact: true }).click();
  await expect.poll(() => requests.some((request) => request.path === "hint" && request.body.kind === "replay")).toBe(true);
  await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.currentTime)).toBeLessThan(3.5);
});

test("saved-card suspension is reversible and keeps context and review progress", async ({ page }) => {
  let suspended = false;
  await page.route("**/api/saved-items**", async (route) => {
    if (route.request().method() === "PATCH") { suspended = route.request().postDataJSON().archived; await route.fulfill({ json: { ok: true } }); return; }
    const requested = new URL(route.request().url()).searchParams.get("archived") === "true";
    await route.fulfill({ json: { items: requested === suspended ? [{ id: 1, kind: "word", lexeme_id: 1, surface: "学习", selected_meaning: "to study", selected_reading: "xue2 xi2", note: null, tags: [], archived: suspended, created_at: "2026-10-18", anki_note_id: null, review: { rung: 1, passes: 2, fails: 0, graduated: false }, contexts: [{ sentence_id: 1, item_id: 1, item_title: "Study scene", zh: "学习，再学习。", en: "Study, then study again.", t0_ms: 0, t1_ms: 3500 }] }] : [] } });
  });
  await page.goto("/saved");
  await page.getByRole("button", { name: "Suspend 学习", exact: true }).click();
  await page.getByRole("button", { name: "Suspended cards", exact: true }).click();
  await expect(page.getByText("Review rung 2", { exact: true })).toBeVisible();
  await expect(page.getByText("to study", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Resume 学习", exact: true }).click();
  await page.getByRole("button", { name: "Active cards", exact: true }).click();
  await expect(page.getByRole("button", { name: "Suspend 学习", exact: true })).toBeVisible();
  await expect(page.getByText("Study, then study again.", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(result.violations.map(({ id }) => id)).toEqual([]);
});
