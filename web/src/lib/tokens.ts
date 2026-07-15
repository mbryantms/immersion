// Word-token display helpers shared by subtitle overlay / transcript rows.

import type { Word } from "../api/types";

/** Drop leading/trailing whitespace-only tokens (SRT cues often carry
 *  trailing spaces that would otherwise render inside the subtitle pill).
 *  Interior spaces stay — they separate latin words. */
export function trimTokens(words: Word[]): Word[] {
  let start = 0;
  let end = words.length;
  while (start < end && words[start].type === "x" && !words[start].t.trim()) start++;
  while (end > start && words[end - 1].type === "x" && !words[end - 1].t.trim()) end--;
  return start === 0 && end === words.length ? words : words.slice(start, end);
}

// Fallback for fonts without the `halt` feature (PingFang/Kaiti on iOS —
// html.no-halt, set by a runtime measurement in lib/haltSupport.ts): trailing
// full-width punctuation still carries its designed-in em-box blank there, so
// the subtitle pill looks like it ends in a space. The last token gets a
// class; index.css compensates on the pill's padding, only under .no-halt.
const TRIM_FULL = /[。，、；：）」』”’〉》】]$/; // ink hugs the left edge → ~½em blank
const TRIM_HALF = /[！？]$/; // ink roughly centered → ~¼em blank

export function endPunctTrimClass(words: Word[]): string | null {
  const last = words[words.length - 1];
  if (!last || last.type !== "x") return null;
  if (TRIM_FULL.test(last.t)) return "end-trim-full";
  if (TRIM_HALF.test(last.t)) return "end-trim-half";
  return null;
}
