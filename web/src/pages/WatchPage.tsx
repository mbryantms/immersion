import CorrectionEditor from "../player/CorrectionEditor";
import SourcePanel from "../player/SourcePanel";
import { sourceSelection } from "../gloss/selection";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { QueryError } from "@/components/ErrorBoundary";
import { Skeleton } from "@/components/ui/skeleton";
import { post } from "../api/client";
import {
  patchTrackOffset,
  prefetchExplain,
  queueTranscribe,
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
import ExplainSheet from "../player/ExplainSheet";
import SessionSummary, { type SessionLookup } from "../player/SessionSummary";
import SubtitleOverlay from "../player/SubtitleOverlay";
import TranscriptPanel from "../player/TranscriptPanel";
import { useKeyboard } from "../player/useKeyboard";
import { useSentenceClock, type MediaEl } from "../player/useSentenceClock";
import StudyModeSelector from "../player/StudyModeSelector";
import { textIsVisible, type StudyMode } from "../player/studyMode";

export default function WatchPage() {
  const { id } = useParams();
  return <WatchSession key={id} />;
}

function WatchSession() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const videoRef = useRef<MediaEl | null>(null);
  const playerRef = useRef<HTMLDivElement | null>(null);

  const { data: item, isError: itemError, refetch: refetchItem } = useItem(id);
  const { data: sentData, isError: sentencesError, refetch: refetchSentences } = useSentences(id);
  const { data: knowledgeData } = useKnowledge(id);
  const knowledge = knowledgeData?.states ?? {};
  const savedLexemes = useMemo(() => new Set(knowledgeData?.saved ?? []), [knowledgeData]);

  const isAudio = item?.kind === "audio";
  const prefs = usePrefs();
  const [loop, setLoop] = useState(false);
  const [studyMode, setStudyMode] = useState<StudyMode>("read");
  const [listeningHint, setListeningHint] = useState(false);
  const [playbackError, setPlaybackError] = useState(false);
  const showText = textIsVisible(studyMode, listeningHint);
  const effectiveSubtitleMode = showText ? prefs.subtitleMode : "off";
  const [correctionFor, setCorrectionFor] = useState<SentenceOut | null>(null);
  const [gloss, setGloss] = useState<GlossTarget | null>(null);
  const [isPlayerFullscreen, setIsPlayerFullscreen] = useState(false);
  const [enRevealed, setEnRevealed] = useState<Set<number>>(new Set());
  const [pyRevealed, setPyRevealed] = useState<Set<string>>(new Set());
  const [explainFor, setExplainFor] = useState<SentenceOut | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [nudgeHidden, setNudgeHidden] = useState(true);
  const [transcribeQueued, setTranscribeQueued] = useState(false);
  const sessionLookups = useRef<Map<number, SessionLookup>>(new Map());
  const prefetchedExplains = useRef<Set<number>>(new Set());
  const playedSeconds = useRef(0);
  const subOffsetRef = useRef<number | null>(null); // survives rapid keypresses
  const [subOffset, setSubOffset] = useState<number | null>(null);

  // live sync nudges shift cue times client-side against the offset the
  // payload was baked with — no transcript refetch per keypress
  const zhTrackEarly = item?.tracks.find((t) => t.lang === "zh" && t.selected);
  const offsetDelta = (subOffset ?? zhTrackEarly?.offset_ms ?? 0) - (sentData?.zh_offset_ms ?? 0);
  const sentences = useMemo(() => {
    const raw = sentData?.sentences ?? [];
    if (!offsetDelta) return raw;
    return raw.map((s) => ({ ...s, t0: Math.max(0, s.t0 + offsetDelta), t1: Math.max(0, s.t1 + offsetDelta) }));
  }, [sentData, offsetDelta]);

  const { idx, visible, autoPaused, resume, armSentence, syncToTime } = useSentenceClock(videoRef, sentences, {
    pauseAfter: prefs.pauseAfter,
    pauseAfterDelayMs: prefs.pauseAfterDelayMs,
    loop,
    interactionHold: !!gloss || !!correctionFor,
    subtitleMode: effectiveSubtitleMode,
    itemId: id,
  });
  const current = idx >= 0 ? sentences[idx] : null;

  const setKnowledge = useSetKnowledge(id);
  const saveItem = useSaveItem(id);
  const changeStudyMode = useCallback((mode: StudyMode) => {
    setStudyMode(mode);
    setListeningHint(false);
    setGloss(null);
    setExplainFor(null);
    track("study_mode_change", { item_id: id, study_mode: mode });
  }, [id]);

  useEffect(() => {
    const media = videoRef.current;
    if (!media) return;
    const onError = () => setPlaybackError(true);
    const onLoaded = () => setPlaybackError(false);
    media.addEventListener("error", onError);
    media.addEventListener("loadeddata", onLoaded);
    return () => {
      media.removeEventListener("error", onError);
      media.removeEventListener("loadeddata", onLoaded);
    };
  }, [item]);

  useEffect(() => {
    const onFullscreenChange = () => setIsPlayerFullscreen(document.fullscreenElement === playerRef.current);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  // per-item session state
  useEffect(() => {
    setNudgeHidden(localStorage.getItem(`rewatch-nudge-${id}`) === "1");
    setTranscribeQueued(false);
    sessionLookups.current = new Map();
    playedSeconds.current = 0;
    subOffsetRef.current = null;
    setSubOffset(null);
  }, [id]);

  // reaching the end of the episode is the natural recap moment
  useEffect(() => {
    const media = videoRef.current;
    if (!media) return;
    const onEnded = () => {
      flush();
      setSummaryOpen(true);
    };
    media.addEventListener("ended", onEnded);
    return () => media.removeEventListener("ended", onEnded);
  }, [item, isAudio]);

  // ---- subtitle sync offset (,/. keys) -------------------------------------
  const zhTrack = zhTrackEarly;
  const shownOffset = subOffset ?? zhTrack?.offset_ms ?? 0;
  const nudgeSubs = useCallback(
    (delta: number) => {
      if (!zhTrack) return;
      const next = Math.max(-30_000, Math.min(30_000, (subOffsetRef.current ?? zhTrack.offset_ms) + delta));
      subOffsetRef.current = next;
      setSubOffset(next); // applied client-side via offsetDelta; PATCH just persists
      patchTrackOffset(zhTrack.id, next).catch(() => toast.error("Offset not saved — server unreachable"));
    },
    [zhTrack],
  );

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
        playedSeconds.current += 5;
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
      if (word.lex && !sessionLookups.current.has(word.lex)) {
        sessionLookups.current.set(word.lex, {
          lexemeId: word.lex,
          surface: word.t,
          pinyin: word.py?.join(" "),
          sentenceId: sentence.id,
        });
      }
      // a lookup is a confusion signal: warm the explanation cache so a
      // follow-up Explain click lands on (or joins) an in-flight generation
      if (!prefetchedExplains.current.has(sentence.id)) {
        prefetchedExplains.current.add(sentence.id);
        prefetchExplain(sentence.id);
      }
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
    if (!sel.rangeCount) return;
    const selected = sourceSelection(sel.getRangeAt(0));
    if (!selected || selected.end - selected.start > 12) return;
    const sentence = sentences.find((s) => s.id === selected.sentenceId);
    if (!sentence) return;
    post<LookupResult>("/lookup", { sentence_id: sentence.id, start: selected.start, end: selected.end })
      .then((res) => {
        if (res.candidates.length) {
          videoRef.current?.pause();
          setGloss({ sentence, span: res.span, candidates: res.candidates });
        }
      })
      .catch(() => {});
  }, [sentences, current]);

  const saveWord = useCallback(
    (lexemeId: number, surface: string, sentenceId: number, selection?: { selected_reading?: string; selected_meaning?: string; occurrence_start?: number }) => {
      saveItem.mutate(
        { kind: "word", lexeme_id: lexemeId, surface, sentence_id: sentenceId, ...selection },
        {
          onSuccess: (r) => toast.success(r.created ? `Saved ${surface}` : `${surface} — added this context`),
          onError: () => toast.error(`Couldn't save ${surface}`),
        },
      );
      track("save", { item_id: id, sentence_id: sentenceId, lexeme_id: lexemeId });
    },
    [saveItem, id],
  );
  const saveSentence = useCallback(
    (sentenceId: number) => {
      saveItem.mutate(
        { kind: "sentence", sentence_id: sentenceId },
        {
          onSuccess: (r) => toast.success(r.created ? "Sentence saved" : "Sentence already in your queue"),
          onError: () => toast.error("Couldn't save sentence"),
        },
      );
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
  useKeyboard(correctionFor ? {} : gloss ? {
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
    s: () => { if (showText) prefs.set({ subtitleMode: cycleSubtitleMode(prefs.subtitleMode) }); },
    t: () => showText && current && (enRevealed.has(current.id)
      ? setEnRevealed((p) => { const n = new Set(p); n.delete(current.id); return n; })
      : revealEn(current)),
    p: () => showText && current && togglePinyinSentence(current),
    d: () => {
      if (!current || !showText) return;
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
    ",": () => nudgeSubs(-250),
    ".": () => nudgeSubs(250),
    Escape: closeGloss,
  }, gloss ? [" ", "Escape"] : ["Escape"]);

  if (itemError) return <QueryError onRetry={() => void refetchItem()} />;
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
    <main className="watch-page min-h-[calc(100vh-53px)]" onMouseUp={onMouseUp}>
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
              <h1 className="min-w-0 break-words text-xl font-semibold tracking-[-0.02em] text-stone-50 sm:truncate sm:text-2xl">{item.title}</h1>
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
                  <p className="text-xs font-semibold text-stone-200">{Math.round((item.coverage ?? 0) * 100)}% vocabulary familiarity</p>
                  <p className="text-[11px] text-stone-400">Estimate · {item.unknown_lexemes ?? 0} unmarked words</p>
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

        {item.rewatch_nudge && !nudgeHidden && (
          <div className="mb-3 flex shrink-0 flex-wrap items-center gap-3 rounded-xl border border-teal-400/15 bg-teal-400/6 px-4 py-2.5 text-sm text-teal-100">
            <span>
              This episode has high estimated vocabulary familiarity. Try listening without text
              to check how much you understand.
            </span>
            <span className="grow" />
            <Button
              size="xs"
              variant="secondary"
              className="border border-teal-400/20 bg-teal-400/10 text-teal-200 hover:bg-teal-400/20"
              onClick={() => {
                changeStudyMode("listen");
                localStorage.setItem(`rewatch-nudge-${id}`, "1");
                setNudgeHidden(true);
                track("rewatch_nudge_accept", { item_id: id });
              }}
            >
              Listen without text
            </Button>
            <Button
              size="xs"
              variant="ghost"
              className="text-teal-300/60"
              onClick={() => {
                localStorage.setItem(`rewatch-nudge-${id}`, "1");
                setNudgeHidden(true);
              }}
            >
              Dismiss
            </Button>
          </div>
        )}

        {!isAudio && item.available && !item.ready && item.n_sentences === 0 && (
          <div className="mb-3 flex shrink-0 flex-wrap items-center gap-3 rounded-xl border border-amber-400/15 bg-amber-400/5 px-4 py-2.5 text-sm text-amber-100">
            <span>No Chinese subtitles were found for this video.</span>
            <span className="grow" />
            <Button
              size="xs"
              variant="secondary"
              disabled={transcribeQueued}
              className="border border-amber-400/20 bg-amber-400/10 text-amber-200 hover:bg-amber-400/20"
              onClick={() => {
                queueTranscribe(id)
                  .then(() => setTranscribeQueued(true))
                  .catch(() => {});
              }}
            >
              {transcribeQueued ? "Queued — check back soon" : "Generate transcript (Whisper)"}
            </Button>
          </div>
        )}

        <SourcePanel item={item} />
        <StudyModeSelector value={studyMode} onChange={changeStudyMode} />

        {sentencesError && <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm"><p className="grow">The transcript could not be loaded. Your media can still play.</p><Button variant="outline" size="sm" onClick={() => void refetchSentences()}>Retry transcript</Button></div>}
        {playbackError && <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm"><p className="grow">This media could not play. Check the source file or its conversion status in Admin.</p><Button variant="outline" size="sm" onClick={() => { setPlaybackError(false); videoRef.current?.load(); }}>Retry playback</Button><Button asChild variant="ghost" size="sm"><Link to="/admin">Open Admin</Link></Button></div>}

        <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_410px]">
          <section aria-label="Media player" className="flex min-h-0 min-w-0 flex-col gap-3">
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
                    mode={effectiveSubtitleMode}
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
                  mode={effectiveSubtitleMode}
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
                mode={effectiveSubtitleMode}
                onCycleMode={() => prefs.set({ subtitleMode: cycleSubtitleMode(prefs.subtitleMode) })}
                traditional={prefs.traditional}
                onToggleTraditional={() => prefs.set({ traditional: !prefs.traditional })}
                pinyin={prefs.pinyin}
                onTogglePinyin={() => prefs.set({ pinyin: !prefs.pinyin })}
                textControlsDisabled={!showText}
              />
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2 px-1 text-[11px] text-stone-600">
              {showText && <span className="flex items-center gap-1.5"><CursorIcon /> Tap a word for definitions</span>}
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
              {showText && current?.en && prefs.subtitleMode !== "dual" && (
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
              {showText && current && (
                <Button
                  variant="ghost"
                  size="xs"
                  onClick={() => {
                    videoRef.current?.pause();
                    setExplainFor(current);
                    track("explain", { item_id: id, sentence_id: current.id });
                  }}
                  className="text-muted-foreground hover:text-teal-300"
                  title="AI explanation of the current sentence"
                >
                  <SparkleIcon /> Explain
                </Button>
              )}
              {shownOffset !== 0 && (
                <Badge
                  variant="secondary"
                  className="cursor-pointer tabular-nums text-[10px] text-muted-foreground"
                  onClick={() => nudgeSubs(-shownOffset)}
                  title="Subtitle sync offset — click to reset"
                >
                  subs {shownOffset > 0 ? "+" : ""}{(shownOffset / 1000).toFixed(2)}s
                </Badge>
              )}
              <span className="grow" />
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  videoRef.current?.pause();
                  flush();
                  setSummaryOpen(true);
                }}
                className="text-muted-foreground"
                title="Review this session's lookups"
              >
                End session
              </Button>
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
                  <Shortcut keys=", ." label="Subtitle sync" />
                </div>
              </details>
            </div>
          </section>

          <aside className="h-[48vh] min-h-[360px] overflow-hidden rounded-2xl border border-white/8 shadow-xl shadow-black/15 xl:h-auto xl:min-h-0">
            {studyMode === "dictate" ? (
              <DictationPanel
                key={id}
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
            ) : studyMode === "listen" && !listeningHint ? (
              <div className="flex h-full flex-col items-center justify-center gap-4 bg-card px-7 py-10 text-center">
                <div className="flex size-16 items-center justify-center rounded-full bg-primary/10 text-2xl" aria-hidden="true">听</div>
                <h2 className="text-xl font-semibold">Let your ears lead</h2>
                <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">The transcript, pinyin, and translations are hidden. Replay a sentence before asking for a hint.</p>
                <Button variant="secondary" onClick={() => {
                  setListeningHint(true);
                  track("transcript_hint", { item_id: id, study_mode: "listen", sentence_id: current?.id });
                }}>Reveal transcript as a hint</Button>
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col">
              {studyMode === "listen" && <div className="flex items-center justify-between gap-2 border-b border-border bg-primary/5 px-4 py-2 text-xs text-muted-foreground"><span>Transcript hint is visible</span><Button variant="ghost" size="sm" onClick={() => setListeningHint(false)}>Hide text again</Button></div>}
              {!sentences.length && !sentencesError && <p role="status" className="border-b border-border p-4 text-sm text-muted-foreground">{item.ready ? "No transcript lines are available." : "The transcript is not ready yet. Check processing in Admin."}</p>}
              <TranscriptPanel
                onEdit={(sentence) => { videoRef.current?.pause(); setCorrectionFor(sentence); }}
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
              </div>
            )}
          </aside>
        </div>
      </div>

      {explainFor && <ExplainSheet sentence={explainFor} onClose={() => setExplainFor(null)} />}

      {summaryOpen && (
        <SessionSummary
          lookups={[...sessionLookups.current.values()]}
          minutes={playedSeconds.current / 60}
          knowledge={knowledge}
          savedLexemes={savedLexemes}
          onSave={(selected) => {
            selected.forEach((lookup) =>
              saveItem.mutate({
                kind: "word",
                lexeme_id: lookup.lexemeId,
                surface: lookup.surface,
                sentence_id: lookup.sentenceId,
              }),
            );
            selected.forEach((lookup) => track("save", { item_id: id, sentence_id: lookup.sentenceId, lexeme_id: lookup.lexemeId }));
            toast.success(`Saved ${selected.length} word${selected.length === 1 ? "" : "s"} to your review queue`);
            setSummaryOpen(false);
          }}
          onClose={() => setSummaryOpen(false)}
        />
      )}

      {correctionFor && <CorrectionEditor sentenceId={correctionFor.id} itemId={id} onClose={() => setCorrectionFor(null)} />}
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
    </main>
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

function SparkleIcon() {
  return <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" className="size-3.5" aria-hidden="true"><path d="M9 2.5 10.6 7 15 8.5 10.6 10 9 14.5 7.4 10 3 8.5 7.4 7 9 2.5ZM14.5 13l.6 1.7 1.7.6-1.7.6-.6 1.7-.6-1.7-1.7-.6 1.7-.6.6-1.7Z" /></svg>;
}

function Shortcut({ keys, label }: { keys: string; label: string }) {
  return <span className="flex items-center gap-2"><kbd className="min-w-7 rounded border border-white/10 bg-black/20 px-1.5 py-0.5 text-center text-[10px] text-stone-300">{keys}</kbd>{label}</span>;
}
