import type { KnowledgeStateName, SentenceOut, Word } from "../api/types";
import { Token } from "../gloss/Token";
import type { SubtitleMode } from "../lib/prefs";
import { trimTokens } from "../lib/tokens";

interface Props {
  sentence: SentenceOut | null;
  visible: boolean;
  mode: SubtitleMode;
  knowledge: Record<string, KnowledgeStateName>;
  savedLexemes: Set<number>;
  traditional: boolean;
  toneColors: boolean;
  fontScale: number;
  showPinyin: (sentenceId: number, wordIdx: number) => boolean;
  enRevealed: boolean;
  onTapWord: (sentence: SentenceOut, word: Word) => void;
}

export default function SubtitleOverlay({
  sentence,
  visible,
  mode,
  knowledge,
  savedLexemes,
  traditional,
  toneColors,
  fontScale,
  showPinyin,
  enRevealed,
  onTapWord,
}: Props) {
  if (!sentence || !visible || mode === "off") return null;
  const words = trimTokens(sentence.words);
  const showEn = (mode === "dual" || enRevealed) && sentence.en;
  const scale = Math.max(0.75, Math.min(1.5, fontScale));
  const chineseSize = `clamp(${1.125 * scale}rem, calc(${0.8 * scale}rem + ${1.45 * scale}cqi), ${2 * scale}rem)`;
  const englishSize = `clamp(${0.75 * scale}rem, calc(${0.64 * scale}rem + ${0.5 * scale}cqi), ${1 * scale}rem)`;

  return (
    <div className="subtitle-stack pointer-events-none absolute inset-x-0 flex flex-col items-center">
      <p
        key={`zh-${sentence.id}`}
        lang="zh-CN"
        aria-label={sentence.zh}
        className={`subtitle-primary pointer-events-auto font-zh ${toneColors ? "tones" : ""}`}
        style={{ fontSize: chineseSize }}
        data-sentence-id={sentence.id}
      >
        {words.map((w, i) => (
          <Token
            key={i}
            word={w}
            state={(w.lex && knowledge[w.lex]) || "new"}
            saved={!!w.lex && savedLexemes.has(w.lex)}
            traditional={traditional}
            showPinyin={showPinyin(sentence.id, i)}
            onTap={(word) => onTapWord(sentence, word)}
          />
        ))}
      </p>
      {showEn && (
        <p
          key={`en-${sentence.id}`}
          lang="en"
          className="subtitle-translation pointer-events-auto"
          style={{ fontSize: englishSize }}
        >
          {sentence.en}
        </p>
      )}
    </div>
  );
}
