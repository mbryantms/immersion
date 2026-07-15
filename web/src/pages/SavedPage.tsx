import { ArchiveX, ArrowUpRight, Check, ExternalLink, PackageOpen, RotateCcw, Send, Tags } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { EmptyState, Page, PageHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { setKnowledge, useResetSavedReview, useResetSentencePlayed, useSaved, useUnsave } from "../api/queries";
import type { SavedItemOut } from "../api/types";
import ExportTray from "../saved/ExportTray";

type Kind = "all" | "word" | "sentence";

export default function SavedPage() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<Kind>("all");
  const { data, isLoading } = useSaved(kind === "all" ? undefined : kind);
  const unsave = useUnsave();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [trayIds, setTrayIds] = useState<number[] | null>(null);

  const items = useMemo(() => data?.items ?? [], [data]);
  const selectedItems = items.filter((item) => selected.has(item.id));
  const hasSelectedWords = selectedItems.some((item) => item.lexeme_id);
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.id));

  const toggle = (id: number, on: boolean) => setSelected((previous) => {
    const next = new Set(previous);
    if (on) next.add(id); else next.delete(id);
    return next;
  });

  const bulkKnowledge = async (state: "known" | "ignored") => {
    const lexemes = selectedItems.flatMap((item) => item.lexeme_id ? [item.lexeme_id] : []);
    try {
      await Promise.all(lexemes.map((id) => setKnowledge(id, state)));
      toast.success(`Marked ${lexemes.length} word${lexemes.length === 1 ? "" : "s"} ${state}`);
    } catch {
      toast.error("Some updates failed — check and retry");
    }
    setSelected(new Set());
    void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
  };

  const bulkRemove = async () => {
    const n = selectedItems.length;
    try {
      await Promise.all(selectedItems.map((item) => unsave.mutateAsync(item.id)));
      toast.success(`Removed ${n} item${n === 1 ? "" : "s"} from your queue`);
    } catch {
      toast.error("Some removals failed — check and retry");
    }
    setSelected(new Set());
  };

  return (
    <Page size="medium">
      <PageHeader
        eyebrow="Learning queue"
        title="Saved words and sentences"
        description="Keep useful context close, review it briefly, then graduate durable knowledge to Anki."
        actions={<Button asChild variant="outline"><Link to="/review"><ArrowUpRight />Start review</Link></Button>}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs value={kind} onValueChange={(value) => { setKind(value as Kind); setSelected(new Set()); }}>
          <TabsList><TabsTrigger value="all">All</TabsTrigger><TabsTrigger value="word">Words</TabsTrigger><TabsTrigger value="sentence">Sentences</TabsTrigger></TabsList>
        </Tabs>
        {!!items.length && <label className="flex items-center gap-2 text-xs text-muted-foreground"><Checkbox checked={allSelected} onCheckedChange={(value) => setSelected(value === true ? new Set(items.map((item) => item.id)) : new Set())} />Select all {items.length}</label>}
      </div>

      {selected.size > 0 && (
        <Card className="sticky top-[61px] z-30 border-primary/20 bg-popover/95 shadow-xl backdrop-blur-xl">
          <CardContent className="flex flex-wrap items-center gap-2 py-3">
            <Badge>{selected.size} selected</Badge>
            <span className="grow" />
            <Button size="sm" variant="ghost" disabled={!hasSelectedWords} onClick={() => void bulkKnowledge("known")}><Check />Mark known</Button>
            <Button size="sm" variant="ghost" disabled={!hasSelectedWords} onClick={() => void bulkKnowledge("ignored")}><Tags />Ignore</Button>
            <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void bulkRemove()}><ArchiveX />Remove</Button>
            <Button size="sm" onClick={() => setTrayIds([...selected])}><Send />Export to Anki</Button>
          </CardContent>
        </Card>
      )}

      {isLoading ? <div className="space-y-2">{[1, 2, 3].map((item) => <div key={item} className="h-28 animate-pulse rounded-2xl bg-muted/50" />)}</div> : !items.length ? (
        <EmptyState title="Nothing saved here yet" description="Tap a word or save a sentence while watching. It will appear here with its original context." action={{ label: "Browse the library", href: "/library" }} icon={<PackageOpen className="size-5" />} />
      ) : (
        <ul className="space-y-2">{items.map((item) => <SavedRow key={item.id} item={item} checked={selected.has(item.id)} onCheck={(checked) => toggle(item.id, checked)} onRemove={() => unsave.mutate(item.id)} />)}</ul>
      )}

      {trayIds && <ExportTray savedItemIds={trayIds} onClose={() => setTrayIds(null)} />}
    </Page>
  );
}

