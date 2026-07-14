// Podcast surface for the shared player shell: cover-art stage + <audio>,
// with the same SubtitleOverlay the video surface uses (passed as children).

import type { MediaEl } from "./useSentenceClock";

interface Props {
  mediaRef: React.RefObject<MediaEl | null>;
  src: string;
  cover: string;
  title: string;
  seriesTitle?: string | null;
  onTogglePlay: () => void;
  children?: React.ReactNode; // SubtitleOverlay
}

export default function AudioSurface({ mediaRef, src, cover, title, seriesTitle, onTogglePlay, children }: Props) {
  return (
    <div
      className="video-stage relative flex min-h-[220px] items-center justify-center overflow-hidden bg-black sm:min-h-[360px] xl:min-h-0 xl:flex-1"
      onClick={onTogglePlay}
    >
      <img src={cover} alt="" className="pointer-events-none absolute inset-0 h-full w-full scale-110 object-cover opacity-25 blur-3xl" />
      <div className="pointer-events-none absolute inset-0 bg-black/50" />
      <div className="pointer-events-none relative flex flex-col items-center gap-4 px-6 py-10 sm:py-14">
        <img
          src={cover}
          alt=""
          className="size-36 rounded-2xl border border-white/10 object-cover shadow-2xl shadow-black/50 sm:size-48"
        />
        <div className="max-w-md text-center">
          {seriesTitle && (
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-400">{seriesTitle}</p>
          )}
          <p className="mt-1 line-clamp-2 font-zh text-sm text-stone-200">{title}</p>
        </div>
      </div>
      <audio
        ref={(el) => {
          mediaRef.current = el;
        }}
        src={src}
        preload="metadata"
      />
      {children}
    </div>
  );
}
