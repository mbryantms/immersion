import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect, words } from "./fixtures";

function freshScene() {
  return { id: 1, item_id: 1, goal: "listen", stage: "watch", revision: 0,
    snapshot: { title: "A little Mandarin every day", fingerprint: "test", kind: "video", t0: 0, t1: 3500, lines: [{ id: 1, zh: "学习，再学习。", en: "Study, then study again.", translation_source: "track", t0: 0, t1: 3500, revision: 0, words }] },
    support: {} as Record<string, unknown>, revisits: 0, due_at: null as string | null, completed_at: null as string | null,
    source_current: true, stream_url: "/media/fixture.mp4" as string | null, question: null as Record<string, unknown> | null };
}

async function sceneRoutes(page: Page, options: { loseReply?: boolean; stale?: boolean; budgetZero?: boolean } = {}) {
  let scene = freshScene();
  if (options.stale) { scene.stage = "check"; scene.source_current = false; scene.stream_url = null; scene.question = { id: 1, revision: 1, prompt: "What is happening?", passage: "学习，再学习。", choices: ["Study", "Sleep"], provenance: "learner_authored_reviewed", externally_validated: false }; }
  const requests: { path: string; body: Record<string, any> }[] = [];
  const replies = new Map<string, typeof scene>();
  let lost = false;
  let saved = false;
  await page.route("**/api/items/1/scenes", async (route) => { requests.push({ path: "create", body: route.request().postDataJSON() }); await route.fulfill({ json: scene }); });
  await page.route("**/api/scenes/1**", async (route) => {
    const path = new URL(route.request().url()).pathname.split("/").at(-1)!;
    if (path === "vocabulary") { await route.fulfill({ json: { items: [{ lexeme_id: 1, simplified: "学习", surface: "学习", sentence_id: 1, occurrences: 2, senses: [{ py: "xue2 xi2", defs: ["to study", "to learn"] }], state: "learning", state_source: "derived", saved_item_id: saved ? 1 : null }], suggested_max: options.budgetZero ? 0 : 3, source_current: true } }); return; }
    if (route.request().method() === "GET") { await route.fulfill({ json: scene }); return; }
    const body = route.request().postDataJSON(); requests.push({ path, body });
    const cacheKey = `${path}:${body.request_uuid}`;
    if (replies.has(cacheKey)) { await route.fulfill({ json: replies.get(cacheKey) }); return; }
    scene = { ...scene, revision: scene.revision+1, support: { ...scene.support } };
    if (path === "step") { scene.stage = body.stage; if (body.stage === "complete") { scene.due_at = "2099-10-19T10:00:00Z"; scene.completed_at = "2026-10-18T10:00:00Z"; } }
    if (path === "hint") scene.support[`${scene.stage}_${body.kind}`] = 1;
    if (path === "reflection") { scene.support.checked = true; scene.support.reflection = body.understood; }
    if (path === "questions") { scene.question = { id: 1, revision: scene.revision, prompt: body.question.prompt, passage: body.question.passage, category: body.question.category, choices: body.question.choices.map((choice: any) => choice.text), provenance: "learner_authored_reviewed", externally_validated: false }; scene.support.authored_answer_seen = true; }
    if (path === "answer") { scene.support.checked = true; scene.support.answer_feedback = { correct: body.choice === 0, answer: 0, choice: body.choice, explanations: ["It describes studying.", "There is no sleeping in this line."], provenance: "learner_authored_reviewed" }; }
    if (path === "report-question") { scene.question = null; scene.support.checked = false; scene.support.question_reported = 1; }
    replies.set(cacheKey, scene);
    if (options.loseReply && !lost && path === "step" && body.stage === "reduce") { lost = true; await route.fulfill({ status: 503, json: { detail: "Lost response" } }); return; }
    await route.fulfill({ json: scene });
  });
  await page.route("**/api/mining/budget", async (route) => { await route.fulfill({ json: { daily_word_budget: options.budgetZero ? 0 : 5, used: saved ? 1 : 0, remaining: options.budgetZero ? 0 : 5, timezone: "UTC", soft_limit: true } }); });
  await page.route("**/api/saved-items", async (route) => { if (route.request().method() === "POST") { saved = true; requests.push({ path: "save", body: route.request().postDataJSON() }); } await route.fulfill({ json: { id: 1, created: true, items: [] } }); });
  return requests;
}

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