function SavedRow({ item, checked, onCheck, onRemove }: { item: SavedItemOut; checked: boolean; onCheck: (on: boolean) => void; onRemove: () => void }) {
  const title = item.surface || item.contexts[0]?.zh || "Saved sentence";
  const resetReview = useResetSavedReview();
  const resetSentencePlayed = useResetSentencePlayed();
  const [resetOpen, setResetOpen] = useState(false);
  const playedContexts = item.kind === "sentence"
    ? item.contexts.filter((context) => context.sentence_id && context.played)
    : [];

  const resetPractice = async () => {
    await resetReview.mutateAsync(item.id);
    if (item.kind === "sentence") {
      for (const context of item.contexts) {
        if (!context.item_id || !context.sentence_id) continue;
        try {
          const key = `dict:${context.item_id}`;
          const stored = JSON.parse(localStorage.getItem(key) ?? "{}") as {
            version?: number;
            attempts?: Record<string, unknown>;
            [key: string]: unknown;
          };
          if (stored.version === 2 && stored.attempts) {
            delete stored.attempts[String(context.sentence_id)];
          } else {
            delete stored[String(context.sentence_ord ?? context.sentence_id)];
          }
          localStorage.setItem(key, JSON.stringify(stored));
        } catch {
          // Corrupt or blocked local storage should not prevent the server reset.
        }
      }
    }
    setResetOpen(false);
  };

  const markUnplayed = async () => {
    await Promise.all(playedContexts.map((context) => resetSentencePlayed.mutateAsync(context.sentence_id!)));
    setResetOpen(false);
  };

  return (
    <li>
      <Card className={checked ? "border-primary/30 bg-primary/[0.035]" : "transition hover:border-border"}>
        <CardContent className="py-4">
          <div className="flex items-start gap-3">
            <Checkbox className="mt-1.5" checked={checked} onCheckedChange={(value) => onCheck(value === true)} aria-label={`Select ${title}`} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-zh text-xl text-foreground">{title}</span>
                <Badge variant="secondary" className="text-[10px] capitalize">{item.kind}</Badge>
                {item.anki_note_id && <Badge className="bg-emerald-400/12 text-[10px] text-emerald-300">In Anki</Badge>}
                {item.review && <Badge variant="secondary" className="text-[10px]">{item.review.graduated ? "Review complete" : `Review rung ${item.review.rung + 1}`}</Badge>}
              </div>
              {!!item.contexts.length && (
                <ul className="mt-2 space-y-2">
                  {item.contexts.map((context, index) => (
                    <li key={index} className="rounded-lg bg-muted/30 px-3 py-2">
                      {context.zh && <p className="font-zh text-sm leading-relaxed text-foreground/90">{context.zh}</p>}
                      {context.en && <p className="mt-0.5 text-xs text-muted-foreground">{context.en}</p>}
                      <div className="mt-1.5 flex flex-wrap items-center gap-2">
                        {context.item_id && <Link to={`/watch/${context.item_id}${context.t0_ms != null ? `?t=${context.t0_ms}` : ""}`} className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline">{context.item_title ?? "Open source"}<ExternalLink className="size-3" /></Link>}
                        {context.played && <span className="text-[10px] font-medium text-emerald-300/70">Listened</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {(item.review || playedContexts.length > 0) && (
                <Dialog open={resetOpen} onOpenChange={setResetOpen}>
                  <DialogTrigger asChild><Button variant="ghost" size="icon-sm" className="text-muted-foreground" aria-label={`Reset practice for ${title}`} title="Reset practice"><RotateCcw /></Button></DialogTrigger>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Reset learning state</DialogTitle><DialogDescription>Choose only the state you want to restart. Historical activity and word exposure counts are preserved.</DialogDescription></DialogHeader>
                    <div className="space-y-3">
                      {item.review && <div className="rounded-lg border border-border p-3"><p className="text-sm font-medium">Practice progress</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.kind === "sentence" ? "Return to the first review rung and clear this sentence’s saved dictation attempt." : "Return to the first contextual review rung."}</p><Button className="mt-3" variant="outline" size="sm" disabled={resetReview.isPending} onClick={() => void resetPractice()}><RotateCcw />Reset practice</Button></div>}
                      {playedContexts.length > 0 && <div className="rounded-lg border border-border p-3"><p className="text-sm font-medium">Listened state</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Mark this sentence as unplayed without changing historical minutes or word encounters.</p><Button className="mt-3" variant="outline" size="sm" disabled={resetSentencePlayed.isPending} onClick={() => void markUnplayed()}><RotateCcw />Mark unplayed</Button></div>}
                    </div>
                    <DialogFooter showCloseButton />
                  </DialogContent>
                </Dialog>
              )}
              <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" onClick={onRemove} aria-label={`Remove ${title}`}><ArchiveX /></Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
