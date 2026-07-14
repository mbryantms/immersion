import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { post } from "../api/client";
import {
  saveProgress,
  useItem,
  useKnowledge,
  useSaveItem,
  useSentences,
  useSetKnowledge,
} from "../api/queries";
import type { LookupResult, SentenceOut, Word } from "../api/types";
import GlossSheet, { type GlossTarget } from "../gloss/GlossSheet";
import { flush, track } from "../lib/events";
import { cycleSubtitleMode, usePrefs } from "../lib/prefs";
import AudioSurface from "../player/AudioSurface";
import Controls, { nextRate } from "../player/Controls";
import DictationPanel from "../player/DictationPanel";
import SubtitleOverlay from "../player/SubtitleOverlay";
import TranscriptPanel from "../player/TranscriptPanel";
import { useKeyboard } from "../player/useKeyboard";
import { useSentenceClock, type MediaEl } from "../player/useSentenceClock";

export default function WatchPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const videoRef = useRef<MediaEl | null>(null);
  const playerRef = useRef<HTMLDivElement | null>(null);

  const { data: item } = useItem(id);
  const { data: sentData } = useSentences(id);
  const { data: knowledgeData } = useKnowledge(id);
  const sentences = useMemo(() => sentData?.sentences ?? [], [sentData]);
  const knowledge = knowledgeData?.states ?? {};
  const savedLexemes = useMemo(() => new Set(knowledgeData?.saved ?? []), [knowledgeData]);

  const isAudio = item?.kind === "audio";
  const prefs = usePrefs();
  const [loop, setLoop] = useState(false);
  const [dictation, setDictation] = useState(false);
  const [gloss, setGloss] = useState<GlossTarget | null>(null);
  const [isPlayerFullscreen, setIsPlayerFullscreen] = useState(false);
  const [enRevealed, setEnRevealed] = useState<Set<number>>(new Set());
  const [pyRevealed, setPyRevealed] = useState<Set<string>>(new Set());

  const { idx, visible, autoPaused, resume, armSentence, syncToTime } = useSentenceClock(videoRef, sentences, {
    pauseAfter: prefs.pauseAfter,
    pauseAfterDelayMs: prefs.pauseAfterDelayMs,
    loop,
    interactionHold: !!gloss,
    subtitleMode: prefs.subtitleMode,
    itemId: id,
  });
  const current = idx >= 0 ? sentences[idx] : null;

  const setKnowledge = useSetKnowledge(id);
  const saveItem = useSaveItem(id);

  useEffect(() => {
    const onFullscreenChange = () => setIsPlayerFullscreen(document.fullscreenElement === playerRef.current);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  // ---- resume + progress persistence -------------------------------------
  const [searchParams] = useSearchParams();
  const resumed = useRef(false);
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !item || resumed.current) return;
    resumed.current = true;
    const jump = Number(searchParams.get("t")); // ?t=<ms> deep link (search/concordance)
    if (Number.isFinite(jump) && jump > 0) {
      v.currentTime = jump / 1000;
    } else {
      const pos = item.progress.position_ms;
      if (pos > 3000 && item.duration_ms && pos < 0.95 * item.duration_ms) {
        v.currentTime = pos / 1000;
      }
    }
    v.playbackRate = prefs.rate;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item]);

  useEffect(() => {
    const iv = setInterval(() => {
      const v = videoRef.current;
      if (v && !v.paused) {
        saveProgress(id, {
          position_ms: Math.round(v.currentTime * 1000),
          duration_ms: Math.round((v.duration || 0) * 1000),
          subtitle_mode: prefs.subtitleMode,
        });
      }
    }, 5000);
    return () => {
      clearInterval(iv);
      const v = videoRef.current;
      if (v && v.currentTime > 0) {
        saveProgress(id, {
          position_ms: Math.round(v.currentTime * 1000),
          subtitle_mode: prefs.subtitleMode,
        });
      }
      flush();
    };
  }, [id, prefs.subtitleMode]);

  // ---- sentence navigation -------------------------------------------------
  const seekTo = useCallback(
    (s: SentenceOut, preroll = true) => {
      const v = videoRef.current;
      if (!v) return;
      v.currentTime = Math.max(0, (s.t0 - (preroll ? prefs.prerollMs : 0)) / 1000);
      armSentence(s.id);
      void v.play();
    },
    [armSentence, prefs.prerollMs],
  );
  const goto = useCallback(
    (delta: number) => {
      const i = Math.min(sentences.length - 1, Math.max(0, (idx < 0 ? 0 : idx) + delta));
      if (sentences[i]) seekTo(sentences[i]);
    },
    [idx, sentences, seekTo],
  );

  // ---- gloss ---------------------------------------------------------------
  const openGloss = useCallback(
    (sentence: SentenceOut, word: Word) => {
      if (word.type !== "zh") return;
      videoRef.current?.pause();
      setGloss({ sentence, word });
    },
    [],
  );

  const closeGloss = useCallback(() => setGloss(null), []);
  const resumeFromGloss = useCallback(() => {
    setGloss(null);
    resume();
  }, [resume]);
  const togglePlayback = useCallback(() => {
    const media = videoRef.current;
    if (!media) return;
    if (media.paused) resume();
    else media.pause();
  }, [resume]);

  // drag-selection across characters -> custom span lookup (VID-013)
  const onMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const text = sel.toString().trim();
    if (!text || text.length > 12 || !/[㐀-鿿]/.test(text)) return;
    const node = sel.anchorNode?.parentElement?.closest("[data-sentence-id]");
    const sid = node ? Number(node.getAttribute("data-sentence-id")) : NaN;
    const sentence = sentences.find((s) => s.id === sid) ?? current;
    if (!sentence) return;
    const start = sentence.zh.indexOf(text);
    if (start < 0) return;
    post<LookupResult>("/lookup", { sentence_id: sentence.id, start, end: start + text.length })
      .then((res) => {
        if (res.candidates.length) {
          videoRef.current?.pause();
          setGloss({ sentence, span: res.span, candidates: res.candidates });
        }
      })
      .catch(() => {});
  }, [sentences, current]);

  const saveWord = useCallback(
    (lexemeId: number, surface: string, sentenceId: number) => {
      saveItem.mutate({ kind: "word", lexeme_id: lexemeId, surface, sentence_id: sentenceId });
      track("save", { item_id: id, sentence_id: sentenceId, lexeme_id: lexemeId });
    },
    [saveItem, id],
  );
  const saveSentence = useCallback(
    (sentenceId: number) => {
      saveItem.mutate({ kind: "sentence", sentence_id: sentenceId });
      track("save_sentence", { item_id: id, sentence_id: sentenceId });
    },
    [saveItem, id],
  );

  const revealEn = useCallback((s: SentenceOut) => {
    setEnRevealed((prev) => new Set(prev).add(s.id));
    track("translation_reveal", { item_id: id, sentence_id: s.id });
  }, [id]);

  const togglePinyinSentence = useCallback((s: SentenceOut) => {
    setPyRevealed((prev) => {
      const next = new Set(prev);
      const key = `s:${s.id}`;
      if (next.has(key)) next.delete(key);
      else {
        next.add(key);
        track("pinyin_reveal", { item_id: id, sentence_id: s.id });
      }
      return next;
    });
  }, [id]);

  const showPinyin = useCallback(
    (sentenceId: number, _wordIdx: number) => prefs.pinyin || pyRevealed.has(`s:${sentenceId}`),
    [prefs.pinyin, pyRevealed],
  );

  // ---- keyboard (spec §15.2) ------------------------------------------------
  useKeyboard(gloss ? {
    " ": resumeFromGloss,
    Escape: closeGloss,
  } : {
    " ": () => {
      const v = videoRef.current;
      if (!v) return;
      v.paused ? resume() : v.pause();
    },
    Enter: resume,
    ArrowLeft: () => {
      const media = videoRef.current;
      if (!media) return;
      media.currentTime = Math.max(0, media.currentTime - 5);
      syncToTime(media.currentTime * 1000);
    },
    ArrowRight: () => {
      const media = videoRef.current;
      if (!media) return;
      media.currentTime = Math.min(media.duration || Infinity, media.currentTime + 5);
      syncToTime(media.currentTime * 1000);
    },
    ArrowUp: () => goto(-1),
    ArrowDown: () => goto(1),
    r: () => current && seekTo(current),
    l: () => setLoop((enabled) => {
      const next = !enabled;
      if (next && prefs.pauseAfter) prefs.set({ pauseAfter: false });
      return next;
    }),
    s: () => prefs.set({ subtitleMode: cycleSubtitleMode(prefs.subtitleMode) }),
    t: () => current && (enRevealed.has(current.id)
      ? setEnRevealed((p) => { const n = new Set(p); n.delete(current.id); return n; })
      : revealEn(current)),
    p: () => current && togglePinyinSentence(current),
    d: () => {
      if (!current) return;
      const w = current.words.find((w) => w.type === "zh" && (!w.lex || (knowledge[w.lex] ?? "new") === "new"))
        ?? current.words.find((w) => w.type === "zh");
      if (w) openGloss(current, w);
    },
    a: () => current && saveSentence(current.id),
    "[": () => { const r = nextRate(nextRate(nextRate(prefs.rate))); prefs.set({ rate: r }); if (videoRef.current) videoRef.current.playbackRate = r; },
    "]": () => { const r = nextRate(prefs.rate); prefs.set({ rate: r }); if (videoRef.current) videoRef.current.playbackRate = r; },
    m: () => {
      const next = !prefs.pauseAfter;
      if (next) setLoop(false);
      prefs.set({ pauseAfter: next });
    },
    Escape: closeGloss,
  }, gloss ? [" ", "Escape"] : ["Escape"]);

  if (!item) {
    return (
      <div className="mx-auto grid h-[calc(100vh-53px)] max-w-[1600px] gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-4">
          <Skeleton className="h-12 w-2/3 rounded-xl" />
          <Skeleton className="aspect-video rounded-2xl" />
        </div>
        <Skeleton className="hidden rounded-2xl lg:block" />
      </div>
    );
  }

  return (
    <div className="watch-page min-h-[calc(100vh-53px)]" onMouseUp={onMouseUp}>
      {/* xl pins the page to the viewport so the transcript scrolls inside its
          panel (follow mode needs the panel, not the page, to be the scroller) */}
      <div className="mx-auto flex min-h-[calc(100vh-53px)] max-w-[1680px] flex-col px-3 py-4 sm:px-5 lg:px-6 xl:h-[calc(100vh-53px)]">
        <header className="mb-4 flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            {item.series ? (
              <div className="mb-1.5 flex items-center gap-2 text-xs font-medium text-stone-500">
                <Link to="/library" className="transition hover:text-teal-300">Library</Link>
                <ChevronRightIcon />
                <Link to={`/series/${item.series.id}`} className="truncate transition hover:text-teal-300">
                  {item.series.title}
                </Link>
                {item.ordinal !== null && <span className="text-stone-700">· Episode {item.ordinal}</span>}
              </div>
            ) : (
              <Link to="/library" className="mb-1.5 inline-block text-xs font-medium text-stone-500 transition hover:text-teal-300">Library</Link>
            )}
            <div className="flex items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-[-0.02em] text-stone-50 sm:text-2xl">{item.title}</h1>
              {item.series?.level && (
                <Badge variant="secondary" className="shrink-0 text-[10px] uppercase tracking-wide text-primary">Level {item.series.level}</Badge>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {item.coverage !== undefined && (
              <div className="flex items-center gap-2 rounded-xl border border-white/7 bg-white/[0.035] px-3 py-2">
                <ProgressRing value={item.coverage ?? 0} />
                <div>
                  <p className="text-xs font-semibold text-stone-200">{Math.round((item.coverage ?? 0) * 100)}% familiar</p>
                  <p className="text-[10px] text-stone-500">{item.unknown_lexemes ?? 0} words to learn</p>
                </div>
              </div>
            )}
            <div className="flex overflow-hidden rounded-xl border border-white/7 bg-white/[0.035]">
              <Button
                variant="ghost"
                size="icon"
                disabled={!item.prev_item_id}
                className="episode-nav rounded-none border-r border-white/7"
                onClick={() => item.prev_item_id && navigate(`/watch/${item.prev_item_id}`)}
                title="Previous episode"
                aria-label="Previous episode"
              >
                <PreviousEpisodeIcon />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                disabled={!item.next_item_id}
                className="episode-nav rounded-none"
                onClick={() => item.next_item_id && navigate(`/watch/${item.next_item_id}`)}
                title="Next episode"
                aria-label="Next episode"
              >
                <NextEpisodeIcon />
              </Button>
            </div>
          </div>
        </header>

        <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_410px]">
          <main className="flex min-h-0 min-w-0 flex-col gap-3">
            <div ref={playerRef} className="player-shell flex flex-col overflow-hidden rounded-2xl border border-white/8 bg-[#111715] shadow-2xl shadow-black/25 xl:min-h-0 xl:flex-1">
              {isAudio ? (
                <AudioSurface
                  mediaRef={videoRef}
                  src={item.stream_url}
                  cover={item.thumb_url}
                  title={item.title}
                  seriesTitle={item.series?.title}
                  onTogglePlay={togglePlayback}
                >
                  <SubtitleOverlay
                    sentence={current}
                    visible={visible || (!!gloss && gloss.sentence.id === current?.id)}
                    mode={prefs.subtitleMode}
                    knowledge={knowledge}
                    savedLexemes={savedLexemes}
                    traditional={prefs.traditional}
                    toneColors={prefs.toneColors}
                    fontScale={prefs.fontScale}
                    showPinyin={showPinyin}
                    enRevealed={!!current && enRevealed.has(current.id)}
                    onTapWord={openGloss}
                  />
                </AudioSurface>
              ) : (
              <div className="video-stage relative flex min-h-[220px] items-center justify-center overflow-hidden bg-black sm:min-h-[360px] xl:min-h-0 xl:flex-1" onClick={() => setGloss(null)}>
                <img src={item.thumb_url} alt="" className="pointer-events-none absolute inset-0 h-full w-full scale-110 object-cover opacity-20 blur-3xl" />
                <div className="pointer-events-none absolute inset-0 bg-black/45" />
                <video
                  ref={(el) => {
                    videoRef.current = el;
                  }}
                  src={item.stream_url}
                  poster={item.thumb_url}
                  className="relative mx-auto max-h-[56vh] min-h-[220px] w-full object-contain sm:min-h-[360px] xl:h-full xl:max-h-full xl:min-h-0"
                  playsInline
                  preload="metadata"
                  onClick={(e) => {
                    e.stopPropagation();
                    togglePlayback();
                  }}
                />
                <SubtitleOverlay
                  sentence={current}
                  visible={visible || (!!gloss && gloss.sentence.id === current?.id)}
                  mode={prefs.subtitleMode}
                  knowledge={knowledge}
                  savedLexemes={savedLexemes}
                  traditional={prefs.traditional}
                  toneColors={prefs.toneColors}
                  fontScale={prefs.fontScale}
                  showPinyin={showPinyin}
                  enRevealed={!!current && enRevealed.has(current.id)}
                  onTapWord={openGloss}
                />
              </div>
              )}
              <Controls
                videoRef={videoRef}
                playerRef={playerRef}
                onTogglePlay={togglePlayback}
                onSeek={(seconds) => {
                  if (!videoRef.current) return;
                  videoRef.current.currentTime = seconds;
                  syncToTime(seconds * 1000);
                }}
                onPrev={() => goto(-1)}
                onReplay={() => current && seekTo(current)}
                onNext={() => goto(1)}
                loop={loop}
                onToggleLoop={() => setLoop((enabled) => {
                  const next = !enabled;
                  if (next && prefs.pauseAfter) prefs.set({ pauseAfter: false });
                  return next;
                })}
                pauseAfter={prefs.pauseAfter}
                onTogglePauseAfter={() => {
                  const next = !prefs.pauseAfter;
                  if (next) setLoop(false);
                  prefs.set({ pauseAfter: next });
                }}
                rate={prefs.rate}
                onCycleRate={() => {
                  const r = nextRate(prefs.rate);
                  prefs.set({ rate: r });
                  if (videoRef.current) videoRef.current.playbackRate = r;
                }}
                mode={prefs.subtitleMode}
                onCycleMode={() => prefs.set({ subtitleMode: cycleSubtitleMode(prefs.subtitleMode) })}
                traditional={prefs.traditional}
                onToggleTraditional={() => prefs.set({ traditional: !prefs.traditional })}
                pinyin={prefs.pinyin}
                onTogglePinyin={() => prefs.set({ pinyin: !prefs.pinyin })}
                dictation={dictation}
                onToggleDictation={isAudio ? () => setDictation((x) => !x) : undefined}
              />
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2 px-1 text-[11px] text-stone-600">
              <span className="flex items-center gap-1.5"><CursorIcon /> Tap a word for definitions</span>
              {autoPaused && !gloss && (
                <Button
                  variant="secondary"
                  size="xs"
                  onClick={resume}
                  className="border border-primary/15 bg-primary/10 text-primary hover:bg-primary/15"
                  title="Continue to the next sentence (Space)"
                >
                  <PlaySmallIcon /> Continue <kbd className="hidden font-sans text-[9px] text-primary/55 sm:inline">Space</kbd>
                </Button>
              )}
              {current && (
                <Badge variant="secondary" className="tabular-nums text-[10px] text-muted-foreground">Sentence {idx + 1} of {sentences.length}</Badge>
              )}
              {current?.en && prefs.subtitleMode !== "dual" && (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => enRevealed.has(current.id)
                    ? setEnRevealed((previous) => { const next = new Set(previous); next.delete(current.id); return next; })
                    : revealEn(current)}
                  className="text-muted-foreground"
                  title="Toggle current translation (T)"
                >
                  <TranslationIcon /> {enRevealed.has(current.id) ? "Hide English" : "Reveal English"}
                </Button>
              )}
              {current && (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => saveSentence(current.id)}
                  className="text-muted-foreground hover:text-amber-300"
                  title="Save current sentence (A)"
                >
                  <BookmarkIcon /> Save sentence
                </Button>
              )}
              <span className="grow" />
              <details className="shortcut-help relative">
                <summary className="cursor-pointer list-none rounded-md px-2 py-1 transition hover:bg-white/5 hover:text-stone-300">Keyboard shortcuts</summary>
                <div className="absolute bottom-8 right-0 z-30 grid w-72 grid-cols-2 gap-x-4 gap-y-2 rounded-xl border border-white/10 bg-[#18201d] p-3 text-xs text-stone-400 shadow-2xl">
                  <Shortcut keys="Space" label="Play / pause" />
                  <Shortcut keys="↑ ↓" label="Move sentence" />
                  <Shortcut keys="R" label="Replay" />
                  <Shortcut keys="L" label="Loop" />
                  <Shortcut keys="S" label="Subtitles" />
                  <Shortcut keys="T" label="Translation" />
                  <Shortcut keys="P" label="Pinyin" />
                  <Shortcut keys="D" label="Define" />
                  <Shortcut keys="A" label="Save sentence" />
                  <Shortcut keys="M" label="Auto-pause" />
                </div>
              </details>
            </div>
          </main>

          <aside className="h-[48vh] min-h-[360px] overflow-hidden rounded-2xl border border-white/8 shadow-xl shadow-black/15 xl:h-auto xl:min-h-0">
            {isAudio && dictation ? (
              <DictationPanel
                itemId={id}
                sentences={sentences}
                currentIdx={idx}
                mediaRef={videoRef}
                knowledge={knowledge}
                savedLexemes={savedLexemes}
                traditional={prefs.traditional}
                toneColors={prefs.toneColors}
                onTapWord={openGloss}
                onArmSentence={(sentence) => armSentence(sentence.id)}
              />
            ) : (
              <TranscriptPanel
                sentences={sentences}
                currentIdx={idx}
                knowledge={knowledge}
                savedLexemes={savedLexemes}
                traditional={prefs.traditional}
                toneColors={prefs.toneColors}
                fontScale={prefs.transcriptFontScale}
                showEn={(s) => prefs.subtitleMode === "dual" || enRevealed.has(s.id)}
                showPinyin={showPinyin}
                onSeek={(s) => seekTo(s, false)}
                onTapWord={openGloss}
                onRevealEn={revealEn}
                onFontScaleChange={(fontScale) => prefs.set({ transcriptFontScale: fontScale })}
              />
            )}
          </aside>
        </div>
      </div>

      {gloss && createPortal(
        <GlossSheet
          target={gloss}
          itemId={id}
          knowledge={knowledge}
          savedLexemes={savedLexemes}
          onClose={closeGloss}
          onResume={resumeFromGloss}
          onSaveWord={saveWord}
          onSaveSentence={saveSentence}
          onSetState={(lexemeId, state) => setKnowledge.mutate({ lexemeId, state })}
        />,
        isPlayerFullscreen && playerRef.current ? playerRef.current : document.body,
      )}
    </div>
  );
}

function ChevronRightIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-3" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>;
}

function PlaySmallIcon() {
  return <svg viewBox="0 0 18 18" fill="currentColor" className="size-3" aria-hidden="true"><path d="m5.5 3.5 9 5.5-9 5.5v-11Z" /></svg>;
}

function ProgressRing({ value }: { value: number }) {
  const percent = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="relative size-8">
      <svg viewBox="0 0 36 36" className="size-8 -rotate-90" aria-hidden="true">
        <circle cx="18" cy="18" r="14" fill="none" stroke="currentColor" strokeWidth="3" className="text-white/8" />
        <circle cx="18" cy="18" r="14" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeDasharray={`${percent * 0.88} 88`} className="text-teal-400" />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-teal-200">{Math.round(percent)}</span>
    </div>
  );
}

function PreviousEpisodeIcon() {
  return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4" aria-hidden="true"><path d="m12 5-5 5 5 5M5 5v10" /></svg>;
}

function NextEpisodeIcon() {
  return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" className="size-4" aria-hidden="true"><path d="m8 5 5 5-5 5M15 5v10" /></svg>;
}

function CursorIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-3.5 text-teal-500" aria-hidden="true"><path d="m4 2 9 7-4 .7L7 14 4 2Z" /></svg>;
}

function TranslationIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" className="size-3.5" aria-hidden="true"><path d="M2.5 4h8M6.5 2v2M4 4c.5 2.5 2.5 4.5 5 5.5M9 4c-.5 2.5-2.5 4.5-5 5.5M10 15l3-7 3 7M11 13h4" /></svg>;
}

function BookmarkIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" className="size-3.5" aria-hidden="true"><path d="M5 2.5h8v13l-4-2.7L5 15.5v-13Z" /></svg>;
}

function Shortcut({ keys, label }: { keys: string; label: string }) {
  return <span className="flex items-center gap-2"><kbd className="min-w-7 rounded border border-white/10 bg-black/20 px-1.5 py-0.5 text-center text-[10px] text-stone-300">{keys}</kbd>{label}</span>;
}
