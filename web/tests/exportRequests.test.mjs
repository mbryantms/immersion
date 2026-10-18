import assert from "node:assert/strict";
import test, { afterEach } from "node:test";
const originalStorage = globalThis.localStorage;
afterEach(() => { if (originalStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = originalStorage; });
import { pendingExports, rememberExport, forgetExport } from "../src/saved/exportRequests.ts";

class Storage {
  values = new Map();
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}
const request = (suffix) => ({ request_uuid: `00000000-0000-4000-8000-00000000000${suffix}`, profile_hash: "a".repeat(64), created_at: "2026-10-18T00:00:00Z", entries: [{ saved_item_id: 1, source_hash: "b".repeat(64), meaning: "a selected meaning", include_media: false }] });
test("ambiguous export submissions retain exact independent UUID/payloads until acknowledged", () => {
  globalThis.localStorage = new Storage();
  localStorage.setItem("unrelated-preference", "keep");
  rememberExport(request(1)); rememberExport(request(2));
  assert.deepEqual(pendingExports(), [request(1), request(2)]);
  forgetExport(request(1).request_uuid);
  assert.deepEqual(pendingExports(), [request(2)]);
  assert.equal(localStorage.getItem("unrelated-preference"), "keep");
});
test("damaged submission reminders cannot become requests or hide valid reminders", () => {
  globalThis.localStorage = new Storage(); rememberExport(request(1));
  localStorage.setItem("anki-export-request-v1:broken", "{");
  rememberExport({ ...request(2), created_at: "bad date" });
  assert.deepEqual(pendingExports(), [request(1)]);
});
test("a quota failure is visible before the export request can be sent", () => {
  globalThis.localStorage = { setItem: () => { throw new Error("quota"); } };
  assert.throws(() => rememberExport(request(1)), /quota/);
});
