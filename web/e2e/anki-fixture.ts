import type { Page } from "@playwright/test";
import type { AnkiProfile, ExportBatch } from "../src/anki-types";
export const profile: AnkiProfile = { deck: "Mandarin", model: "Local Mandarin", fields: { ID: "Key", Simplified: "Hanzi", Pinyin: "Reading", Meaning: "Gloss", Sentence: "Context", SentenceMeaning: "ContextMeaning", SentenceAudio: "SourceAudio" }, templates_reviewed: true, word_tts: false };
export const fields = { ID: "study", Simplified: "学习", Traditional: "學習", Pinyin: "xué xí", Meaning: "to study", Sentence: "学习，再学习。", SentenceMeaning: "Study, then study again." };
export async function ankiRoutes(page: Page, options: { lost?: boolean; missing?: boolean; duplicate?: boolean } = {}) {
  const state = { profile: structuredClone(profile), deferred: false, requests: [] as Record<string, any>[], batches: [] as ExportBatch[], noteExists: false, reconciles: 0, submitted: 0, offline: false, profileWrites: [] as AnkiProfile[] };
  const accepted = new Map<string, number>(); let lost = false;
  await page.route("**/api/anki/**", async (route) => {
    const url = new URL(route.request().url()); const path = url.pathname.replace("/api/anki", ""); const method = route.request().method();
    const body = method === "POST" || method === "PUT" ? route.request().postDataJSON() : null;
    const reply = async (json: unknown, status = 200) => route.fulfill({ status, json });
    if (path === "/export-profile") {
      if (method === "PUT") { state.profile = body; state.profileWrites.push(body); }
      return reply({ profile: state.profile, profile_hash: "a".repeat(64) });
    }
    if (path === "/preflight") {
      if (state.offline) return reply({ detail: "AnkiConnect is unavailable" }, 503);
      const errors = body.templates_reviewed ? [] : ["Review the note type's card fronts and backs in Anki."];
      return reply({ ok: !errors.length, errors, warnings: [], models: ["Local Mandarin", "Basic"], decks: ["Mandarin"], model_fields: body.model === "Basic" ? ["Front", "Back"] : ["Key", "Hanzi", "Reading", "Gloss", "Context", "ContextMeaning", "SourceAudio"], profile_hash: "a".repeat(64) });
    }
    if (path === "/export-preview") {
      if (state.offline) return reply({ detail: "AnkiConnect is unavailable" }, 503);
      return reply({ deck: state.profile.deck, model: state.profile.model, profile_hash: "a".repeat(64), preflight: { ok: !options.missing, errors: options.missing ? ["Configured note type is missing. Open Settings."] : [], warnings: [], models: [], decks: [], model_fields: [] }, items: options.missing ? [] : [{ saved_item_id: 1, kind: "word", fields, source_hash: "b".repeat(64), errors: [], sentence_id: 1, can_clip: true, can_image: false, duplicates: options.duplicate ? 1 : 0, duplicate_meanings: options.duplicate ? ["existing study"] : [], already_exported: null }] });
    }
    if (path === "/export") {
      state.requests.push(body);
      let job = accepted.get(body.request_uuid);
      if (!job) {
        job = 10+state.batches.length; accepted.set(body.request_uuid, job); state.submitted++;
        state.batches.unshift({ job_id: job, status: "queued", items: [{ id: job, saved_item_id: 1, original_saved_item_id: 1, surface: "学习", fields: { ...fields, Meaning: body.entries[0].meaning }, profile: structuredClone(state.profile), status: "queued", note_id: null, error: null, warnings: [], export_tag: "immersion-id-fixture", created_at: "2026-10-18T00:00:00Z" }] });
      }
      if (options.lost && !lost) { lost = true; return reply({ detail: "Reply lost after acceptance" }, 503); }
      return reply({ queued: true, job_id: job });
    }
    if (path === "/inbox") {
      const exported = state.batches.some((batch) => batch.items.some((item) => item.status === "added"));
      const visible = !exported && (url.searchParams.get("view") === "deferred") === state.deferred;
      return reply({ counts: { ready: !exported && !state.deferred ? 1 : 0, deferred: !exported && state.deferred ? 1 : 0 }, next_cursor: null, items: visible ? [{ id: 1, surface: "学习", kind: "word", selected_reading: "xue2 xi2", selected_meaning: "to study", attempt_id: state.batches[0]?.items[0].id ?? null, export_status: state.batches[0]?.items[0].status ?? null }] : [] });
    }
    if (path === "/inbox/1") { state.deferred = body.deferred; return reply({ id: 1, deferred: state.deferred }); }
    if (path === "/exports") return reply({ batches: state.batches });
    if (path.startsWith("/exports/")) return reply(state.batches.find((batch) => batch.job_id === Number(path.split("/").at(-1))));
    if (path.endsWith("/reconcile")) {
      state.reconciles++;
      const item = state.batches.flatMap((batch) => batch.items).find((item) => item.id === Number(path.split("/")[2]))!;
      if (state.noteExists) { item.status = "added"; item.note_id = 800; item.error = null; }
      return reply(item);
    }
    if (path.endsWith("/retry")) { state.requests.push(body); return reply({ job_id: 11 }); }
    return reply({ detail: "Unexpected fixture request" }, 404);
  });
  return state;
}
