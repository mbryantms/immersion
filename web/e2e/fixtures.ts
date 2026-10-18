import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test as base } from "@playwright/test";

const video = readFileSync(fileURLToPath(new URL("./fixtures/study.mp4", import.meta.url)));
const image = '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#173c34"/></svg>';
export const words = [
  { t: "学习", start: 0, end: 2, reading: "xue2 xi2", type: "zh", lex: 1, py: ["xué", "xí"], tones: [2, 2], gloss: [{ py: "xue2 xi2", defs: ["to study", "to learn"] }] },
  { t: "，", start: 2, end: 3, type: "x" },
  { t: "再", start: 3, end: 4, type: "zh", lex: 2, py: ["zài"], tones: [4], gloss: [{ py: "zai4", defs: ["again"] }] },
  { t: "学习", start: 4, end: 6, reading: "xue2 xi2", type: "zh", lex: 1, py: ["xué", "xí"], tones: [2, 2], gloss: [{ py: "xue2 xi2", defs: ["to study"] }] },
  { t: "。", start: 6, end: 7, type: "x" },
];
const zh = "学习，再学习。";
const context = { sentence_id: 1, item_id: 1, item_kind: "video", item_available: true, stream_url: "/media/fixture.mp4", zh, en: "Study, then study again.", t0_ms: 0, t1_ms: 3500, words };
const item = { active_tracks: { zh: 1, en: null }, source_status: null, id: 1, title: "A little Mandarin every day", kind: "video", ordinal: 1, duration_ms: 4000, ready: true, available: true, width: 640, height: 360, series: { id: 1, title: "Everyday Mandarin", level: 2 }, stream_url: "/media/fixture.mp4", thumb_url: "/media/thumbs/1.jpg", tracks: [{ id: 1, lang: "zh", source: "sidecar", format: "srt", offset_ms: 0, selected: true, available: true, label: "Chinese.zh.srt" }], n_sentences: 1, progress: { position_ms: 0, completed: false, subtitle_mode: "zh" }, prev_item_id: null, next_item_id: 2, rewatch_nudge: false, coverage: 0.92, unknown_lexemes: 2 };
const series = { id: 1, root_id: 1, kind: "video", title: "Everyday Mandarin", level: 2, episodes: 2, ready: 2, coverage: 0.92, cover_url: "/media/thumbs/1.jpg" };
const lexeme = { lexeme_id: 1, simplified: "学习", traditional: "學習", pinyin: "xue2 xi2", hsk: 1, is_dict: true, senses: [{ py: "xue2 xi2", trad: "學習", defs: ["to study", "to learn"] }], state: "learning", state_source: "derived", saved_item_id: 1, stats: { encounters: 3, lookups: 1, distinct_items: 1, first_seen: null, last_seen: null } };

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.route("**/media/**", async (route) => {
      if (route.request().url().endsWith(".mp4")) await route.fulfill({ status: 200, contentType: "video/mp4", body: video });
      else await route.fulfill({ status: 200, contentType: "image/svg+xml", body: image });
    });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname.replace("/api", "");
      let payload: unknown = {};
      if (path === "/learner-profile") payload = { goal: "listen", level: "unknown", script: "source", interests: [] };
      else if (path === "/library") payload = { roots: [], series: [series], continue: [] };
      else if (path === "/stats/dashboard") payload = { weeks: [], totals: { lookups: 1, sentences_played: 3, saves: 1 }, recurring_unknowns: [], review_due: 1, graduated_waiting: 0, anki: { last_import: null, last_export: null } };
      else if (path === "/recommendations") payload = { band: { low: 0.88, high: 0.985 }, fallback: false, items: [{ item_id: 1, title: item.title, kind: "video", series_id: 1, series_title: series.title, duration_ms: 4000, thumb_url: item.thumb_url, coverage: 0.92, unknown_lexemes: 2 }] };
      else if (/^\/items\/\d+\/sentences$/.test(path)) payload = { item_id: Number(path.split("/")[2]), zh_offset_ms: 0, sentences: [{ id: 1, ord: 0, zh, tr: "學習，再學習。", t0: 0, t1: 3500, en: context.en, conf: 1, words, script_variants: { "學": "学", "習": "习" } }] };
      else if (/^\/items\/\d+$/.test(path)) payload = { ...item, id: Number(path.split("/")[2]), kind: path.endsWith("/2") ? "audio" : "video" };
      else if (path === "/knowledge") payload = { states: { 1: "learning", 2: "new" }, saved: [1] };
      else if (path === "/review/queue") payload = { due: 1, items: [{ saved_item_id: 1, kind: "word", surface: "学习", lexeme_id: 1, mode: "context", rung: 0, streak: 0, context, answer: { pinyin: "xue2 xi2", senses: lexeme.senses } }] };
      else if (/\/review\/\d+\/outcome$/.test(path)) payload = { result: "pass", rung: 0, graduated: false, already_in_anki: false, suggest_drop: false, next_due_days: 1 };
      else if (path === "/saved-items") payload = { items: [] };
      else if (path === "/jobs") payload = { jobs: [], active: false };
      else if (path === "/search") payload = { query: "学习", results: [{ ...context, item_title: item.title }] };
      else if (path === "/lexemes/1") payload = lexeme;
      else if (path.endsWith("/examples") || path.endsWith("/concordance")) payload = { results: [] };
      else if (path === "/dictionaries") payload = { dictionaries: [{ name: "CC-CEDICT", entries: 100, source: "CC-CEDICT" }], lexemes: 100, oov_lexemes: 0 };
      else if (path === "/series/1") payload = { id: 1, title: series.title, level: 2, items: [{ ...item, has_zh: true, position_ms: 0, completed: false }] };
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    });
    await use(page);
  },
});
export { expect } from "@playwright/test";
