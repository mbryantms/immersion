import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { post } from "../api/client";
import { Button } from "../components/ui/button";
import type { StudyMode } from "./studyMode";

export default function DifficultyFeedback({ itemId, goal, position }: { itemId: number; goal: StudyMode; position: () => number }) {
  const qc = useQueryClient();
  const [savedFor, setSavedFor] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (rating: string) => post(`/items/${itemId}/difficulty`, { rating, goal, position_ms: position() }),
    onSuccess: (_data, rating) => { setSavedFor(`${goal}:${rating}`); void qc.invalidateQueries({ queryKey: ["recommendations"] }); },
  });
  return <details className="rounded-xl border border-border bg-card/60 px-4 py-2 text-sm">
    <summary className="min-h-11 cursor-pointer py-3 font-medium">How difficult is this sample?</summary>
    <p className="mb-3 text-xs leading-relaxed text-muted-foreground">After a minute or two, rate your {goal === "read" ? "reading" : goal === "listen" ? "listening" : "dictation"} experience. Your rating helps rank this episode. It is separate from vocabulary marks.</p>
    <div className="flex flex-wrap gap-2">{[["too_easy", "Too easy"], ["manageable", "Manageable"], ["too_hard", "Too hard"]].map(([rating, label]) => <Button className="min-h-11" key={rating} variant={savedFor === `${goal}:${rating}` ? "default" : "outline"} disabled={save.isPending} aria-pressed={savedFor === `${goal}:${rating}`} onClick={() => save.mutate(rating)}>{label}</Button>)}</div>
    {savedFor?.startsWith(`${goal}:`) && <p role="status" className="mt-3 text-xs text-primary">Rating saved for {goal === "dictate" ? "dictation" : goal === "read" ? "reading" : "listening"}.</p>}
    {save.isError && <p role="alert" className="mt-3 text-xs text-destructive">Rating could not be saved. Try again.</p>}
  </details>;
}
