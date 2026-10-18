import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { scoreAttempt } from "../src/lib/dictation.ts";
import { textIsVisible, maskedParts } from "../src/player/studyMode.ts";

const fixtures = JSON.parse(readFileSync(new URL("../../server/tests/fixtures/dictation_cases.json", import.meta.url), "utf8"));
for (const fixture of fixtures) {
  test(`character accuracy: ${fixture.expected} / ${fixture.typed}`, () => {
    assert.equal(scoreAttempt(fixture.expected, fixture.typed).score, fixture.score);
  });
}
test("listening and dictation cannot expose text through ordinary display preferences", () => {
  assert.equal(textIsVisible("read"), true);
  assert.equal(textIsVisible("listen"), false);
  assert.equal(textIsVisible("listen", true), true);
  assert.equal(textIsVisible("dictate"), false);
  assert.equal(textIsVisible("dictate", true), false);
});
test("every repeated cloze occurrence is masked", () => {
  assert.deepEqual(maskedParts("学习，再学习。", "学习"), ["", "，再", "。"]);
  assert.deepEqual(maskedParts("你好。", ""), ["你好。"]);
});
