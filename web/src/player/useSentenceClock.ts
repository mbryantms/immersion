import { useEffect, useRef, useState } from "react";

import type { SentenceOut } from "../api/types";
import { track } from "../lib/events";
import { displayIndexAt, heardEnough, reachedTargetBoundary, targetIndexAt } from "./sentenceClockModel";

/** Anything with a clock we can drive: <video> for episodes, <audio> for podcasts. */
export type MediaEl = HTMLVideoElement | HTMLAudioElement;

export interface ClockOpts {
  pauseAfter: boolean;
  pauseAfterDelayMs: number;
  loop: boolean;
  interactionHold: boolean;
  subtitleMode: string;
  itemId: number;
}

interface PlaybackTarget {
  index: number;
  /** Explicit targets come from replay/transcript navigation and survive preroll. */
  explicit: boolean;
  /** Logical media position where this pass through the sentence began. */
  heardFromMs: number;
  completed: boolean;
}

const GRACE_MS = 180;

/**
 * Keeps subtitle display state and learning playback state separate.
 *
 * The displayed sentence follows media time. Auto-pause and loop follow an
 * explicit playback target, so a dropped animation frame or overlapping cue
 * cannot silently replace the sentence the learner asked to hear.
 */
export function useSentenceClock(
  mediaRef: React.RefObject<MediaEl | null>,
  sentences: SentenceOut[],
  opts: ClockOpts,
) {
  const [idx, setIdx] = useState(-1);
  const [visible, setVisible] = useState(false);
  const [autoPaused, setAutoPaused] = useState(false);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const targetRef = useRef<PlaybackTarget | null>(null);
  const pinnedIdxRef = useRef<number | null>(null);
  const autoResumeTimerRef = useRef<number | null>(null);

  const clearAutoResume = () => {
    if (autoResumeTimerRef.current === null) return;
    window.clearTimeout(autoResumeTimerRef.current);
    autoResumeTimerRef.current = null;
  };

  const armIndex = (index: number, explicit: boolean, heardFromMs?: number) => {
    targetRef.current = index >= 0 && index < sentences.length
      ? {
          index,
          explicit,
          heardFromMs: heardFromMs ?? (explicit
            ? sentences[index].t0
            : (mediaRef.current?.currentTime ?? sentences[index].t0 / 1000) * 1000),
          completed: false,
        }
      : null;
    pinnedIdxRef.current = null;
    setAutoPaused(false);
    clearAutoResume();
  };

  const advanceAfterPause = (media: MediaEl) => {
    const completed = targetRef.current?.index ?? pinnedIdxRef.current ?? -1;
    const currentMs = media.currentTime * 1000;
    const next = targetIndexAt(sentences, currentMs + 1, completed + 1);
    targetRef.current = next >= 0
      ? { index: next, explicit: false, heardFromMs: sentences[next].t0, completed: false }
      : null;
    pinnedIdxRef.current = null;
    setAutoPaused(false);
    clearAutoResume();

    // Overlapping cues require a small rewind so the next selected sentence is
    // heard from its own beginning instead of resuming partway through it.
    if (next >= 0 && sentences[next].t0 < currentMs - 30) {
      media.currentTime = sentences[next].t0 / 1000;
    }
  };

  const resume = () => {
    const media = mediaRef.current;
    if (!media?.paused) return;
    if (autoPaused || pinnedIdxRef.current !== null) advanceAfterPause(media);
    void media.play();
  };

  // A definition or other learning interaction owns the pause. Any scheduled
  // resume must be cancelled rather than firing later beneath the interaction.
  useEffect(() => {
    if (opts.interactionHold) clearAutoResume();
    // clearAutoResume intentionally operates on a stable ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.interactionHold]);

  useEffect(() => {
    const media = mediaRef.current;
    if (!media || !sentences.length) return;
    let raf = 0;

    const scheduleAutoResume = (targetIndex: number) => {
      clearAutoResume();
      const delay = optsRef.current.pauseAfterDelayMs;
      if (delay <= 0) return;
      autoResumeTimerRef.current = window.setTimeout(() => {
        autoResumeTimerRef.current = null;
        if (
          pinnedIdxRef.current === targetIndex
          && media.paused
          && !optsRef.current.interactionHold
        ) {
          advanceAfterPause(media);
          void media.play();
        }
      }, delay);
    };

    const recordCompletion = (target: PlaybackTarget, positionMs: number) => {
      const sentence = sentences[target.index];
      if (!sentence) return;
      if (heardEnough(sentence, target.heardFromMs)) {
        track("sentence_played", {
          item_id: optsRef.current.itemId,
          sentence_id: sentence.id,
          subtitle_mode: optsRef.current.subtitleMode,
          position_ms: Math.round(positionMs),
        });
      }
    };

    const tick = () => {
      const ms = media.currentTime * 1000;
      const clockIndex = displayIndexAt(sentences, ms);
      const currentOpts = optsRef.current;

      if (!media.paused || media.ended) {
        if (!targetRef.current) {
          const target = targetIndexAt(sentences, ms);
          targetRef.current = target >= 0
            ? { index: target, explicit: false, heardFromMs: ms, completed: false }
            : null;
        }

        let target = targetRef.current;
        // Continuous playback can cross several very short or malformed cues in
        // one frame. Advance until the next unfinished target is found.
        while (target) {
          const sentence = sentences[target.index];
          if (!sentence || !reachedTargetBoundary(sentence, ms)) break;
          if (target.completed) break;
          target.completed = true;
          recordCompletion(target, ms);

          if (currentOpts.loop) {
            media.currentTime = sentence.t0 / 1000;
            target.heardFromMs = sentence.t0;
            target.completed = false;
            pinnedIdxRef.current = null;
            setAutoPaused(false);
            if (media.ended) void media.play();
            break;
          }

          if (currentOpts.pauseAfter) {
            // A frame may arrive after the following cue has started. Snap to the
            // selected boundary and pin the reviewed sentence instead of showing
            // the following line while paused.
            media.pause();
            media.currentTime = sentence.t1 / 1000;
            pinnedIdxRef.current = target.index;
            setIdx(target.index);
            setVisible(true);
            setAutoPaused(true);
            scheduleAutoResume(target.index);
            raf = requestAnimationFrame(tick);
            return;
          }

          const next = targetIndexAt(sentences, ms + 1, target.index + 1);
          targetRef.current = next >= 0
            ? { index: next, explicit: false, heardFromMs: sentences[next].t0, completed: false }
            : null;
          target = targetRef.current;
        }
      }

      const displayIndex = pinnedIdxRef.current ?? clockIndex;
      const displaySentence = displayIndex >= 0 ? sentences[displayIndex] : null;
      setIdx(displayIndex);
      setVisible(
        pinnedIdxRef.current !== null
        || (!!displaySentence && ms < displaySentence.t1 + GRACE_MS),
      );
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      clearAutoResume();
    };
    // mediaRef is stable; sentence replacement intentionally rebuilds the clock.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaRef, sentences]);

  return {
    idx,
    visible,
    autoPaused,
    resume,
    /** Arm the exact sentence selected by replay or transcript navigation. */
    armSentence: (sentenceId: number) => {
      const index = sentences.findIndex((sentence) => sentence.id === sentenceId);
      armIndex(index, true, index >= 0 ? sentences[index].t0 : undefined);
    },
    /** Recompute the next boundary after free timeline or relative seeking. */
    syncToTime: (ms: number) => {
      armIndex(targetIndexAt(sentences, ms), false, ms);
    },
  };
}
