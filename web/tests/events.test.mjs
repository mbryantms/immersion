import assert from "node:assert/strict";
import test from "node:test";

function setup() {
  const entries = new Map();
  const scheduled = new Map();
  let nextTimer = 0;
  globalThis.localStorage = {
    get length() { return entries.size; },
    key: (index) => [...entries.keys()][index] ?? null,
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key),
  };
  globalThis.document = { visibilityState: "visible", addEventListener() {} };
  globalThis.window = { setTimeout: (fn) => { scheduled.set(++nextTimer, fn); return nextTimer; }, addEventListener() {} };
  globalThis.clearTimeout = (id) => scheduled.delete(id);
  Object.defineProperty(globalThis, "navigator", { value: { sendBeacon: () => false }, configurable: true });
  return { entries, scheduled };
}

test("failed HTTP requests retain UUIDs and retry; only acknowledged events are removed", async () => {
  const { entries, scheduled } = setup();
  let ok = false;
  const batches = [];
  globalThis.fetch = async (_url, init) => { batches.push(JSON.parse(init.body)); return { ok }; };
  const events = await import("../src/lib/events.ts?http");
  events.track("lookup", { lexeme_id: 7 });
  await events.flush();
  assert.equal(entries.size, 1);
  assert.ok(scheduled.size > 0);
  ok = true;
  await events.flush();
  assert.equal(entries.size, 0);
  assert.equal(batches[0][0].client_uuid, batches[1][0].client_uuid);
});

test("an accepted beacon is retained until normal acknowledgement", async () => {
  const { entries } = setup();
  let calls = 0;
  globalThis.fetch = async () => { calls++; return { ok: true }; };
  navigator.sendBeacon = () => true;
  document.visibilityState = "hidden";
  const events = await import("../src/lib/events.ts?beacon");
  events.track("sentence_played", { sentence_id: 1 });
  await events.flush();
  assert.equal(entries.size, 1);
  assert.equal(calls, 0);
  document.visibilityState = "visible";
  await events.flush();
  assert.equal(entries.size, 0);
});

test("refused beacons fall back to HTTP and reloads recover pending events", async () => {
  const { entries } = setup();
  globalThis.fetch = async () => ({ ok: false });
  document.visibilityState = "hidden";
  const first = await import("../src/lib/events.ts?before-reload");
  first.track("lookup", { lexeme_id: 3 });
  await first.flush();
  assert.equal(entries.size, 1);
  const second = await import("../src/lib/events.ts?after-reload");
  let delivered;
  document.visibilityState = "visible";
  globalThis.fetch = async (_url, init) => { delivered = JSON.parse(init.body); return { ok: true }; };
  await second.flush();
  assert.equal(delivered.length, 1);
  assert.equal(delivered[0].lexeme_id, 3);
  assert.equal(entries.size, 0);
});

test("events added while a request is in flight are not accidentally acknowledged", async () => {
  const { entries } = setup();
  let finish;
  globalThis.fetch = () => new Promise((resolve) => { finish = resolve; });
  const events = await import("../src/lib/events.ts?concurrent");
  events.track("lookup", { lexeme_id: 1 });
  const pending = events.flush();
  events.track("lookup", { lexeme_id: 2 });
  finish({ ok: true });
  await pending;
  assert.equal(entries.size, 1);
  assert.equal(JSON.parse([...entries.values()][0]).lexeme_id, 2);
});
