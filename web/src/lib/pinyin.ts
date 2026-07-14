// CEDICT-style numbered pinyin -> tone marks ("mo4 fang2" -> "mò fáng").
// Placement rules: a/e take the mark; in "ou" the o takes it; otherwise the
// last vowel. u: / v are ü. Tone 5 (neutral) carries no mark.

const MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à"],
  e: ["ē", "é", "ě", "è"],
  i: ["ī", "í", "ǐ", "ì"],
  o: ["ō", "ó", "ǒ", "ò"],
  u: ["ū", "ú", "ǔ", "ù"],
  ü: ["ǖ", "ǘ", "ǚ", "ǜ"],
};

function markSyllable(syllable: string): string {
  const m = syllable.match(/^([A-Za-zü:]+?)([1-5])$/);
  if (!m) return syllable; // not numbered pinyin — leave as-is
  let body = m[1].replace(/u:|v/g, "ü").replace(/U:|V/g, "Ü");
  const tone = Number(m[2]);
  if (tone === 5) return body;
  const lower = body.toLowerCase();
  let idx = -1;
  if (lower.includes("a")) idx = lower.indexOf("a");
  else if (lower.includes("e")) idx = lower.indexOf("e");
  else if (lower.includes("ou")) idx = lower.indexOf("o");
  else {
    for (let i = lower.length - 1; i >= 0; i--) {
      if ("iouü".includes(lower[i])) {
        idx = i;
        break;
      }
    }
  }
  if (idx < 0) return body;
  const ch = body[idx];
  const isUpper = ch !== ch.toLowerCase();
  const marked = MARKS[ch.toLowerCase()]?.[tone - 1];
  if (!marked) return body;
  return body.slice(0, idx) + (isUpper ? marked.toUpperCase() : marked) + body.slice(idx + 1);
}

export function numberedToMarks(pinyin: string): string {
  return pinyin
    .split(/\s+/)
    .map((s) => markSyllable(s))
    .join(" ");
}

/** Honor the display preference; input is CEDICT numbered pinyin. */
export function formatPinyin(pinyin: string | null | undefined, style: "marks" | "numbers"): string {
  if (!pinyin) return "";
  return style === "marks" ? numberedToMarks(pinyin) : pinyin;
}
