import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post, put } from "../api/client";
import { startExport } from "../api/queries";
import type { ExportBatch, ExportInbox } from "../anki-types";
import { Page, PageHeader } from "../components/layout/Page";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import ExportTray from "../saved/ExportTray";
import { forgetExport, pendingExports, type ExportRequest } from "../saved/exportRequests";
import { statusLabel } from "../saved/ExportBatchStatus";

export default function ExportPage() {
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const requestedAttempt = Number(params.get("attempt")) || null;
  const [historyCursor, setHistoryCursor] = useState<number | null>(null);
  const focusedAttempt = useRef<number | null>(null);
  const [view, setView] = useState<"ready" | "deferred">("ready");
  const [cursor, setCursor] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [tray, setTray] = useState<number[] | null>(null);
  const [pending, setPending] = useState<ExportRequest[]>([]);
  const [storageError, setStorageError] = useState(false);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<Set<number>>(new Set());
  const retryIds = useRef<Record<string, string>>({});
  const inbox = useQuery({ queryKey: ["anki-inbox", view, cursor], queryFn: () => get<ExportInbox>(`/anki/inbox?view=${view}${cursor ? `&before_id=${cursor}` : ""}`), refetchInterval: 5000 });
  const history = useQuery({ queryKey: ["anki-exports", historyCursor, requestedAttempt], queryFn: () => get<{ batches: ExportBatch[]; next_cursor: number | null }>(`/anki/exports?${historyCursor ? `before_job_id=${historyCursor}&` : ""}${requestedAttempt ? `include_attempt_id=${requestedAttempt}` : ""}`), refetchInterval: (query) => query.state.data?.batches.some((batch) => ["queued", "running"].includes(batch.status)) ? 2000 : false });
  useEffect(() => {
    if (requestedAttempt && focusedAttempt.current !== requestedAttempt && history.data) {
      const target = document.getElementById(`export-attempt-${requestedAttempt}`);
      if (target) { target.focus({ preventScroll: true }); target.scrollIntoView({ block: "center" }); focusedAttempt.current = requestedAttempt; }
    }
  }, [requestedAttempt, history.data]);
  const refreshPending = () => { try { setPending(pendingExports()); setStorageError(false); } catch { setStorageError(true); } };
  useEffect(() => { refreshPending(); window.addEventListener("storage", refreshPending); return () => window.removeEventListener("storage", refreshPending); }, []);
  const action = async (work: () => Promise<unknown>) => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      await work(); setSelected([]); refreshPending();
      await Promise.all([queryClient.invalidateQueries({ queryKey: ["anki-inbox"] }), queryClient.invalidateQueries({ queryKey: ["anki-exports"] }), queryClient.invalidateQueries({ queryKey: ["saved"] }), queryClient.invalidateQueries({ queryKey: ["dashboard"] })]);
    } catch (value) { setError(value instanceof Error ? value.message : "Could not complete export action"); }
    finally { inFlight.current = false; setBusy(false); }
  };
  const latest = new Map<number, number>();
  for (const batch of history.data?.batches ?? []) for (const item of batch.items) if (item.saved_item_id) latest.set(item.saved_item_id, Math.max(latest.get(item.saved_item_id) ?? 0, item.id));
  return <Page size="medium"><PageHeader eyebrow="Long-term retention" title="Anki export inbox" description="Completed local reviews stay here until you export or defer them. Anki schedules long-term practice; an export does not establish mastery." actions={<><Button asChild variant="outline"><Link to="/saved">All saved cards</Link></Button><Button asChild variant="outline"><Link to="/settings">Anki setup</Link></Button></>} />
    {error && <p role="alert" className="rounded-lg border border-amber-400/30 p-3 text-sm text-amber-200">{error} Your cards and accepted exports are retained.</p>}
    {storageError && <p role="alert" className="text-sm text-amber-200">Browser submission reminders are unavailable. Accepted exports remain in the history below.</p>}
    {!!pending.length && <Card><CardHeader><CardTitle className="text-base">Submissions awaiting confirmation</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-muted-foreground">A reply may have been lost. Retry the same request safely; a previously accepted request returns its original export. Dismissing a reminder does not cancel accepted work.</p>{pending.map((request) => <div key={request.request_uuid} className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-3"><p className="text-sm">{request.entries.length} card{request.entries.length === 1 ? "" : "s"} · {new Date(request.created_at).toLocaleDateString()}</p><Button className="min-h-11" disabled={busy} onClick={() => void action(async () => { await startExport(request.entries, request.profile_hash, request.request_uuid); forgetExport(request.request_uuid); })}>Retry same submission</Button><Button variant="outline" className="min-h-11" disabled={busy} onClick={() => void action(async () => { forgetExport(request.request_uuid); })}>Dismiss reminder</Button></div>)}</CardContent></Card>}
    <Card><CardHeader><CardTitle className="text-base">Completed reviews awaiting handoff</CardTitle></CardHeader><CardContent className="space-y-4"><div className="flex flex-wrap gap-2" role="group" aria-label="Export inbox view">{(["ready", "deferred"] as const).map((value) => <Button key={value} className="min-h-11" variant={view === value ? "default" : "outline"} aria-pressed={view === value} onClick={() => { setView(value); setCursor(null); setSelected([]); }}>{value === "ready" ? "Ready" : "Deferred"} {inbox.data?.counts[value] ?? ""}</Button>)}</div>
      {inbox.isError ? <div role="alert" className="space-y-2 text-sm text-amber-200"><p>Could not load export-ready cards. Your saved cards are retained.</p><Button variant="outline" onClick={() => void inbox.refetch()}>Retry inbox</Button></div> : !inbox.data ? <p role="status" className="text-sm text-muted-foreground">Loading completed reviews…</p> : inbox.data.items.length ? <>
        <ul className="space-y-3">{inbox.data.items.map((item) => <li key={item.id} className="flex flex-wrap items-start gap-3 rounded-xl border border-border p-4"><label className="flex min-h-11 min-w-0 flex-1 items-start gap-3"><input type="checkbox" className="mt-1.5 size-4 shrink-0 accent-teal-400" checked={selected.includes(item.id)} disabled={busy || ["queued", "running", "uncertain"].includes(item.export_status ?? "")} onChange={(event) => setSelected(event.target.checked ? [...selected, item.id] : selected.filter((id) => id !== item.id))} /><span className="min-w-0 break-words"><span lang="zh" className="block font-zh text-lg">{item.surface}</span>{item.selected_reading && <span className="block text-sm text-primary">{item.selected_reading}</span>}{item.selected_meaning && <span className="block text-sm">{item.selected_meaning}</span>}{item.attempt_id && <Link to={`/exports?attempt=${item.attempt_id}`} className="mt-1 inline-flex min-h-11 items-center text-sm text-primary underline">View export for {item.surface}</Link>}{item.export_status && <span className="mt-1 block text-xs text-muted-foreground">{statusLabel(item.export_status)} · details below</span>}</span></label><Button className="min-h-11" variant="outline" aria-label={`${view === "ready" ? "Defer" : "Restore"} ${item.surface}`} disabled={busy || ["queued", "running", "uncertain"].includes(item.export_status ?? "")} onClick={() => void action(() => put(`/anki/inbox/${item.id}`, { deferred: view === "ready" }))}>{view === "ready" ? "Defer" : "Restore"}</Button></li>)}</ul>
        <div className="flex flex-wrap gap-2"><Button className="min-h-11" disabled={!selected.length || busy} onClick={() => setTray([...selected])}>Preview {selected.length} selected for Anki</Button>{cursor && <Button variant="outline" className="min-h-11" onClick={() => { setCursor(null); setSelected([]); }}>First page</Button>}{inbox.data.next_cursor && <Button variant="outline" className="min-h-11" onClick={() => { setCursor(inbox.data!.next_cursor); setSelected([]); }}>Next cards</Button>}</div>
      </> : <p className="text-sm text-muted-foreground">{view === "deferred" ? "No deferred cards. Deferring leaves review progress and source context unchanged." : "No completed reviews awaiting export. Browse deferred cards or continue local practice."}</p>}
    </CardContent></Card>
    <Card><CardHeader><CardTitle className="text-base">Recent export history</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-xs text-muted-foreground">Export history is shown 20 submissions per page. Each submission retains its reviewed fields, destination and per-card outcome. Closing a dialog or reloading does not stop accepted work. Retry retains the submitted fields and settings; create a fresh preview to use changed source text or setup.</p>{history.isError ? <div role="alert" className="space-y-2 text-sm text-amber-200"><p>Could not refresh export history.</p><Button variant="outline" onClick={() => void history.refetch()}>Retry history</Button></div> : !history.data ? <p role="status">Loading export history…</p> : !history.data.batches.length ? <p className="text-sm text-muted-foreground">No accepted export submissions yet.</p> : history.data.batches.map((batch) => <section key={batch.job_id} aria-label={`Export submission ${batch.job_id}`} className="space-y-3 rounded-xl border border-border p-4"><h3 className="text-sm font-medium">Submission {batch.job_id} · {batch.status === "done" ? "Processed" : batch.status === "failed" ? "Worker needs attention" : batch.status}</h3>{batch.items.map((item) => {
      const isLatest = item.is_latest !== false && (!item.saved_item_id || latest.get(item.saved_item_id) === item.id);
      const terminal = !["queued", "running"].includes(batch.status);
      return <div id={`export-attempt-${item.id}`} tabIndex={-1} key={item.id} className="space-y-2 border-t border-border pt-3"><p className="text-sm"><span lang="zh" className="font-zh text-lg">{item.surface}</span> · {statusLabel(item.status)}</p><p className="text-xs text-muted-foreground">Deck: {item.profile.deck} · note type: {item.profile.model}{item.note_id ? ` · Anki note ${item.note_id}` : ""}</p>{item.error && <p className="text-sm text-amber-200">{item.error}</p>}{item.warnings.map((warning) => <p key={warning} className="text-xs text-muted-foreground">{warning}</p>)}<details className="rounded-lg bg-muted/20 p-3"><summary className="min-h-11 cursor-pointer text-sm">Reviewed fields and source for {item.surface}</summary><dl className="space-y-2 text-sm">{Object.entries(item.fields).map(([name, value]) => <div key={name}><dt className="text-xs text-muted-foreground">{name}</dt><dd className="break-words">{value || "—"}</dd></div>)}</dl><p className="mt-3 break-all text-xs text-muted-foreground">Find this exact note in Anki with: tag:{item.export_tag}</p></details>
        {terminal && isLatest && item.status === "uncertain" && <div className="space-y-2"><Button className="min-h-11" variant="outline" aria-label={`Check Anki for ${item.surface}`} disabled={busy} onClick={() => void action(() => post(`/anki/export-attempts/${item.id}/reconcile`))}>Check Anki</Button>{item.saved_item_id && <><label className="flex min-h-11 items-start gap-3 text-sm"><input type="checkbox" className="mt-1 size-4 shrink-0 accent-teal-400" checked={confirmed.has(item.id)} onChange={(event) => setConfirmed((previous) => { const next = new Set(previous); if (event.target.checked) next.add(item.id); else next.delete(item.id); return next; })} /><span>I checked Anki for {item.surface} and no note with this export tag exists. Allow another add.</span></label><Button className="min-h-11" aria-label={`Retry unconfirmed ${item.surface}`} disabled={busy || !confirmed.has(item.id)} onClick={() => void action(async () => { const key = `${item.id}:confirmed`; retryIds.current[key] ??= crypto.randomUUID(); await post(`/anki/export-attempts/${item.id}/retry`, { request_uuid: retryIds.current[key], confirm_no_note: true }); delete retryIds.current[key]; })}>Retry unconfirmed note</Button></>}</div>}
        {terminal && isLatest && item.saved_item_id && ["error", "queued"].includes(item.status) && <Button className="min-h-11" variant="outline" aria-label={`Retry ${item.surface}`} disabled={busy} onClick={() => void action(async () => { const key = `${item.id}:retry`; retryIds.current[key] ??= crypto.randomUUID(); await post(`/anki/export-attempts/${item.id}/retry`, { request_uuid: retryIds.current[key] }); delete retryIds.current[key]; })}>Retry original submission</Button>}
      </div>; })}</section>)}<div className="flex flex-wrap gap-2">{historyCursor && <Button className="min-h-11" variant="outline" onClick={() => setHistoryCursor(null)}>Recent submissions</Button>}{history.data?.next_cursor && <Button className="min-h-11" variant="outline" onClick={() => setHistoryCursor(history.data!.next_cursor)}>Older submissions</Button>}</div></CardContent></Card>
    {tray && <ExportTray savedItemIds={tray} onClose={() => { setTray(null); refreshPending(); void queryClient.invalidateQueries({ queryKey: ["anki-exports"] }); void queryClient.invalidateQueries({ queryKey: ["anki-inbox"] }); }} />}
  </Page>;
}
