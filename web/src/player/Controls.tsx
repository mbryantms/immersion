import { useEffect, useState } from "react";

import type { SubtitleMode } from "../lib/prefs";
import type { MediaEl } from "./useSentenceClock";

interface Props {
  videoRef: React.RefObject<MediaEl | null>;
  playerRef: React.RefObject<HTMLDivElement | null>;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  onPrev: () => void;
  onReplay: () => void;
  onNext: () => void;
  loop: boolean;
  onToggleLoop: () => void;
  pauseAfter: boolean;
  onTogglePauseAfter: () => void;
  rate: number;
  onCycleRate: () => void;
  mode: SubtitleMode;
  onCycleMode: () => void;
  traditional: boolean;
  onToggleTraditional: () => void;
  pinyin: boolean;
  onTogglePinyin: () => void;
  // present only for audio items (podcasts)
  dictation?: boolean;
  onToggleDictation?: () => void;
}

const RATES = [0.6, 0.8, 1.0, 1.25];
export const nextRate = (r: number) => RATES[(RATES.indexOf(r) + 1) % RATES.length] ?? 1.0;

export default function Controls(p: Props) {
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [buffered, setBuffered] = useState(0);
  const [paused, setPaused] = useState(true);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const v = p.videoRef.current;
    if (!v) return;
    const onTime = () => {
      setTime(v.currentTime);
      if (v.buffered.length) setBuffered(v.buffered.end(v.buffered.length - 1));
    };
    const onDur = () => setDur(v.duration || 0);
    const onPlay = () => setPaused(false);
    const onPause = () => setPaused(true);
    const onVolume = () => {
      setMuted(v.muted);
      setVolume(v.volume);
    };
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("progress", onTime);
    v.addEventListener("durationchange", onDur);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("volumechange", onVolume);
    onDur();
    onVolume();
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("progress", onTime);
      v.removeEventListener("durationchange", onDur);
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
      v.removeEventListener("volumechange", onVolume);
    };
  }, [p.videoRef]);

  useEffect(() => {
    const onFullscreen = () => setIsFullscreen(document.fullscreenElement === p.playerRef.current);
    document.addEventListener("fullscreenchange", onFullscreen);
    return () => document.removeEventListener("fullscreenchange", onFullscreen);
  }, [p.playerRef]);

  const v = p.videoRef.current;
  const progress = dur ? (time / dur) * 100 : 0;
  const bufferedProgress = dur ? Math.min(100, (buffered / dur) * 100) : 0;
  const iconButton =
    "control-button flex size-10 shrink-0 items-center justify-center rounded-full text-stone-300 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-400";
  const learningButton = (on: boolean) =>
    `learning-toggle ${on ? "is-active" : ""}`;

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await p.playerRef.current?.requestFullscreen();
    } catch {
      // Fullscreen can be denied by embedded browsers or device policy.
    }
  };

  const togglePictureInPicture = async () => {
    if (!(v instanceof HTMLVideoElement)) return;
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await v.requestPictureInPicture();
    } catch {
      // PiP support can be advertised before the media is ready.
    }
  };

  return (
    <div className="shrink-0 border-t border-white/7 bg-[#111715] px-3 pb-3 pt-2 sm:px-4">
      <div className="group relative flex h-5 items-center">
        <div className="pointer-events-none absolute inset-x-0 h-1 overflow-hidden rounded-full bg-white/10">
          <div className="absolute inset-y-0 left-0 bg-white/15" style={{ width: `${bufferedProgress}%` }} />
          <div className="absolute inset-y-0 left-0 bg-teal-400" style={{ width: `${progress}%` }} />
        </div>
        <input
          aria-label="Playback progress"
          type="range"
          min={0}
          max={dur || 1}
          step={0.1}
          value={time}
          onChange={(e) => p.onSeek(Number(e.target.value))}
          className="player-range relative z-10 w-full cursor-pointer"
        />
      </div>

      <div className="flex items-center gap-0.5">
        <button
          className={`${iconButton} mr-1 size-10 bg-white text-[#111715] hover:bg-teal-100 hover:text-[#111715]`}
          onClick={p.onTogglePlay}
          title={paused ? "Play (Space)" : "Pause (Space)"}
          aria-label={paused ? "Play" : "Pause"}
        >
          {paused ? <PlayIcon /> : <PauseIcon />}
        </button>
        <button className={iconButton} onClick={p.onPrev} title="Previous sentence (↑)" aria-label="Previous sentence">
          <PreviousIcon />
        </button>
        <button className={iconButton} onClick={p.onReplay} title="Replay sentence (R)" aria-label="Replay sentence">
          <ReplayIcon />
        </button>
        <button className={iconButton} onClick={p.onNext} title="Next sentence (↓)" aria-label="Next sentence">
          <NextIcon />
        </button>

        <div className="group/volume ml-0.5 flex items-center">
          <button
            className={iconButton}
            onClick={() => v && (v.muted = !v.muted)}
            title={muted ? "Unmute" : "Mute"}
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted || volume === 0 ? <MutedIcon /> : <VolumeIcon />}
          </button>
          <input
            aria-label="Volume"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={muted ? 0 : volume}
            onChange={(e) => {
              if (!v) return;
              v.muted = false;
              v.volume = Number(e.target.value);
            }}
            className="volume-range hidden w-16 cursor-pointer sm:block"
          />
        </div>

        <span className="ml-2 hidden text-xs tabular-nums text-stone-400 sm:inline">
          <span className="text-stone-200">{fmtTime(time)}</span> / {fmtTime(dur)}
        </span>
        <span className="grow" />

        <button className={`${iconButton} hidden sm:flex`} onClick={p.onCycleRate} title="Playback speed ([ ])">
          <span className="text-xs font-semibold">{p.rate}×</span>
        </button>
        {document.pictureInPictureEnabled && v instanceof HTMLVideoElement && (
          <button
            className={`${iconButton} hidden sm:flex`}
            onClick={() => void togglePictureInPicture()}
            title="Picture in picture"
            aria-label="Picture in picture"
          >
            <PictureInPictureIcon />
          </button>
        )}
        <button className={iconButton} onClick={() => void toggleFullscreen()} title="Fullscreen" aria-label="Fullscreen">
          {isFullscreen ? <MinimizeIcon /> : <FullscreenIcon />}
        </button>
      </div>

      <div className="mt-2 flex items-center gap-2 overflow-x-auto border-t border-white/7 pt-2 scrollbar-none">
        <span className="mr-1 hidden shrink-0 text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-500 md:inline">
          Learning mode
        </span>
        <button className={learningButton(p.loop)} onClick={p.onToggleLoop} title="Loop sentence (L)">
          <ReplayIcon small /> <span>Loop</span>
        </button>
        <button className={learningButton(p.pauseAfter)} onClick={p.onTogglePauseAfter} title="Pause after each sentence (M)">
          <PauseAfterIcon /> <span>Auto-pause</span>
        </button>
        <button className={learningButton(p.mode !== "off")} onClick={p.onCycleMode} title="Cycle subtitles (S)">
          <SubtitlesIcon />
          <span>{p.mode === "off" ? "Subtitles off" : p.mode === "zh" ? "中文" : "中文 + English"}</span>
        </button>
        <button className={learningButton(p.pinyin)} onClick={p.onTogglePinyin} title="Show pinyin (P)">
          <span className="font-zh text-sm font-semibold">拼</span> <span>Pinyin</span>
        </button>
        <button className={learningButton(p.traditional)} onClick={p.onToggleTraditional} title="Use traditional characters">
          <span className="font-zh text-sm font-semibold">繁</span> <span>Traditional</span>
        </button>
        {p.onToggleDictation && (
          <button className={learningButton(!!p.dictation)} onClick={p.onToggleDictation} title="Dictation practice: type what you hear">
            <PencilIcon /> <span>Dictation</span>
          </button>
        )}
        <button className={`${learningButton(false)} sm:hidden`} onClick={p.onCycleRate} title="Playback speed">
          <span>{p.rate}× speed</span>
        </button>
      </div>
    </div>
  );
}

