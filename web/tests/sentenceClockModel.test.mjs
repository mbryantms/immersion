import assert from "node:assert/strict";
import test from "node:test";

import {
  displayIndexAt,
  heardEnough,
  reachedTargetBoundary,
  targetIndexAt,
} from "../src/player/sentenceClockModel.ts";

const adjacent = [
  { id: 1, t0: 10_000, t1: 12_000 },
  { id: 2, t0: 12_000, t1: 14_000 },
];

test("a dropped frame cannot replace the playback boundary", () => {
  const target = adjacent[0];
  assert.equal(reachedTargetBoundary(target, 11_970), false);
  assert.equal(displayIndexAt(adjacent, 12_015), 1);
  assert.equal(reachedTargetBoundary(target, 12_015), true);
});

test("overlapping display cues do not replace the armed target", () => {
  const overlapping = [
    { id: 1, t0: 10_000, t1: 12_000 },
    { id: 2, t0: 11_800, t1: 13_500 },
  ];
  assert.equal(displayIndexAt(overlapping, 11_900), 1);
  assert.equal(reachedTargetBoundary(overlapping[0], 11_900), false);
  assert.equal(reachedTargetBoundary(overlapping[0], 12_010), true);
});

test("preroll targets the selected sentence rather than the preceding cue", () => {
  assert.equal(displayIndexAt(adjacent, 11_700), 0);
  const explicitlySelected = adjacent.findIndex((sentence) => sentence.id === 2);
  assert.equal(explicitlySelected, 1);
  assert.equal(reachedTargetBoundary(adjacent[explicitlySelected], 12_500), false);
});

test("resume advances to the first unfinished later sentence", () => {
  const malformed = [
    { id: 1, t0: 0, t1: 1_000 },
    { id: 2, t0: 900, t1: 1_000 },
    { id: 3, t0: 1_000, t1: 2_000 },
  ];
  assert.equal(targetIndexAt(malformed, 1_001, 1), 2);
});

test("free seeking selects the next unfinished sentence", () => {
  assert.equal(targetIndexAt(adjacent, 11_500), 0);
  assert.equal(targetIndexAt(adjacent, 12_500), 1);
  assert.equal(targetIndexAt(adjacent, 15_000), -1);
});

test("completion tracking distinguishes a full replay from a late seek", () => {
  const sentence = adjacent[0];
  assert.equal(heardEnough(sentence, sentence.t0), true);
  assert.equal(heardEnough(sentence, 10_600), true);
  assert.equal(heardEnough(sentence, 10_601), false);
  assert.equal(heardEnough(sentence, 11_500), false);
});
