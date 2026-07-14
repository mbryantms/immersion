import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { explainSentence } from "../api/queries";
import type { ExplainResult, SentenceOut } from "../api/types";
import { posLabel } from "../lib/pos";

interface Props {
  sentence: SentenceOut;
  onClose: () => void;
}

/** On-demand deep dive into one sentence. Pinyin, HSK levels, POS, and
 *  dictionary glosses come from the app's own analysis/lexicon; the AI layer
 *  (grounded on that tokenization) adds translations, structure, particle
 *  logic, pronunciation notes, register variations, pattern examples, and
 *  pitfalls. Provenance always shown. */
export default function ExplainSheet({ sentence, onClose }: Props) {
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    explainSentence(sentence.id)
      .then((r) => !cancelled && setResult(r))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [sentence.id]);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-zh text-lg leading-relaxed">{sentence.zh}</DialogTitle>
          <DialogDescription className="space-y-0.5">
            {result?.pinyin && <span className="block text-[13px] text-stone-400">{result.pinyin}</span>}
            {sentence.en && <span className="block text-xs text-stone-500">{sentence.en}</span>}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-sm text-red-300">
            {error.includes("503") ? "AI provider is unavailable right now." : error}
          </p>
        )}
        {!result && !error && (
          <div className="space-y-2">
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-2/3" />
            <p className="text-[11px] text-stone-600">First look at this sentence — thinking it through…</p>
          </div>
        )}
        {result && (
          <div className="space-y-5">
            {/* translations */}
            <div className="space-y-1">
              <p className="text-sm leading-relaxed text-stone-100">{result.natural}</p>
              {result.literal && (
                <p className="text-xs italic leading-relaxed text-stone-500">lit. {result.literal}</p>
              )}
              <div className="flex flex-wrap gap-1.5 pt-1">
                {result.hsk.level && (
                  <Badge variant="secondary" className="text-[10px] text-teal-300">HSK {result.hsk.level}</Badge>
                )}
                {result.hsk.offlist.map((word) => (
                  <Badge key={word} variant="secondary" className="font-zh text-[10px] text-amber-300/80" title="Beyond the HSK lists">
                    {word} · off-list
                  </Badge>
                ))}
              </div>
            </div>

            {result.structure && (
              <Section label="Structure">
                <p className="text-xs leading-relaxed text-stone-300">{result.structure}</p>
              </Section>
            )}

            {result.words.length > 0 && (
              <Section label="Word by word">
                <div className="space-y-1">
                  {result.words.map((word, i) => (
                    <div key={i} className="rounded-lg bg-white/[0.03] px-3 py-2">
                      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                        <span className="font-zh text-[15px] text-teal-200">{word.zh}</span>
                        {word.py && <span className="text-[11px] text-stone-500">{word.py}</span>}
                        {word.pos && <span className="text-[10px] uppercase tracking-wide text-stone-600">{posLabel(word.pos)}</span>}
                        {word.hsk && <span className="text-[10px] text-teal-500/80">HSK {word.hsk}</span>}
                      </div>
                      <p className="mt-0.5 text-xs leading-relaxed text-stone-400">{word.role}</p>
                      {word.defs && word.defs.length > 0 && (
                        <p className="mt-0.5 text-[11px] leading-relaxed text-stone-600">{word.defs.join(" · ")}</p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {result.particles.length > 0 && (
              <Section label="Particles & function words">
                <div className="space-y-1">
                  {result.particles.map((particle, i) => (
                    <div key={i} className="flex items-baseline gap-3 rounded-lg bg-white/[0.03] px-3 py-2">
                      <span className="font-zh shrink-0 text-[15px] text-violet-300">{particle.zh}</span>
                      <span className="text-xs leading-relaxed text-stone-400">{particle.note}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {result.pronunciation.length > 0 && (
              <Section label="Pronunciation">
                <BulletList items={result.pronunciation} />
              </Section>
            )}

            {result.nuance && (
              <Section label="Nuance">
                <p className="text-xs leading-relaxed text-stone-300">{result.nuance}</p>
              </Section>
            )}

            {result.variations.length > 0 && (
              <Section label="Other ways to say it">
                <div className="space-y-1">
                  {result.variations.map((variation, i) => (
                    <div key={i} className="rounded-lg bg-white/[0.03] px-3 py-2">
                      <p className="font-zh text-[15px] text-stone-100">{variation.zh}</p>
                      <p className="text-[11px] text-stone-500">{variation.py}</p>
                      <p className="mt-0.5 text-xs text-stone-400">{variation.note}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {result.pattern?.examples && result.pattern.examples.length > 0 && (
              <Section label={`Pattern${result.pattern.name ? ` · ${result.pattern.name}` : ""}`}>
                <div className="space-y-1">
                  {result.pattern.examples.map((example, i) => (
                    <div key={i} className="rounded-lg bg-white/[0.03] px-3 py-2">
                      <p className="font-zh text-[15px] text-stone-100">{example.zh}</p>
                      <p className="text-[11px] text-stone-500">{example.py}</p>
                      <p className="mt-0.5 text-xs text-stone-400">{example.en}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {result.mistakes.length > 0 && (
              <Section label="Watch out for">
                <BulletList items={result.mistakes} accent="text-amber-500" />
              </Section>
            )}

            <Badge variant="secondary" className="text-[10px] text-muted-foreground">
              AI · {result.model ?? result.provider} — pinyin & HSK from dictionary data
            </Badge>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-stone-500">{label}</h3>
      {children}
    </section>
  );
}

function BulletList({ items, accent = "text-teal-500" }: { items: string[]; accent?: string }) {
  return (
    <ul className="space-y-1 text-xs leading-relaxed text-stone-300">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2">
          <span className={accent}>•</span>
          {item}
        </li>
      ))}
    </ul>
  );
}
