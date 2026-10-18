import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, patch } from "../api/client";
import type { Word } from "../api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

type Detail = {
  revision: number;
  source: { zh: string; en: string | null; t0_ms: number; t1_ms: number };
  current: { zh: string; en: string | null; t0_ms: number; t1_ms: number; words: Word[] };
  history: { revision: number; action: string; created_at: string }[];
};

export default function CorrectionEditor({ sentenceId, itemId, onClose }: { sentenceId: number; itemId: number; onClose: () => void }) {
  const client = useQueryClient();
  const key = ["corrections", sentenceId];
  const query = useQuery({ queryKey: key, queryFn: () => get<Detail>(`/sentences/${sentenceId}/corrections`), staleTime: Infinity });
  const [zh, setZh] = useState("");
  const [en, setEn] = useState("");
  const [start, setStart] = useState(0);
  const [end, setEnd] = useState(0);
  const [edits, setEdits] = useState<Record<number, { reading?: string; meaning?: string }>>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const returnFocus = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  useEffect(() => {
    if (!query.data) return;
    const current = query.data.current;
    setZh(current.zh); setEn(current.en ?? ""); setStart(current.t0_ms / 1000); setEnd(current.t1_ms / 1000);
    setEdits({});
  }, [query.data]);
  const submit = async (action?: { reset?: boolean; restore_revision?: number }) => {
    if (!query.data || busy.current) return;
    busy.current = true; setPending(true); setError("");
    try {
      const current = query.data.current;
      const updates: Record<string, unknown> = { expected_revision: query.data.revision };
      if (action) Object.assign(updates, action);
      else {
        if (zh !== current.zh) updates.zh = zh;
        if (en !== (current.en ?? "")) updates.en = en || null;
        if (start * 1000 !== current.t0_ms) updates.t0_ms = Math.round(start * 1000);
        if (end * 1000 !== current.t1_ms) updates.t1_ms = Math.round(end * 1000);
        if (zh === current.zh && Object.keys(edits).length) updates.words = Object.entries(edits).map(([position, values]) => ({ start: Number(position), ...values }));
        if (Object.keys(updates).length === 1) { setError("Change a field before saving."); return; }
      }
      const result = await patch<Detail>(`/sentences/${sentenceId}/corrections`, updates);
      client.setQueryData(key, result);
      await client.invalidateQueries({ queryKey: ["item", itemId] });
      await Promise.all(["sentences", "item", "knowledge", "saved", "review-queue", "search", "concordance", "dashboard", "recommendations"].map((name) => client.invalidateQueries({ queryKey: [name] })));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save the correction."); }
    finally { busy.current = false; setPending(false); }
  };
  return <Dialog open onOpenChange={(open) => { if (!open && !pending) onClose(); }}>
    <DialogContent onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }} className="flex max-h-[90dvh] flex-col sm:max-w-2xl" onInteractOutside={(event) => { if (pending) event.preventDefault(); }}>
      <DialogTitle>Correct this line</DialogTitle>
      <DialogDescription>Keep a local correction and its history. The original subtitle file stays intact.</DialogDescription>
      {query.isPending ? <p role="status">Loading line history…</p> : query.isError ? <div role="alert"><p>Could not load this line.</p><Button onClick={() => query.refetch()}>Retry loading</Button></div> : query.data && <form className="flex min-h-0 flex-col gap-4" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
          <p className="text-xs text-muted-foreground">Revision {query.data.revision}. Local word analysis uses the dictionary; check names and ambiguous readings.</p>
          <label className="block space-y-1">Chinese text<textarea aria-label="Chinese text" required maxLength={2000} value={zh} onChange={(event) => setZh(event.target.value)} className="min-h-20 w-full rounded-md border border-border bg-background p-3 font-zh text-lg" /></label>
          <label className="block space-y-1">English meaning<textarea aria-label="English meaning" maxLength={4000} value={en} onChange={(event) => setEn(event.target.value)} className="min-h-16 w-full rounded-md border border-border bg-background p-3" /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">Start (seconds)<Input aria-label="Source start in seconds" className="min-h-11" type="number" min={0} step={0.001} value={start} onChange={(event) => setStart(Number(event.target.value))} /></label>
            <label className="space-y-1">End (seconds)<Input aria-label="Source end in seconds" className="min-h-11" type="number" min={0} step={0.001} value={end} onChange={(event) => setEnd(Number(event.target.value))} /></label>
          </div>
          <p className="text-xs text-muted-foreground">Times use the subtitle track clock. Your subtitle sync adjustment is applied during playback.</p>
          <details>
            <summary className="min-h-11 cursor-pointer py-3 font-medium">Word readings and meanings</summary>
            {zh !== query.data.current.zh ? <p className="text-sm text-muted-foreground">Save the Chinese text first, then correct its new words. Changing Chinese also clears the English translation unless you edit its meaning.</p> : <div className="space-y-3">{query.data.current.words.filter((word) => word.type === "zh" && word.start !== undefined).map((word) => <fieldset key={word.start} className="rounded-lg border border-border p-3">
              <legend className="px-1 font-zh">{word.t} · character {(word.start ?? 0) + 1}</legend>
              <label className="block space-y-1 text-xs">Reading (numbered pinyin)<Input aria-label={`Reading for ${word.t} at character ${(word.start ?? 0) + 1}`} value={edits[word.start!]?.reading ?? word.reading ?? ""} placeholder="yin2 hang2" onChange={(event) => setEdits((previous) => ({ ...previous, [word.start!]: { ...previous[word.start!], reading: event.target.value } }))} /></label>
              <label className="mt-2 block space-y-1 text-xs">Meaning in this line<Input aria-label={`Meaning for ${word.t} at character ${(word.start ?? 0) + 1}`} value={edits[word.start!]?.meaning ?? word.meaning ?? ""} onChange={(event) => setEdits((previous) => ({ ...previous, [word.start!]: { ...previous[word.start!], meaning: event.target.value } }))} /></label>
            </fieldset>)}</div>}
          </details>
          <details><summary className="min-h-11 cursor-pointer py-3 font-medium">Original source and correction history</summary>
            <p lang="zh" className="font-zh text-base">{query.data.source.zh}</p>
            {query.data.source.en && <p className="mt-1 text-muted-foreground">{query.data.source.en}</p>}
            <p className="mt-1 text-xs text-muted-foreground">{query.data.source.t0_ms / 1000}–{query.data.source.t1_ms / 1000} seconds</p>
            <ul className="mt-3 space-y-2">{query.data.history.map((revision) => <li key={revision.revision} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-2"><span>Revision {revision.revision} · {revision.action}</span><Button className="min-h-11" type="button" variant="secondary" disabled={pending} onClick={() => submit({ restore_revision: revision.revision })}>Restore revision {revision.revision}</Button></li>)}</ul>
          </details>
        </div>
        {error && <div role="alert" className="text-sm text-amber-200"><p>{error}</p><Button className="min-h-11" type="button" variant="ghost" disabled={pending} onClick={() => { setError(""); query.refetch(); }}>Reload latest line</Button></div>}
        <div className="flex shrink-0 flex-wrap gap-2 border-t border-border pt-3">
          <Button className="min-h-11" type="submit" disabled={pending}>{pending ? "Saving correction…" : "Save correction"}</Button>
          <Button className="min-h-11" type="button" variant="secondary" disabled={pending || query.data.revision === 0} onClick={() => submit({ reset: true })}>Reset to source</Button>
          <Button className="min-h-11" type="button" variant="ghost" disabled={pending} onClick={onClose}>Done</Button>
        </div>
      </form>}
    </DialogContent>
  </Dialog>;
}
