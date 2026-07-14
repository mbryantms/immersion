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
