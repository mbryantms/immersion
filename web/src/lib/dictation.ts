// Dictation LCS scoring — kept in sync with server/src/app/lingua/diff.py
// (client-side for instant feedback; the server copy drives review scoring).
// Only CJK characters count: punctuation and spacing aren't listening skill.

const CJK = /[㐀-鿿]/;

export function normZh(text: string): string {
  return [...text].filter((ch) => CJK.test(ch)).join("");
}

export type DiffSegment =
  | { kind: "ok"; text: string }
  | { kind: "miss"; expected: string; got: string } // wrong/missing chars
  | { kind: "extra"; text: string }; // typed chars with no counterpart

export interface DictationResult {
  score: number; // matched / expected chars; 1 when nothing to hear
  segments: DiffSegment[];
}

export const PASS_SCORE = 0.95;

type Op = ["eq" | "del" | "ins", string];

function lcsOps(a: string, b: string): Op[] {
  const n = a.length;
  const m = b.length;
  const table = new Uint16Array((n + 1) * (m + 1));
  const at = (i: number, j: number) => table[i * (m + 1) + j];
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      table[i * (m + 1) + j] =
        a[i] === b[j] ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
    }
  }
  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      ops.push(["eq", a[i]]);
      i++;
      j++;
    } else if (at(i + 1, j) >= at(i, j + 1)) {
      ops.push(["del", a[i]]);
      i++;
    } else {
      ops.push(["ins", b[j]]);
      j++;
    }
  }
  for (; i < n; i++) ops.push(["del", a[i]]);
  for (; j < m; j++) ops.push(["ins", b[j]]);
  return ops;
}

/** Runs of del/ins collapse into one miss (expected + what was typed);
 *  leading/trailing pure insertions render as struck-through extras. */
export function scoreAttempt(expectedZh: string, typed: string): DictationResult {
  const expected = normZh(expectedZh);
  const typedN = normZh(typed);
  if (!expected) return { score: 1, segments: [] };

  const ops = lcsOps(expected, typedN);
  const segments: DiffSegment[] = [];
  let ok = 0;
  let idx = 0;
  while (idx < ops.length) {
    const [op, ch] = ops[idx];
    if (op === "eq") {
      ok++;
      const last = segments[segments.length - 1];
      if (last?.kind === "ok") last.text += ch;
      else segments.push({ kind: "ok", text: ch });
      idx++;
      continue;
    }
    // group a run of del/ins
    let dels = "";
    let inss = "";
    while (idx < ops.length && ops[idx][0] !== "eq") {
      if (ops[idx][0] === "del") dels += ops[idx][1];
      else inss += ops[idx][1];
      idx++;
    }
    if (dels) segments.push({ kind: "miss", expected: dels, got: inss });
    else segments.push({ kind: "extra", text: inss });
  }
  return { score: ok / expected.length, segments };
}
