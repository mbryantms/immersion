import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import ArtifactFeedback from "./ArtifactFeedback";
import { ApiError } from "../api/client";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { explainSentence, explainSentenceExtras } from "../api/queries";
import type { ExplainCore, ExplainExtras, SentenceOut } from "../api/types";
import { posLabel } from "../lib/pos";

interface Props {
  sentence: SentenceOut;
  onClose: () => void;
}

/** Explicit, cancellable AI assistance. Dictionary facts remain separate. */
export default function ExplainSheet({ sentence, onClose }: Props) {
  const [result, setResult] = useState<ExplainCore | null>(null);
  const [extras, setExtras] = useState<ExplainExtras | null>(null);
  const [extrasLoading, setExtrasLoading] = useState(false);
  const [extrasError, setExtrasError] = useState<Error | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const next = new AbortController(); controller.current = next;
    setResult(null); setExtras(null); setError(null); setFailure(null); setExtrasError(null); setExtrasLoading(false);
    explainSentence(sentence.id, { signal: next.signal })
      .then((value) => { if (!next.signal.aborted) setResult(value); })
      .catch((value: Error) => { if (!next.signal.aborted) { setFailure(value); setError(value instanceof ApiError && value.status === 409 && typeof value.detail === "object" && value.detail !== null && "artifact_id" in value.detail ? "This explanation was rejected." : value.message); } });
    return () => next.abort();
  }, [sentence.id, sentence.provenance?.revision, attempt]);
  const more = () => {
    const signal = controller.current?.signal;
    setExtrasLoading(true); setExtrasError(null);
    void explainSentenceExtras(sentence.id, { signal }).then((value) => { if (!signal?.aborted) setExtras(value); })
      .catch((value: Error) => { if (!signal?.aborted) setExtrasError(value); })
      .finally(() => { if (!signal?.aborted) setExtrasLoading(false); });
  };
  const rejectedId = (value: Error | null) => value instanceof ApiError && typeof value.detail === "object" && value.detail !== null && "artifact_id" in value.detail ? Number(value.detail.artifact_id) : undefined;
  const coreRejected = rejectedId(failure);
  const extrasRejected = rejectedId(extrasError);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-zh text-lg leading-relaxed">{sentence.zh}</DialogTitle>
          <DialogDescription className="space-y-0.5">
            {result?.pinyin && <span className="block text-[13px] text-stone-400">{result.pinyin}</span>}
            {sentence.en && <span className="block text-xs text-muted-foreground">{sentence.en}</span>}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-sm text-red-300">
            {error.includes("503") ? "AI provider is unavailable right now." : error}
          </p>
        )}
        {coreRejected && <ArtifactFeedback artifactId={coreRejected} sentenceId={sentence.id} rejected onRetry={() => setAttempt((value) => value + 1)} />}
        {error && !coreRejected && <Button variant="outline" onClick={() => setAttempt((value) => value + 1)}>Try explanation again</Button>}
        {!result && !error && (
          <div className="space-y-2">
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-2/3" />
            <p className="text-[11px] text-muted-foreground">First look at this sentence — thinking it through…</p>
          </div>
        )}
        {result && (
          <div className="space-y-5">
            {/* translations */}
            <div className="space-y-1">
              <p className="text-sm leading-relaxed text-stone-100">{result.natural}</p>
              {result.literal && (
                <p className="text-xs italic leading-relaxed text-muted-foreground">lit. {result.literal}</p>
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
                    <div key={i} className="rounded-lg bg-white/3 px-3 py-2">
                      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                        <span className="font-zh text-base text-teal-200">{word.zh}</span>
                        {word.py && <span className="text-[11px] text-muted-foreground">{word.py}</span>}
                        {word.pos && <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{posLabel(word.pos)}</span>}
                        {word.hsk && <span className="text-[10px] text-teal-500/80">HSK {word.hsk}</span>}
                      </div>
                      <p className="mt-0.5 text-xs leading-relaxed text-stone-400">{word.role}</p>
                      {word.defs && word.defs.length > 0 && (
                        <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{word.defs.join(" · ")}</p>
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
                    <div key={i} className="flex items-baseline gap-3 rounded-lg bg-white/3 px-3 py-2">
                      <span className="font-zh shrink-0 text-base text-violet-300">{particle.zh}</span>
                      <span className="text-xs leading-relaxed text-stone-400">{particle.note}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {!extras && !extrasLoading && !extrasRejected && <Button variant="outline" className="min-h-11" onClick={more}>Request more detail</Button>}
            {extrasLoading && <p role="status" className="text-sm text-muted-foreground">Generating optional pronunciation notes and examples…</p>}
            {extrasError && <p role="alert" className="text-sm text-amber-200">More detail is unavailable. {extrasRejected ? "This artifact was rejected." : extrasError.message}</p>}
            {extrasRejected && <ArtifactFeedback artifactId={extrasRejected} label="extra detail" sentenceId={sentence.id} rejected onRetry={more} />}
            {extras && (
              <>
                <ArtifactFeedback artifactId={extras.artifact_id} label="extra detail" sentenceId={sentence.id} onReject={() => { setExtras(null); setExtrasError(new ApiError(409, { artifact_id: extras.artifact_id }, "Artifact rejected")); }} onRetry={more} />
                {extras.pronunciation.length > 0 && (
                  <Section label="Pronunciation">
                    <BulletList items={extras.pronunciation} />
                  </Section>
                )}

                {extras.nuance && (
                  <Section label="Nuance">
                    <p className="text-xs leading-relaxed text-stone-300">{extras.nuance}</p>
                  </Section>
                )}

                {extras.variations.length > 0 && (
                  <Section label="Other ways to say it">
                    <div className="space-y-1">
                      {extras.variations.map((variation, i) => (
                        <div key={i} className="rounded-lg bg-white/3 px-3 py-2">
                          <p className="font-zh text-base text-stone-100">{variation.zh}</p>
                          <p className="text-[11px] text-muted-foreground">{variation.py}</p>
                          <p className="mt-0.5 text-xs text-stone-400">{variation.note}</p>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {extras.pattern?.examples && extras.pattern.examples.length > 0 && (
                  <Section label={`Pattern${extras.pattern.name ? ` · ${extras.pattern.name}` : ""}`}>
                    <div className="space-y-1">
                      {extras.pattern.examples.map((example, i) => (
                        <div key={i} className="rounded-lg bg-white/3 px-3 py-2">
                          <p className="font-zh text-base text-stone-100">{example.zh}</p>
                          <p className="text-[11px] text-muted-foreground">{example.py}</p>
                          <p className="mt-0.5 text-xs text-stone-400">{example.en}</p>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {extras.mistakes.length > 0 && (
                  <Section label="Watch out for">
                    <BulletList items={extras.mistakes} accent="text-amber-300" />
                  </Section>
                )}
              </>
            )}

            <p className="text-xs text-muted-foreground">Structure and source-token checks passed. AI meaning, grammar and pronunciation notes can still be wrong; they do not count as learning evidence.</p>
            <ArtifactFeedback artifactId={result.artifact_id} sentenceId={sentence.id} onReject={() => { controller.current?.abort(); setExtras(null); setResult(null); setFailure(new ApiError(409, { artifact_id: result.artifact_id }, "Artifact rejected")); setError("This explanation was rejected."); }} onRetry={() => setAttempt((value) => value + 1)} />
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
      <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</h3>
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
