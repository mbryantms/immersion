// Dictation practice (podcasts): listen per sentence, type what you hear,
// LCS-scored feedback. Answers stay hidden until a sentence is checked —
// this is listening practice, not copying. Ported from the podreader page.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { KnowledgeStateName, SentenceOut, Word } from "../api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Token } from "../gloss/Token";
import { PASS_SCORE, scoreAttempt, type DictationResult } from "../lib/dictation";
import { track } from "../lib/events";
import { trimTokens } from "../lib/tokens";
import type { MediaEl } from "./useSentenceClock";

interface Attempt {
  typed: string;
  checked: boolean;
  scriptPolicy?: "source" | "equivalent";
}

interface StoredAttempts {
  version: 2;
  attempts: Record<number, Attempt>;
}

interface Props {
  itemId: number;
  sentences: SentenceOut[];
  currentIdx: number;
  mediaRef: React.RefObject<MediaEl | null>;
  knowledge: Record<string, KnowledgeStateName>;
  savedLexemes: Set<number>;
  traditional: boolean;
  toneColors: boolean;
  onTapWord: (s: SentenceOut, w: Word) => void;
  onArmSentence: (s: SentenceOut) => void;
}

export default function DictationPanel({
  itemId,
  sentences,
  currentIdx,
  mediaRef,
  knowledge,
  savedLexemes,
  traditional,
  toneColors,
  onTapWord,
  onArmSentence,
}: Props) {
  const storageKey = `dict:${itemId}`;
  const [scriptPolicy, setScriptPolicy] = useState<"source" | "equivalent">("source");
  const [storageError, setStorageError] = useState(false);
  const [attempts, setAttempts] = useState<Record<number, Attempt>>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? "{}") as StoredAttempts | Record<number, Attempt>;
      if ("version" in stored && stored.version === 2) return stored.attempts;
      // One-time migration from the original ordinal-keyed format. Sentence
      // ids survive transcript reordering and enable a precise per-line reset.
      return Object.fromEntries(
        Object.entries(stored).flatMap(([ordinal, attempt]) => {
          const sentence = sentences[Number(ordinal)];
          return sentence ? [[sentence.id, attempt]] : [];
        }),
      );
    } catch {
      return {};
    }
  });
  const latestAttempts = useRef(attempts);
  latestAttempts.current = attempts;
  const persistAttempts = useCallback(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ version: 2, attempts: latestAttempts.current } satisfies StoredAttempts));
      setStorageError(false);
    } catch { setStorageError(true); }
  }, [storageKey]);
  useEffect(() => {
    const timer = window.setTimeout(persistAttempts, 400);
    return () => clearTimeout(timer);
  }, [attempts, persistAttempts]);
  useEffect(() => {
    const saveOnHide = () => { if (document.visibilityState === "hidden") persistAttempts(); };
    document.addEventListener("visibilitychange", saveOnHide);
    return () => {
      document.removeEventListener("visibilitychange", saveOnHide);
      try { localStorage.setItem(storageKey, JSON.stringify({ version: 2, attempts: latestAttempts.current } satisfies StoredAttempts)); } catch { /* retain in memory until unmount */ }
    };
  }, [persistAttempts, storageKey]);
  const scoreCache = useRef(new Map<number, { zh: string; typed: string; policy: string; result: DictationResult }>());
  const results = useMemo(() => {
    const out: Record<number, DictationResult> = {};
    for (const sentence of sentences) {
      const attempt = attempts[sentence.id];
      if (attempt?.checked) {
        let cached = scoreCache.current.get(sentence.id);
        if (!cached || cached.zh !== sentence.zh || cached.typed !== attempt.typed || cached.policy !== (attempt.scriptPolicy ?? "source")) {
          cached = { zh: sentence.zh, typed: attempt.typed, policy: attempt.scriptPolicy ?? "source", result: scoreAttempt(sentence.zh, attempt.typed, attempt.scriptPolicy === "equivalent" ? sentence.script_variants : {}) };
          scoreCache.current.set(sentence.id, cached);
        }
        out[sentence.id] = cached.result;
      }
    }
    return out;
  }, [attempts, sentences]);

  // per-sentence playback with a stop point at t1 (rAF; timeupdate is too coarse)
  const stopAtMs = useRef<number | null>(null);
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const media = mediaRef.current;
      if (media && stopAtMs.current !== null && media.currentTime * 1000 >= stopAtMs.current) {
        media.pause();
        stopAtMs.current = null;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [mediaRef]);

  const playSentence = useCallback(
    (s: SentenceOut) => {
      const media = mediaRef.current;
      if (!media) return;
      media.currentTime = s.t0 / 1000;
      onArmSentence(s);
      stopAtMs.current = s.t1;
      void media.play();
    },
    [mediaRef, onArmSentence],
  );

  const check = useCallback(
    (s: SentenceOut, ordinalKey: number) => {
      const a = attempts[ordinalKey];
      if (!a?.typed || a.checked) return;
      const result = scoreAttempt(s.zh, a.typed, scriptPolicy === "equivalent" ? s.script_variants : {});
      track("review_outcome", {
        item_id: itemId, sentence_id: s.id, study_mode: "dictation",
        data: { score: Math.round(result.score * 100), script_policy: scriptPolicy, task: "transcription" },
      });
      setAttempts((prev) => ({ ...prev, [ordinalKey]: { ...a, checked: true, scriptPolicy } }));
    },
    [itemId, attempts, scriptPolicy],
  );

  const done = Object.values(attempts).filter((a) => a.checked).length;

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#121816]">
      <div className="border-b border-white/7 px-4 pb-3 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-stone-100">Dictation</h2>
              <Badge variant="secondary" className="bg-white/6 text-[10px] font-medium text-stone-400">
                {done}/{sentences.length} checked
              </Badge>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-stone-400">Play a line, type what you hear, then press Enter.</p>
            <p className="mt-1 text-xs leading-relaxed text-stone-400">This measures transcription, not comprehension. Names and numbers count; punctuation and spaces are ignored.</p>
          </div>
          {done > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="text-xs text-stone-500 hover:text-stone-200"
              onClick={() => setAttempts({})}
            >
              Reset
            </Button>
          )}
        </div>
      </div>

      <label className="flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-3 text-xs text-stone-300">
        Character script
        <select value={scriptPolicy} onChange={(event) => setScriptPolicy(event.target.value as "source" | "equivalent")} className="min-h-11 rounded-md border border-white/20 bg-stone-900 px-2">
          <option value="source">Match source script</option>
          <option value="equivalent">Allow unambiguous simplified/traditional pairs</option>
        </select>
        <span>Ambiguous forms still require the source character. Checked attempts keep their original policy.</span>
      </label>
      {storageError && <p role="status" className="border-b border-border px-4 py-3 text-sm text-amber-200">This browser could not save your attempts. Keep this page open to retain them.</p>}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {sentences.map((s, idx) => {
          const attempt = attempts[s.id] ?? { typed: "", checked: false };
          const result: DictationResult | null = results[s.id] ?? null;
          const active = idx === currentIdx;
          return (
            <div
              key={s.id}
              data-sentence-id={s.id}
              className={`border-b border-white/[0.045] px-4 py-3 ${active ? "bg-teal-400/[0.04]" : ""}`}
            >
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="icon"
                  className="size-8 shrink-0 rounded-full bg-white/8 text-stone-200 hover:bg-teal-400/20"
                  onClick={() => playSentence(s)}
                  title={`Play sentence ${idx + 1}`}
                  aria-label={`Play sentence ${idx + 1}`}
                >
                  <PlayIcon />
                </Button>
                <span className="w-10 shrink-0 text-right text-[10px] tabular-nums text-stone-600">{fmt(s.t0)}</span>
                <Input
                  lang="zh-CN"
                  aria-label={`Dictation answer for sentence ${idx + 1}`}
                  maxLength={512}
                  autoComplete="off"
                  spellCheck={false}
                  value={attempt.typed}
                  onChange={(e) =>
                    setAttempts((prev) => ({ ...prev, [s.id]: { typed: e.target.value, checked: false } }))
                  }
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.nativeEvent.isComposing) check(s, s.id);
                    e.stopPropagation(); // keep player shortcuts out of the input
                  }}
                  placeholder="听写…"
                  className="h-11 border-white/10 bg-black/20 font-zh text-base text-stone-100 placeholder:text-stone-400"
                />
                {result ? (
                  <Badge
                    role="status"
                    aria-label={`${Math.round(result.score * 100)} percent character accuracy`}
                    className={
                      result.score >= PASS_SCORE
                        ? "bg-emerald-400/15 text-emerald-300"
                        : "bg-white/8 text-stone-300"
                    }
                  >
                    {Math.round(result.score * 100)}%
                  </Badge>
                ) : (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 shrink-0 text-stone-500 hover:text-teal-300"
                    onClick={() => check(s, s.id)}
                    disabled={!attempt.typed}
                    title="Check (Enter)"
                    aria-label="Check"
                  >
                    <CheckIcon />
                  </Button>
                )}
              </div>

              {result && (
                <div className="mt-2 pl-10">
                  <p className="font-zh text-base leading-relaxed">
                    {result.segments.map((seg, i) =>
                      seg.kind === "ok" ? (
                        <span key={i} className="text-stone-200">{seg.text}</span>
                      ) : seg.kind === "miss" ? (
                        <mark key={i} className="rounded bg-transparent px-0.5 text-red-400 underline decoration-red-400/60 underline-offset-4">
                          {seg.expected}
                          {seg.got && <span className="ml-0.5 align-super text-[10px] text-stone-500">{seg.got}</span>}
                        </mark>
                      ) : (
                        <span key={i} className="text-stone-600 line-through">{seg.text}</span>
                      ),
                    )}
                  </p>
                  <p className={`mt-1 font-zh text-[1.02rem] leading-[1.8] ${toneColors ? "tones" : ""}`}>
                    {trimTokens(s.words).map((w, i) => (
                      <Token
                        key={i}
                        word={w}
                        state={(w.lex && knowledge[w.lex]) || "new"}
                        saved={!!w.lex && savedLexemes.has(w.lex)}
                        traditional={traditional}
                        showPinyin={false}
                        onTap={(word) => onTapWord(s, word)}
                      />
                    ))}
                  </p>
                  {s.en && <p className="mt-0.5 text-[13px] text-stone-400">{s.en}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PlayIcon() {
  return <svg viewBox="0 0 24 24" fill="currentColor" className="ml-0.5 size-3.5" aria-hidden="true"><path d="M7.5 4.8v14.4L19 12 7.5 4.8Z" /></svg>;
}

function CheckIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-4" aria-hidden="true"><path d="m5 13 4.5 4.5L19 7" /></svg>;
}

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
