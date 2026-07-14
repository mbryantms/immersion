import { AlertTriangle, CheckCircle2, Database, FolderPlus, LoaderCircle, Play, RefreshCw, ServerCog, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { get, post } from "../api/client";
import { useCreateJob, useJobs, useLibrary } from "../api/queries";
import type { JobOut } from "../api/types";

export default function JobsPage() {
  const queryClient = useQueryClient();
  const { data, refetch } = useJobs();
  const { data: library } = useLibrary();
  const createJob = useCreateJob();
  const [ankiMessage, setAnkiMessage] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [root, setRoot] = useState({ slug: "", path: "", include: "" });
  const [addingRoot, setAddingRoot] = useState(false);

  const importAnki = async () => {
    setAnkiMessage("Queueing known-word import…");
    try {
      await post("/anki/import-known", { mature_days: 21 });
      setAnkiMessage("Import queued. Keep Anki Desktop open while it runs.");
      const status = await get<{ last_import: unknown }>("/anki/status");
      if (status.last_import) setAnkiMessage(`Import queued · previous sync ${JSON.stringify(status.last_import)}`);
    } catch (error) {
      setAnkiMessage(`Could not queue import: ${String(error)}`);
    }
  };

  const addRoot = async (event: FormEvent) => {
    event.preventDefault();
    if (!root.slug.trim() || !root.path.trim()) return;
    setAddingRoot(true);
    try {
      await post("/roots", { slug: root.slug.trim(), path: root.path.trim(), include_glob: root.include.trim() || null });
      setRoot({ slug: "", path: "", include: "" });
      setDialogOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["library"] });
      await refetch();
    } finally {
      setAddingRoot(false);
    }
  };

  return (
    <Page size="medium">
      <PageHeader
        eyebrow="System administration"
        title="Libraries and background work"
        description="Add local media sources, synchronize learner knowledge, and monitor ingestion or export jobs."
        actions={
          <>
            <Button variant="outline" onClick={() => void importAnki()}><Sparkles />Import from Anki</Button>
            <Button onClick={() => createJob.mutate({ type: "scan_all" })} disabled={createJob.isPending}><RefreshCw className={createJob.isPending ? "animate-spin" : ""} />Scan libraries</Button>
          </>
        }
      />

      {ankiMessage && <Card className="border-amber-400/15 bg-amber-400/[0.035]"><CardContent className="flex items-start gap-2 py-3 text-xs text-amber-100/80"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-300" />{ankiMessage}</CardContent></Card>}

      <section>
        <SectionHeader title="Media roots" description="Folders periodically scanned for video, audio, and subtitle files" action={
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild><Button size="sm" variant="outline"><FolderPlus />Add media root</Button></DialogTrigger>
            <DialogContent className="sm:max-w-lg">
              <form onSubmit={addRoot}>
                <DialogHeader><DialogTitle>Add media root</DialogTitle><DialogDescription>Point Immersion at a local folder. The initial scan starts automatically.</DialogDescription></DialogHeader>
                <div className="space-y-4 py-5">
                  <Field label="Short name" hint="A stable identifier such as lfc or podcasts"><Input value={root.slug} onChange={(event) => setRoot({ ...root, slug: event.target.value })} placeholder="podcasts" autoFocus /></Field>
                  <Field label="Folder path" hint="Absolute path visible to the server"><Input value={root.path} onChange={(event) => setRoot({ ...root, path: event.target.value })} placeholder="/media/mandarin/podcasts" /></Field>
                  <Field label="Include pattern" hint="Optional glob for selecting subfolders"><Input value={root.include} onChange={(event) => setRoot({ ...root, include: event.target.value })} placeholder="Level */*" /></Field>
                </div>
                <DialogFooter><Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>Cancel</Button><Button type="submit" disabled={addingRoot || !root.slug.trim() || !root.path.trim()}>{addingRoot && <LoaderCircle className="animate-spin" />}Add and scan</Button></DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        } />
        <div className="grid gap-3 sm:grid-cols-2">
          {(library?.roots ?? []).map((mediaRoot) => (
            <Card key={mediaRoot.id}>
              <CardContent className="py-4">
                <div className="flex items-start gap-3"><div className="flex size-9 items-center justify-center rounded-xl bg-primary/8 text-primary"><Database className="size-4" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-mono text-sm font-medium">{mediaRoot.slug}</p><Badge variant="secondary" className="capitalize">{mediaRoot.kind}</Badge>{!mediaRoot.enabled && <Badge variant="destructive">Disabled</Badge>}</div><p className="mt-1 truncate font-mono text-[11px] text-muted-foreground" title={mediaRoot.path}>{mediaRoot.path}</p>{mediaRoot.include_glob && <p className="mt-1 text-[10px] text-muted-foreground">Includes: {mediaRoot.include_glob}</p>}</div></div>
              </CardContent>
            </Card>
          ))}
          {!library?.roots.length && <Card className="border-dashed bg-card/30 sm:col-span-2"><CardContent className="py-10 text-center text-sm text-muted-foreground">No media roots configured.</CardContent></Card>}
        </div>
      </section>

      <section>
        <SectionHeader title="Background jobs" description={data?.active ? "Work is currently running; this list refreshes automatically" : "Recent scans, analysis, and Anki exports"} action={data?.active && <Badge className="gap-1 bg-primary/10 text-primary"><LoaderCircle className="size-3 animate-spin" />Active</Badge>} />
        <Card className="overflow-hidden">
          <div className="divide-y divide-border">
            {(data?.jobs ?? []).map((job) => <JobRow key={job.id} job={job} onRetry={async () => { await post(`/jobs/${job.id}/retry`); await refetch(); }} />)}
            {!data?.jobs.length && <div className="py-12 text-center text-sm text-muted-foreground"><ServerCog className="mx-auto mb-2 size-6" />No jobs recorded.</div>}
          </div>
        </Card>
      </section>
    </Page>
  );
}

function JobRow({ job, onRetry }: { job: JobOut; onRetry: () => Promise<void> }) {
  const status = {
    queued: { icon: <Play />, className: "bg-muted text-muted-foreground" },
    running: { icon: <LoaderCircle className="animate-spin" />, className: "bg-amber-400/10 text-amber-300" },
    done: { icon: <CheckCircle2 />, className: "bg-emerald-400/10 text-emerald-300" },
    failed: { icon: <AlertTriangle />, className: "bg-destructive/10 text-destructive" },
  }[job.status];
  const message = job.error ? job.error.split("\n").at(-2) ?? job.error.slice(-160) : job.progress;
  return (
    <div className="grid gap-3 px-4 py-3 sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <Badge className={`gap-1 capitalize ${status.className}`}>{status.icon}{job.status}</Badge>
      <div className="min-w-0"><div className="flex items-center gap-2"><p className="text-sm font-medium">{job.type.replaceAll("_", " ")}</p><span className="text-[10px] text-muted-foreground">#{job.id}</span></div>{message && <p className={`mt-0.5 truncate text-xs ${job.error ? "text-destructive/80" : "text-muted-foreground"}`} title={message}>{message}</p>}{job.payload && <p className="mt-0.5 truncate font-mono text-[9px] text-muted-foreground/60">{JSON.stringify(job.payload)}</p>}</div>
      {job.status === "failed" && <Button size="sm" variant="outline" onClick={() => void onRetry()}><RefreshCw />Retry</Button>}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return <label className="grid gap-1.5"><span className="text-sm font-medium">{label}</span>{children}<span className="text-[11px] text-muted-foreground">{hint}</span></label>;
}
