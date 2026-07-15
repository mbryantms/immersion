import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { get } from "../api/client";
import type { KnowledgeStateName, LexemeInfo, SentenceOut, Word } from "../api/types";
import { track } from "../lib/events";
import { formatPinyin } from "../lib/pinyin";
import { freqBand, posLabel } from "../lib/pos";
import { usePrefs } from "../lib/prefs";

export interface GlossTarget {
  sentence: SentenceOut;
  word?: Word; // token tap
  span?: string; // drag-selection lookup
  candidates?: LexemeInfo[]; // from POST /lookup
}

interface Props {
  target: GlossTarget;
  itemId: number;
  knowledge: Record<string, KnowledgeStateName>;
  savedLexemes: Set<number>;
  onClose: () => void;
  onResume: () => void;
  onSaveWord: (lexemeId: number, surface: string, sentenceId: number) => void;
  onSaveSentence: (sentenceId: number) => void;
  onSetState: (lexemeId: number, state: KnowledgeStateName) => void;
}

function localInfo(word: Word, knowledge: Record<string, KnowledgeStateName>): LexemeInfo {
  return {
    lexeme_id: word.lex ?? -1,
    simplified: word.t,
    traditional: word.tr ?? null,
    pinyin: null,
    hsk: null,
    is_dict: !!word.gloss,
    senses: (word.gloss ?? []).map((g) => ({ py: g.py, trad: null, defs: g.defs })),
    state: (word.lex && knowledge[word.lex]) || "new",
    state_source: null,
    saved_item_id: null,
  };
}

const stateLabel: Record<KnowledgeStateName, string> = {
  new: "New",
  learning: "Learning",
  familiar: "Familiar",
  known: "Known",
  ignored: "Ignored",
};

const stateDot: Record<KnowledgeStateName, string> = {
  new: "bg-sky-400",
  learning: "bg-amber-400",
  familiar: "bg-teal-400",
  known: "bg-emerald-400",
  ignored: "bg-stone-500",
};