function Icon({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={`size-[18px] ${className}`} aria-hidden="true">{children}</svg>;
}

function PlayIcon() { return <svg viewBox="0 0 24 24" fill="currentColor" className="ml-0.5 size-4" aria-hidden="true"><path d="M7.5 4.8v14.4L19 12 7.5 4.8Z" /></svg>; }
function PauseIcon() { return <svg viewBox="0 0 24 24" fill="currentColor" className="size-4" aria-hidden="true"><path d="M6.5 5h4v14h-4zM13.5 5h4v14h-4z" /></svg>; }
function PreviousIcon() { return <Icon><path d="m15 18-6-6 6-6" /><path d="M6 6v12" /></Icon>; }
function NextIcon() { return <Icon><path d="m9 18 6-6-6-6" /><path d="M18 6v12" /></Icon>; }
function ReplayIcon({ small = false }: { small?: boolean }) { return <Icon className={small ? "size-3.5" : ""}><path d="M3.5 9a9 9 0 1 1-.2 5" /><path d="M3.5 4v5h5" /></Icon>; }
function VolumeIcon() { return <Icon><path d="M11 5 6 9H3v6h3l5 4V5Z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18 6a8.5 8.5 0 0 1 0 12" /></Icon>; }
function MutedIcon() { return <Icon><path d="M11 5 6 9H3v6h3l5 4V5Z" /><path d="m16 9 5 5M21 9l-5 5" /></Icon>; }
function FullscreenIcon() { return <Icon><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /></Icon>; }
function MinimizeIcon() { return <Icon><path d="M3 8h5V3M21 8h-5V3M3 16h5v5M21 16h-5v5" /></Icon>; }
function PictureInPictureIcon() { return <Icon><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M13 12h6v5h-6z" /></Icon>; }
function PauseAfterIcon() { return <Icon><path d="M6.5 7v10M10.5 7v10" /><path d="M15 8.5h4v7h-4z" /></Icon>; }
function PencilIcon() { return <Icon className="size-3.5"><path d="M17 3.5 20.5 7 8 19.5l-4.5 1 1-4.5L17 3.5Z" /></Icon>; }
function SubtitlesIcon() { return <Icon><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 11h4M7 15h3M13 15h4" /></Icon>; }

function fmtTime(sec: number): string {
  if (!Number.isFinite(sec)) return "0:00";
  const s = Math.floor(sec);
  const hours = Math.floor(s / 3600);
  const mins = Math.floor((s % 3600) / 60);
  const seconds = String(s % 60).padStart(2, "0");
  return hours ? `${hours}:${String(mins).padStart(2, "0")}:${seconds}` : `${mins}:${seconds}`;
}
