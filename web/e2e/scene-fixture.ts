import type { Page } from "@playwright/test";
import { words } from "./fixtures";

function freshScene() {
  return { id: 1, item_id: 1, goal: "listen", stage: "watch", revision: 0,
    snapshot: { title: "A little Mandarin every day", fingerprint: "test", kind: "video", t0: 0, t1: 3500, lines: [{ id: 1, zh: "学习，再学习。", en: "Study, then study again.", translation_source: "track", t0: 0, t1: 3500, revision: 0, words }] },
    support: {} as Record<string, unknown>, revisits: 0, due_at: null as string | null, completed_at: null as string | null,
    source_current: true, stream_url: "/media/fixture.mp4" as string | null, question: null as Record<string, unknown> | null };
}

export async function sceneRoutes(page: Page, options: { loseReply?: boolean; stale?: boolean; budgetZero?: boolean } = {}) {
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