export default function GlossSheet({
  target,
  itemId,
  knowledge,
  savedLexemes,
  onClose,
  onResume,
  onSaveWord,
  onSaveSentence,
  onSetState,
}: Props) {
  const initial = target.candidates ?? (target.word ? [localInfo(target.word, knowledge)] : []);
  const [candidates, setCandidates] = useState<LexemeInfo[]>(initial);
  const [pick, setPick] = useState(0);
  const dialogRef = useRef<HTMLElement>(null);
  const pinyinStyle = usePrefs((p) => p.pinyinStyle);

  useEffect(() => {
    dialogRef.current?.focus({ preventScroll: true });
  }, []);

  // enrich the instant local gloss with full senses / traditional / HSK / stats
  useEffect(() => {
    setCandidates(initial);
    setPick(0);
    const lex = target.candidates ? null : target.word?.lex;
    if (lex) {
      track("lookup", { item_id: itemId, sentence_id: target.sentence.id, lexeme_id: lex });
      get<LexemeInfo>(`/lexemes/${lex}`)
        .then((info) => setCandidates([info]))
        .catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  const c = candidates[pick];
  if (!c) return null;
  const state = (c.lexeme_id > 0 && knowledge[c.lexeme_id]) || c.state;
  const saved = c.lexeme_id > 0 && savedLexemes.has(c.lexeme_id);

  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-end justify-center p-3 sm:p-5">
      <button
        type="button"
        className="pointer-events-auto absolute inset-0 cursor-default bg-black/20 backdrop-blur-[1px]"
        onClick={onClose}
        aria-label="Close definition and remain paused"
        tabIndex={-1}
      />
      <div className="absolute bottom-0 left-1/2 h-48 w-[min(90vw,760px)] -translate-x-1/2 rounded-full bg-teal-500/8 blur-3xl" />
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Definition for ${c.simplified}`}
        tabIndex={-1}
        className="gloss-popover pointer-events-auto relative flex max-h-[min(560px,calc(100vh-1.5rem))] w-full max-w-[720px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#131a17]/96 shadow-[0_24px_80px_rgba(0,0,0,.58)] backdrop-blur-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-white/10 sm:hidden" />

        <header className="relative shrink-0 border-b border-white/7 px-4 pb-4 pt-3 sm:px-5 sm:pt-5">
          <button
            onClick={onClose}
            className="absolute right-3 top-3 flex size-8 items-center justify-center rounded-full text-stone-500 transition hover:bg-white/7 hover:text-stone-100 focus-visible:outline-2 focus-visible:outline-teal-400"
            aria-label="Close definition"
            title="Close (Esc)"
          >
            <CloseIcon />
          </button>

          <div className="flex min-w-0 items-start gap-4 pr-9">
            <div className="flex min-h-14 min-w-14 max-w-36 shrink-0 items-center justify-center rounded-2xl border border-teal-300/10 bg-teal-400/8 px-3 shadow-inner shadow-teal-200/5 sm:min-h-16 sm:min-w-16">
              <span className={`font-zh font-medium text-stone-50 ${c.simplified.length > 3 ? "text-2xl" : "text-3xl sm:text-4xl"}`}>{c.simplified}</span>
            </div>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                {c.pinyin && <span className="text-lg font-medium tracking-wide text-teal-200">{formatPinyin(c.pinyin, pinyinStyle)}</span>}
                {c.traditional && c.traditional !== c.simplified && (
                  <span className="font-zh text-base text-stone-400">繁 {c.traditional}</span>
                )}
                {c.hsk && (
                  <span className="rounded-md border border-white/8 bg-white/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">HSK {c.hsk}</span>
                )}
                {posLabel(c.pos) && (
                  <span className="rounded-md border border-white/8 bg-white/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">{posLabel(c.pos)}</span>
                )}
                {freqBand(c.freq_rank) && (
                  <span title={`frequency rank #${c.freq_rank?.toLocaleString()}`} className="rounded-md border border-white/8 bg-white/5 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">{freqBand(c.freq_rank)}</span>
                )}
                <span className="inline-flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-stone-500">
                  <i className={`size-1.5 rounded-full ${stateDot[state]}`} />
                  {stateLabel[state]}
                </span>
              </div>
              {c.stats ? (
                <p className="mt-2 text-[11px] text-stone-600">
                  Encountered <span className="text-stone-400">{c.stats.encounters}×</span>
                  <span className="mx-1.5 text-stone-700">·</span>
                  Looked up <span className="text-stone-400">{c.stats.lookups}×</span>
                </p>
              ) : (
                <p className="mt-2 text-[11px] text-stone-600">Tap words while watching to build learning history.</p>
              )}
            </div>
          </div>

          {candidates.length > 1 && (
            <div className="mt-3 flex items-center gap-1.5 overflow-x-auto pl-[4.5rem] sm:pl-20">
              <span className="mr-1 shrink-0 text-[10px] uppercase tracking-wider text-stone-600">Matches</span>
              {candidates.map((candidate, i) => (
                <button
                  key={`${candidate.lexeme_id}-${i}`}
                  onClick={() => setPick(i)}
                  className={`shrink-0 rounded-lg border px-2.5 py-1 font-zh text-sm transition ${i === pick ? "border-teal-400/25 bg-teal-400/10 text-teal-100" : "border-white/7 bg-white/[0.025] text-stone-400 hover:bg-white/6 hover:text-stone-100"}`}
                >
                  {candidate.simplified}
                </button>
              ))}
            </div>
          )}
        </header>

        <div className="flex shrink-0 items-center gap-3 border-b border-teal-300/10 bg-teal-400/[0.055] px-4 py-2.5 text-xs text-teal-100/75 sm:px-5">
          <span className="flex min-w-0 flex-1 items-center gap-2"><PauseIcon />Playback paused for lookup</span>
          <button type="button" onClick={onResume} className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-teal-400 px-3 text-[11px] font-semibold text-teal-950 transition hover:bg-teal-300">
            <PlayIcon /> Resume <span className="hidden text-teal-900/60 sm:inline">· Space</span>
          </button>
        </div>

        <div className="transcript-scroll min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          <div className="space-y-2.5">
            {c.senses.slice(0, 6).map((sense, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-white/5 text-[10px] tabular-nums text-stone-600">{i + 1}</span>
                <p className="min-w-0 text-[13px] leading-relaxed text-stone-200 sm:text-sm">
                  {sense.py && sense.py !== c.pinyin && <span className="mr-2 font-medium text-teal-300/75">{formatPinyin(sense.py, pinyinStyle)}</span>}
                  {sense.defs.join(" · ")}
                </p>
              </div>
            ))}
            {!c.senses.length && (
              <div className="rounded-xl border border-dashed border-white/8 px-4 py-5 text-center">
                <p className="text-sm text-stone-400">No dictionary definition available.</p>
                <p className="mt-1 text-xs text-stone-600">This may be a name or an out-of-vocabulary expression.</p>
              </div>
            )}
          </div>

          <div className="mt-4 rounded-xl border border-white/7 bg-black/15 px-3.5 py-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-stone-600">
              <ContextIcon /> In this sentence
            </div>
            <p className="font-zh text-base leading-relaxed text-stone-200">{target.sentence.zh}</p>
            {target.sentence.en && <p className="mt-1 text-xs leading-relaxed text-stone-500">{target.sentence.en}</p>}
          </div>
        </div>

        <footer className="flex shrink-0 flex-wrap items-center gap-2 border-t border-white/7 bg-black/10 px-4 py-3 sm:px-5">
          {c.lexeme_id > 0 && (
            <>
              <button
                onClick={() => onSaveWord(c.lexeme_id, c.simplified, target.sentence.id)}
                className={`gloss-action-primary ${saved ? "is-saved" : ""}`}
              >
                <BookmarkIcon filled={saved} />
                {saved ? "Saved · add context" : "Save word"}
              </button>
              <button
                onClick={() => onSetState(c.lexeme_id, state === "known" ? "new" : "known")}
                className={`gloss-action ${state === "known" ? "is-active" : ""}`}
              >
                <CheckIcon /> {state === "known" ? "Known" : "Mark known"}
              </button>
              <button
                onClick={() => onSetState(c.lexeme_id, state === "ignored" ? "new" : "ignored")}
                className={`gloss-action ${state === "ignored" ? "is-active-muted" : ""}`}
              >
                <IgnoreIcon /> {state === "ignored" ? "Ignored" : "Ignore"}
              </button>
            </>
          )}
          <button
            onClick={() => onSaveSentence(target.sentence.id)}
            className="gloss-action sm:ml-auto"
          >
            <SentenceIcon /> Save sentence
          </button>
          {c.lexeme_id > 0 && (
            <Link to={`/word/${c.lexeme_id}`} onClick={onClose} className="gloss-action" title="Strokes, examples, concordance">
              <WordPageIcon /> Word page
            </Link>
          )}
        </footer>
      </section>
    </div>
  );
}

