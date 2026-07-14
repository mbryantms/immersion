import { memo } from "react";

import type { KnowledgeStateName, Word } from "../api/types";

interface TokenProps {
  word: Word;
  state: KnowledgeStateName;
  saved: boolean;
  traditional: boolean;
  showPinyin: boolean;
  onTap?: (word: Word) => void;
}

/** One tappable word: per-character tone colors + optional ruby pinyin.
 *  Non-zh tokens (latin, digits, punctuation) render as plain text. */
export const Token = memo(function Token({
  word,
  state,
  saved,
  traditional,
  showPinyin,
  onTap,
}: TokenProps) {
  if (word.type === "x") return <span className="x text-neutral-400">{word.t}</span>;

  const display = traditional && word.tr ? word.tr : word.t;
  const tones = word.tones ?? [];
  const py = word.py ?? [];
  const charwise = display.length === tones.length;

  const chars = charwise
    ? [...display].map((ch, i) => {
        const inner = <span className={`t${tones[i] ?? 5}`}>{ch}</span>;
        return showPinyin && py[i] ? (
          <ruby key={i}>
            {inner}
            <rt>{py[i]}</rt>
          </ruby>
        ) : (
          <span key={i}>{inner}</span>
        );
      })
    : [<span key="w" className={`t${tones[0] ?? 5}`}>{display}</span>];

  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={`Look up ${display}`}
      className={`w k-${state}${saved ? " saved" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onTap?.(word);
      }}
      onKeyDown={(e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        e.stopPropagation();
        onTap?.(word);
      }}
    >
      {chars}
    </span>
  );
});
