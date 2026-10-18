import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { get } from "../api/client";
import type { ExportBatch } from "../anki-types";
export const statusLabel = (status: string) => ({ queued: "Queued", running: "Preparing", added: "Confirmed in Anki", already_exported: "Already linked to Anki", uncertain: "Unconfirmed — check Anki", error: "Needs attention", removed: "Saved card removed" }[status] ?? status);
export default function ExportBatchStatus({ jobId }: { jobId: number }) {
  const query = useQuery({ queryKey: ["anki-export", jobId], queryFn: () => get<ExportBatch>(`/anki/exports/${jobId}`), refetchInterval: (result) => ["queued", "running"].includes(result.state.data?.status ?? "queued") ? 2000 : false });
  if (query.isError) return <p role="alert" className="text-sm text-amber-200">Could not refresh export status. The accepted export is retained in the <Link to="/exports" className="underline">export inbox</Link>.</p>;
  if (!query.data) return <p role="status" className="text-sm text-muted-foreground">Loading accepted export…</p>;
  return <section className="space-y-3" aria-label="Accepted export status"><p role="status" className="text-sm">{["queued", "running"].includes(query.data.status) ? "Export accepted. You can close this dialog; processing continues." : "Export processing finished. Only confirmed notes are linked to Anki."}</p><ul className="space-y-2">{query.data.items.map((item) => <li key={item.id} className="rounded-lg border border-border p-3 text-sm"><p><span lang="zh" className="font-zh">{item.surface}</span> · {statusLabel(item.status)}</p>{item.note_id && <p className="text-xs text-muted-foreground">Anki note {item.note_id}</p>}{item.error && <p className="mt-1 text-amber-200">{item.error}</p>}{item.warnings.map((warning) => <p key={warning} className="mt-1 text-xs text-muted-foreground">{warning}</p>)}</li>)}</ul><Link to="/exports" className="inline-flex min-h-11 items-center text-sm text-primary underline">Open persistent export inbox</Link></section>;
}
