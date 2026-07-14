export interface TimedSentence {
  id: number;
  t0: number;
  t1: number;
}

/** Last sentence that has started at `ms`; used only for the visual clock. */
export function displayIndexAt(sentences: TimedSentence[], ms: number): number {
  let lo = 0;
  let hi = sentences.length - 1;
  let current = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (sentences[mid].t0 <= ms) {
      current = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return current;
}

/** Sentence whose end should be observed next at this playback position. */
export function targetIndexAt(sentences: TimedSentence[], ms: number, from = 0): number {
  for (let i = Math.max(0, from); i < sentences.length; i += 1) {
    if (sentences[i].t1 > ms) return i;
  }
  return -1;
}

/** Boundary detection is independent of whichever cue is currently displayed. */
export function reachedTargetBoundary(sentence: TimedSentence, ms: number): boolean {
  return ms >= sentence.t1;
}

/** A pass counts as an encounter only after most of the sentence was heard. */
export function heardEnough(sentence: TimedSentence, heardFromMs: number, threshold = 0.7): boolean {
  const duration = sentence.t1 - sentence.t0;
  const heard = sentence.t1 - Math.max(sentence.t0, heardFromMs);
  return duration > 0 && heard >= threshold * duration;
}
