import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchExportPreview, startExport } from "../api/queries";
import type { ExportPreview } from "../api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import ExportBatchStatus from "./ExportBatchStatus";
import { forgetExport, rememberExport, type ExportRequest } from "./exportRequests";

type Row = { include: boolean; allowDuplicate: boolean; media: boolean; meaning: string };
export default function ExportTray({ savedItemIds, onClose }: { savedItemIds: number[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [rows, setRows] = useState<Record<number, Row>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [jobId, setJobId] = useState<number | null>(null);
  const [pending, setPending] = useState<ExportRequest | null>(null);
  const alive = useRef(false);
  const inFlight = useRef(false);
  useEffect(() => {
    alive.current = true; let cancelled = false;
    setPreview(null); setError(null);
    void fetchExportPreview(savedItemIds).then((data) => {
      if (cancelled) return;
      const initial: Record<number, Row> = {};
      for (const item of data.items) initial[item.saved_item_id] = { include: !item.already_exported && !item.duplicates && !item.errors.length, allowDuplicate: false, media: item.can_clip, meaning: item.fields.Meaning ?? "" };
      setRows(initial); setPreview(data);
    }).catch((value: Error) => { if (!cancelled) setError(value.message); });
    return () => { cancelled = true; alive.current = false; };
  }, [savedItemIds, reload]);
  const submit = async () => {
    if (inFlight.current || !preview) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const request: ExportRequest = pending ?? { request_uuid: crypto.randomUUID(), profile_hash: preview.profile_hash, created_at: new Date().toISOString(), entries: preview.items.filter((item) => rows[item.saved_item_id].include).map((item) => ({ saved_item_id: item.saved_item_id, source_hash: item.source_hash, meaning: rows[item.saved_item_id].meaning, allow_duplicate: rows[item.saved_item_id].allowDuplicate, include_media: rows[item.saved_item_id].media })) };
      // Persist the exact UUID/payload before sending; an ambiguous reply can
      // be retried after close/reload without submitting a different export.
      try { rememberExport(request); } catch { throw new Error("Your browser could not save the submission reminder. Allow storage or free space, then retry. Nothing was sent."); }
      setPending(request);
      const accepted = await startExport(request.entries, request.profile_hash, request.request_uuid);
      try { forgetExport(request.request_uuid); } catch { /* Replaying a retained reminder is idempotent. */ }
      if (alive.current) { setJobId(accepted.job_id); setPending(null); }
      void queryClient.invalidateQueries({ queryKey: ["anki-exports"] });
      void queryClient.invalidateQueries({ queryKey: ["anki-inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (value) { if (alive.current) setError(value instanceof Error ? value.message : "Export was not confirmed"); }
    finally { inFlight.current = false; if (alive.current) setBusy(false); }
  };
  const count = Object.values(rows).filter((row) => row.include).length;
  return <Dialog open onOpenChange={(open) => !open && onClose()}><DialogContent className="flex max-h-[88dvh] flex-col overflow-hidden sm:max-w-3xl"><DialogHeader><DialogTitle>Export to Anki</DialogTitle><DialogDescription className="break-words">{preview ? `Deck: ${preview.deck} · note type: ${preview.model}. Review the selected meanings and available source audio before sending.` : "Checking settings, source context and duplicates in Anki…"}</DialogDescription></DialogHeader>
    <div className="min-h-0 space-y-4 overflow-y-auto px-1 pb-1">
      {error && <div role="alert" className="space-y-2 rounded-lg border border-amber-400/30 p-3 text-sm text-amber-200"><p>{error}</p><p>{pending ? "The reply was not confirmed. Retry the same submission, or use the export inbox after closing. Accepted exports remain there." : "Your cards are retained. Open Anki, check Settings or refresh the preview."}</p></div>}
      {jobId ? <ExportBatchStatus jobId={jobId} /> : preview ? <>
        {preview.preflight.errors.map((message) => <p key={message} role="alert" className="text-sm text-amber-200">{message}</p>)}
        {preview.preflight.warnings.map((message) => <p key={message} className="text-xs text-muted-foreground">{message}</p>)}
        {!preview.preflight.ok && <Button asChild variant="outline" className="min-h-11"><Link to="/settings">Open Anki export setup</Link></Button>}
        {preview.items.map((item) => { const row = rows[item.saved_item_id]; const blocked = !!item.already_exported || !!item.errors.length;
          return <section key={item.saved_item_id} aria-label={`Export preview for ${item.fields.Simplified}`} className="space-y-3 rounded-xl border border-border bg-muted/20 p-4"><label className="flex min-h-11 flex-wrap items-center gap-3 text-base"><input type="checkbox" className="size-4 accent-teal-400" disabled={blocked || busy || !!pending} checked={row.include} onChange={(event) => setRows({ ...rows, [item.saved_item_id]: { ...row, include: event.target.checked } })} /><span lang="zh" className="font-zh text-lg">{item.fields.Simplified}</span><span className="text-sm text-muted-foreground">{item.fields.Pinyin}</span></label>
            {item.already_exported && <p className="text-sm text-primary">Already linked to Anki note {item.already_exported}</p>}
            {item.errors.map((message) => <p key={message} className="text-sm text-amber-200">{message}</p>)}
            <label className="block space-y-1 text-sm"><span>Meaning for {item.fields.Simplified}</span><Input className="min-h-11" maxLength={2000} disabled={blocked || busy || !!pending} value={row.meaning} onChange={(event) => setRows({ ...rows, [item.saved_item_id]: { ...row, meaning: event.target.value } })} /></label>
            {item.fields.Sentence && <p lang="zh" className="font-zh text-base leading-relaxed">{item.fields.Sentence}</p>}
            {item.fields.SentenceMeaning && <p className="text-xs text-muted-foreground">{item.fields.SentenceMeaning}</p>}
            {item.duplicates > 0 && <div className="space-y-2"><p className="text-sm text-amber-200">{item.duplicates} existing note{item.duplicates === 1 ? "" : "s"} with this Chinese text. {item.duplicate_meanings[0] && `Existing meaning: ${item.duplicate_meanings[0]}`}</p><label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="size-4 accent-teal-400" checked={row.allowDuplicate} disabled={blocked || busy || !!pending} onChange={(event) => setRows({ ...rows, [item.saved_item_id]: { ...row, allowDuplicate: event.target.checked, include: event.target.checked } })} />Add another note for {item.fields.Simplified}</label></div>}
            {item.can_clip ? <label className="flex min-h-11 items-center gap-3 text-sm"><input type="checkbox" className="size-4 accent-teal-400" checked={row.media} disabled={blocked || busy || !!pending} onChange={(event) => setRows({ ...rows, [item.saved_item_id]: { ...row, media: event.target.checked } })} />Attach available source media for {item.fields.Simplified}</label> : <p className="text-xs text-muted-foreground">Source audio is unavailable. This export uses text; recording or pronunciation accuracy is not inferred.</p>}
          </section>; })}
      </> : !error && <p role="status" className="text-sm text-muted-foreground">Preparing an export preview…</p>}
      <p className="text-xs text-muted-foreground">Closing discards unsubmitted preview edits and keeps accepted exports running. Resume their status and recovery actions in the export inbox. Exporting does not mark vocabulary mastered.</p>
    </div><DialogFooter className="shrink-0 border-t border-border pt-3"><Button className="min-h-11" variant="outline" onClick={onClose}>Close export</Button>{!jobId && !pending && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => setReload((value) => value+1)}>Refresh preview</Button>}{!jobId && preview?.preflight.ok && <Button className="min-h-11" disabled={busy || !count || Object.values(rows).some((row) => row.include && !row.meaning.trim())} onClick={() => void submit()}>{busy ? "Submitting…" : pending ? "Retry same submission" : `Export ${count} note${count === 1 ? "" : "s"}`}</Button>}</DialogFooter>
  </DialogContent></Dialog>;
}
