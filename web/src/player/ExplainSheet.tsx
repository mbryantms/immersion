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

interface Props {
  sentence: SentenceOut;
  onClose: () => void;
}

/** On-demand AI breakdown of one sentence: gist, chunk-by-chunk roles, grammar
 *  notes. Cached server-side per zh text; provenance always shown. */
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
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-zh text-lg leading-relaxed">{sentence.zh}</DialogTitle>
          {sentence.en && <DialogDescription>{sentence.en}</DialogDescription>}
        </DialogHeader>

        {error && (
          <p className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-sm text-red-300">
            {error.includes("503") ? "AI provider is unavailable right now." : error}
          </p>
        )}
        {!result && !error && (
          <div className="space-y-2">
            <Skeleton className="h-5 w-4/5" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-12 w-2/3" />
          </div>
        )}
        {result && (
          <div className="space-y-4">
            <p className="text-sm leading-relaxed text-stone-200">{result.gist}</p>

            <div className="space-y-1.5">
              {result.chunks.map((chunk, i) => (
                <div key={i} className="flex items-baseline gap-3 rounded-lg bg-white/[0.03] px-3 py-2">
                  <span className="font-zh shrink-0 text-[15px] text-teal-200">{chunk.zh}</span>
                  <span className="text-xs leading-relaxed text-stone-400">{chunk.note}</span>
                </div>
              ))}
            </div>

            {result.points.length > 0 && (
              <ul className="space-y-1 text-xs leading-relaxed text-stone-300">
                {result.points.map((point, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-teal-500">•</span>
                    {point}
                  </li>
                ))}
              </ul>
            )}

            <Badge variant="secondary" className="text-[10px] text-muted-foreground">
              AI · {result.model ?? result.provider}
            </Badge>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
