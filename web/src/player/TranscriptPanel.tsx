import { useVirtualizer } from "@tanstack/react-virtual";
import { Type } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import type { KnowledgeStateName, SentenceOut, Word } from "../api/types";
import { Token } from "../gloss/Token";
import { trimTokens } from "../lib/tokens";

interface Props {
  sentences: SentenceOut[];
  currentIdx: number;
  knowledge: Record<string, KnowledgeStateName>;
  savedLexemes: Set<number>;
  traditional: boolean;
  toneColors: boolean;
  fontScale: number;
  showEn: (s: SentenceOut) => boolean;
  showPinyin: (sentenceId: number, wordIdx: number) => boolean;
  onSeek: (s: SentenceOut) => void;
  onTapWord: (s: SentenceOut, w: Word) => void;
  onRevealEn: (s: SentenceOut) => void;
  onFontScaleChange: (scale: number) => void;
}

export default function TranscriptPanel({
  sentences,
  currentIdx,
  knowledge,
  savedLexemes,
  traditional,
  toneColors,
  fontScale,
  showEn,
  showPinyin,
  onSeek,
  onTapWord,
  onRevealEn,
  onFontScaleChange,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const [isFollowing, setIsFollowing] = useState(true);
  const [query, setQuery] = useState("");
  const transcriptScale = Math.max(0.85, Math.min(1.6, fontScale));

  const rows = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return sentences
      .map((sentence, originalIdx) => ({ sentence, originalIdx }))
      .filter(({ sentence }) => !normalized || sentence.zh.includes(normalized) || sentence.en?.toLocaleLowerCase().includes(normalized));
  }, [query, sentences]);

  const activeRow = rows.findIndex(({ originalIdx }) => originalIdx === currentIdx);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => Math.round(102 * Math.max(1, transcriptScale)),
    overscan: 8,
  });

  useEffect(() => {
    virtualizer.measure();
  }, [transcriptScale, virtualizer]);

  useEffect(() => {
    if (activeRow >= 0 && follow.current && !query) {
      virtualizer.scrollToIndex(activeRow, { align: "center", behavior: "smooth" });
    }
  }, [activeRow, query, virtualizer]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#121816]">
      <div className="border-b border-white/7 px-4 pb-3 pt-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-stone-100">Interactive transcript</h2>
              <span className="rounded-full bg-white/6 px-2 py-0.5 text-[10px] font-medium text-stone-400">
                {sentences.length} lines
              </span>
            </div>
            <p className="mt-0.5 text-xs text-stone-500">Select any word to explore it</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 border border-white/8 bg-white/[0.025] px-2 text-stone-400 hover:bg-white/[0.06] hover:text-stone-100"
                  aria-label={`Transcript text size, ${Math.round(transcriptScale * 100)} percent`}
                  title="Adjust transcript text size"
                >
                  <Type className="size-3.5" />
                  <span className="hidden text-[10px] tabular-nums sm:inline">{Math.round(transcriptScale * 100)}%</span>
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" sideOffset={8} collisionPadding={12} className="w-64 border border-white/8 bg-[#18201d] p-4 shadow-2xl">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-stone-100">Transcript text</p>
                    <p className="mt-0.5 text-xs text-stone-500">Saved for every video</p>
                  </div>
                  <span className="rounded-md bg-white/6 px-2 py-1 text-xs font-medium tabular-nums text-teal-300">{Math.round(transcriptScale * 100)}%</span>
                </div>
                <div className="mt-4 flex items-center gap-3">
                  <span className="text-xs text-stone-500" aria-hidden="true">A</span>
                  <Slider
                    min={0.85}
                    max={1.6}
                    step={0.05}
                    value={[transcriptScale]}
                    onValueChange={([value]) => onFontScaleChange(value)}
                    aria-label="Transcript text size"
                  />
                  <span className="text-xl leading-none text-stone-300" aria-hidden="true">A</span>
                </div>
                <div className="mt-3 flex justify-between border-t border-white/7 pt-3">
                  <p className="text-[11px] text-stone-500">85–160%</p>
                  <Button variant="ghost" size="xs" disabled={transcriptScale === 1} onClick={() => onFontScaleChange(1)} className="text-stone-400">Reset</Button>
                </div>
              </PopoverContent>
            </Popover>
            <button
              type="button"
              onClick={() => {
                const next = !isFollowing;
                setIsFollowing(next);
                follow.current = next;
              }}
              className={`follow-toggle ${isFollowing ? "is-active" : ""}`}
              aria-pressed={isFollowing}
              title="Keep the active sentence in view"
            >
              <span className="follow-toggle-dot" />
              Follow
            </button>
          </div>
        </div>

        <label className="mt-3 flex h-9 items-center gap-2 rounded-lg border border-white/8 bg-black/15 px-3 text-stone-500 transition focus-within:border-teal-400/40 focus-within:bg-black/25 focus-within:text-stone-300">
          <SearchIcon />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search Chinese or English"
            className="min-w-0 flex-1 bg-transparent text-xs text-stone-200 outline-none placeholder:text-stone-600"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} className="rounded p-0.5 hover:bg-white/10" aria-label="Clear search">
              <CloseIcon />
            </button>
          )}
        </label>
      </div>

      <div ref={parentRef} className="transcript-scroll min-h-0 flex-1 overflow-y-auto">
        {rows.length ? (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
            {virtualizer.getVirtualItems().map((row) => {
              const { sentence: s, originalIdx } = rows[row.index];
              const active = originalIdx === currentIdx;
              return (
                <div
                  key={s.id}
                  data-index={row.index}
                  data-sentence-id={s.id}
                  ref={virtualizer.measureElement}
                  className={`transcript-row group absolute inset-x-0 border-b border-white/[0.045] px-4 py-3 transition-colors ${active ? "is-active" : "hover:bg-white/[0.025]"}`}
                  style={{ transform: `translateY(${row.start}px)` }}
                >
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => onSeek(s)}
                      title="Play from here"
                      className={`mt-1 flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-[10px] tabular-nums transition ${active ? "bg-teal-400/12 text-teal-300" : "text-stone-600 hover:bg-white/5 hover:text-teal-300"}`}
                    >
                      {active && <span className="playing-bars"><i /><i /><i /></span>}
                      {fmt(s.t0)}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p
                        className={`font-zh leading-[1.8] text-stone-100 ${toneColors ? "tones" : ""}`}
                        style={{ fontSize: `${1.08 * transcriptScale}rem` }}
                      >
                        {trimTokens(s.words).map((w, i) => (
                          <Token
                            key={i}
                            word={w}
                            state={(w.lex && knowledge[w.lex]) || "new"}
                            saved={!!w.lex && savedLexemes.has(w.lex)}
                            traditional={traditional}
                            showPinyin={showPinyin(s.id, i)}
                            onTap={(word) => onTapWord(s, word)}
                          />
                        ))}
                      </p>
                      {s.en &&
                        (showEn(s) ? (
                          <p className="mt-0.5 leading-relaxed text-stone-400" style={{ fontSize: `${13 * transcriptScale}px` }}>{s.en}</p>
                        ) : (
                          <button
                            onClick={() => onRevealEn(s)}
                            className="mt-1 inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] font-medium text-stone-600 transition hover:bg-white/5 hover:text-stone-300"
                          >
                            <EyeIcon /> Reveal translation
                          </button>
                        ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <SearchIcon large />
            <p className="mt-3 text-sm font-medium text-stone-300">No matching lines</p>
            <p className="mt-1 text-xs text-stone-600">Try a different word or phrase.</p>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 border-t border-white/7 px-4 py-2 text-[10px] text-stone-600">
        <span className="flex items-center gap-1.5"><i className="size-1.5 rounded-full bg-sky-400" /> New</span>
        <span className="flex items-center gap-1.5"><i className="size-1.5 rounded-full bg-amber-400" /> Learning</span>
        <span className="ml-auto hidden sm:inline">↑ ↓ to move between lines</span>
      </div>
    </div>
  );
}

function SearchIcon({ large = false }: { large?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className={large ? "size-6 text-stone-700" : "size-3.5"} aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>;
}

function CloseIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="size-3.5" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17" /></svg>;
}

function EyeIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="size-3.5" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></svg>;
}

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
