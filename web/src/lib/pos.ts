// ICTCLAS part-of-speech tags (jieba lexicon) -> reader-friendly labels.
// Unmapped tags fall back to the raw code.

const POS_LABELS: Record<string, string> = {
  n: "noun",
  nr: "name",
  ns: "place",
  nt: "organization",
  nz: "proper noun",
  ng: "noun morpheme",
  v: "verb",
  vd: "verb (adverbial)",
  vn: "verb-noun",
  vg: "verb morpheme",
  a: "adjective",
  ad: "adjective (adverbial)",
  an: "adjective-noun",
  ag: "adj. morpheme",
  d: "adverb",
  m: "numeral",
  mq: "numeral-classifier",
  q: "measure word",
  r: "pronoun",
  c: "conjunction",
  p: "preposition",
  u: "particle",
  uj: "particle 的",
  ul: "particle 了",
  t: "time word",
  f: "locative",
  s: "place word",
  i: "idiom",
  l: "set phrase",
  j: "abbreviation",
  o: "onomatopoeia",
  e: "interjection",
  y: "modal particle",
  b: "attributive",
  z: "descriptive",
  zg: "descriptive",
  x: "non-word",
  eng: "loanword",
};

export function posLabel(tag: string | null | undefined): string | null {
  if (!tag) return null;
  return POS_LABELS[tag] ?? POS_LABELS[tag[0]] ?? tag;
}

/** Frequency band for a rank: readable at a glance, exact rank in the title. */
export function freqBand(rank: number | null | undefined): string | null {
  if (!rank) return null;
  if (rank <= 1000) return "Top 1k";
  if (rank <= 5000) return "Top 5k";
  if (rank <= 20000) return "Top 20k";
  if (rank <= 60000) return "Top 60k";
  return "Rare";
}
