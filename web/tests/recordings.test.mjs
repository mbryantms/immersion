import assert from "node:assert/strict";
import test from "node:test";
import { voiceKey } from "../src/guided/recordings.ts";

test("recordings bind to source snapshot identity rather than mutable scene progress", () => {
  const scene = { id: 1, item_id: 2, revision: 0, stage: "watch", snapshot: { fingerprint: "source", t0: 0, t1: 3000, lines: [{ id: 3, revision: 1, zh: "学习" }] } };
  const key = voiceKey(scene);
  assert.equal(voiceKey({ ...scene, revision: 20, stage: "clarify" }), key);
  for (const changed of [
    { ...scene, id: 2 }, { ...scene, item_id: 3 },
    { ...scene, snapshot: { ...scene.snapshot, fingerprint: "new file" } },
    { ...scene, snapshot: { ...scene.snapshot, t0: 100 } },
    { ...scene, snapshot: { ...scene.snapshot, lines: [{ id: 3, revision: 2, zh: "学习" }] } },
    { ...scene, snapshot: { ...scene.snapshot, lines: [{ id: 3, revision: 1, zh: "休息" }] } },
  ]) assert.notEqual(voiceKey(changed), key);
});
