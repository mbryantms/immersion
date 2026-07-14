// Per-character stroke-order animation (hanzi-writer / Make-Me-a-Hanzi data,
// served from /hanzi-data). Click a character to replay its animation.

import { useEffect, useRef, useState } from "react";
import HanziWriter from "hanzi-writer";

const dataCache = new Map<string, Promise<unknown>>();

function loadCharData(char: string): Promise<unknown> {
  let p = dataCache.get(char);
  if (!p) {
    p = fetch(`/hanzi-data/${encodeURIComponent(char)}.json`).then((r) => {
      if (!r.ok) throw new Error("no stroke data");
      return r.json();
    });
    dataCache.set(char, p);
  }
  return p;
}

export default function CharacterStrokes({ word }: { word: string }) {
  const chars = [...word].filter((ch) => /[㐀-鿿]/.test(ch));
  if (!chars.length) return null;
  return (
    <div className="flex flex-wrap gap-3">
      {chars.map((ch, i) => (
        <SingleChar key={`${ch}-${i}`} char={ch} />
      ))}
    </div>
  );
}

function SingleChar({ char }: { char: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const writer = useRef<HanziWriter | null>(null);
  const [strokes, setStrokes] = useState<number | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadCharData(char)
      .then((data) => {
        if (cancelled || !ref.current) return;
        setStrokes((data as { strokes: unknown[] }).strokes.length);
        ref.current.innerHTML = "";
        writer.current = HanziWriter.create(ref.current, char, {
          width: 88,
          height: 88,
          padding: 4,
          strokeColor: "#e7e5e4",
          radicalColor: "#2dd4bf",
          outlineColor: "#44403c",
          delayBetweenStrokes: 120,
          strokeAnimationSpeed: 1.2,
          charDataLoader: (c, onComplete) => {
            void loadCharData(c).then((d) => onComplete(d as never));
          },
        });
        writer.current.animateCharacter();
      })
      .catch(() => !cancelled && setMissing(true));
    return () => {
      cancelled = true;
    };
  }, [char]);

  if (missing) {
    return (
      <div className="flex h-28 w-24 flex-col items-center justify-center rounded-xl border border-white/7 bg-white/[0.03]">
        <span className="font-zh text-3xl text-stone-300">{char}</span>
        <span className="mt-1 text-[10px] text-stone-600">no stroke data</span>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => writer.current?.animateCharacter()}
      className="flex flex-col items-center rounded-xl border border-white/7 bg-white/[0.03] p-2 transition hover:border-teal-400/40"
      title={`Replay stroke order for ${char}`}
    >
      <div ref={ref} className="size-[88px]" />
      <span className="mt-1 text-[10px] tabular-nums text-stone-500">
        {strokes != null ? `${strokes} strokes` : "…"}
      </span>
    </button>
  );
}