function CloseIcon() {
  return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" className="size-4" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg>;
}

function PauseIcon() {
  return <svg viewBox="0 0 18 18" fill="currentColor" className="size-3.5 shrink-0" aria-hidden="true"><path d="M4.5 3.5h3v11h-3zM10.5 3.5h3v11h-3z" /></svg>;
}

function PlayIcon() {
  return <svg viewBox="0 0 18 18" fill="currentColor" className="size-3.5" aria-hidden="true"><path d="m5.5 3.5 9 5.5-9 5.5v-11Z" /></svg>;
}

function ContextIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" className="size-3.5" aria-hidden="true"><path d="M3 4h12v8H8l-3.5 2.5V12H3V4Z" /></svg>;
}

function BookmarkIcon({ filled = false }: { filled?: boolean }) {
  return <svg viewBox="0 0 18 18" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.5" className="size-4" aria-hidden="true"><path d="M5 2.5h8v13l-4-2.7L5 15.5v-13Z" /></svg>;
}

function CheckIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="size-4" aria-hidden="true"><path d="m4 9.5 3 3L14 5.5" /></svg>;
}

function IgnoreIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-4" aria-hidden="true"><circle cx="9" cy="9" r="6" /><path d="m5 13 8-8" /></svg>;
}

function WordPageIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-4" aria-hidden="true"><path d="M4 3h10v12H4z" /><path d="M6.5 6.5h5M6.5 9h5M6.5 11.5h3" /></svg>;
}

function SentenceIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="size-4" aria-hidden="true"><path d="M3.5 4.5h11M3.5 8.5h11M3.5 12.5h7" /><path d="M13.5 11v5M11 13.5h5" /></svg>;
}
