import { ArrowLeft, ArrowUpRight, BookMarked, Check, CircleSlash2, Eye, LibraryBig, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { LoadingPage, Page, SectionHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { clearKnowledge, resetLexemeStats, setKnowledge, useConcordance, useExamples, useLexeme } from "../api/queries";
import type { KnowledgeStateName } from "../api/types";
import { formatPinyin } from "../lib/pinyin";
import { freqBand, posLabel } from "../lib/pos";
import { usePrefs } from "../lib/prefs";
import CharacterStrokes from "../word/CharacterStrokes";

export default function WordPage() {
  const id = Number(useParams().id);
  const queryClient = useQueryClient();
  const { data: lex, isLoading } = useLexeme(id);
  const { data: concordance } = useConcordance(id);
  const { data: examples } = useExamples(id);
  const pinyinStyle = usePrefs((prefs) => prefs.pinyinStyle);
  const [updating, setUpdating] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  if (isLoading) return <LoadingPage label="Loading word" />;
  if (!lex) return null;

  const updateState = async (state: KnowledgeStateName) => {
    setUpdating(true);
    try {
      if (lex.state === state && lex.state_source === "manual") await clearKnowledge(id);
      else await setKnowledge(id, state);
      await queryClient.invalidateQueries({ queryKey: ["lexeme", id] });
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    } finally {
      setUpdating(false);
    }
  };

  const clearManualState = async () => {
    setUpdating(true);
    try {
      await clearKnowledge(id);
      await queryClient.invalidateQueries({ queryKey: ["lexeme", id] });
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    } finally {
      setUpdating(false);
    }
  };

  const resetExposure = async () => {
    setUpdating(true);
    try {
      await resetLexemeStats(id);
      await queryClient.invalidateQueries({ queryKey: ["lexeme", id] });
      setResetOpen(false);
    } finally {
      setUpdating(false);
    }
  };

  return (
    <Page size="medium">
      <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit text-muted-foreground"><Link to="/search"><ArrowLeft />Back to search</Link></Button>

      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-end gap-4">
          <div className="flex min-h-24 min-w-24 items-center justify-center rounded-3xl border border-primary/15 bg-primary/[0.07] px-4 shadow-inner"><h1 className="font-zh text-5xl text-foreground sm:text-6xl">{lex.simplified}</h1></div>
          <div className="pb-1">
            {lex.traditional && lex.traditional !== lex.simplified && <p className="font-zh text-2xl text-muted-foreground">{lex.traditional}</p>}
            <p className="text-xl font-medium text-primary">{formatPinyin(lex.senses[0]?.py ?? lex.pinyin, pinyinStyle)}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lex.hsk && <Badge variant="secondary">HSK {lex.hsk}</Badge>}
              {posLabel(lex.pos) && <Badge variant="secondary">{posLabel(lex.pos)}</Badge>}
              {freqBand(lex.freq_rank) && <Badge variant="secondary" title={`Frequency rank #${lex.freq_rank?.toLocaleString()}`}>{freqBand(lex.freq_rank)}</Badge>}
              <Badge className={stateColor(lex.state)}>{lex.state}{lex.state_source ? ` · ${lex.state_source}` : ""}</Badge>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant={lex.state === "known" ? "default" : "outline"} disabled={updating} onClick={() => void updateState("known")}><Check />{lex.state === "known" ? "Known" : "Mark known"}</Button>
          <Button variant="outline" disabled={updating} onClick={() => void updateState("ignored")} className={lex.state === "ignored" ? "border-muted-foreground/30 bg-muted" : ""}><CircleSlash2 />{lex.state === "ignored" ? "Ignored" : "Ignore"}</Button>
          <Dialog open={resetOpen} onOpenChange={setResetOpen}>
            <DialogTrigger asChild><Button variant="ghost" disabled={updating}><RotateCcw />Reset</Button></DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Reset data for {lex.simplified}</DialogTitle>
                <DialogDescription>Knowledge and exposure are separate. Saved contexts and review progress will not be changed.</DialogDescription>
              </DialogHeader>
              <div className="space-y-3">
                <div className="rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-4">
                    <div><p className="text-sm font-medium">Clear manual status</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Restore Anki status if available, otherwise Learning when saved or New.</p></div>
                    <Button variant="outline" size="sm" disabled={updating || lex.state_source !== "manual"} onClick={() => void clearManualState()}><RotateCcw />Clear</Button>
                  </div>
                </div>
                <div className="rounded-lg border border-destructive/20 p-3">
                  <div className="flex items-start justify-between gap-4">
                    <div><p className="text-sm font-medium">Reset exposure history</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">Set Seen and Looked up counters back to zero. The audit event is retained.</p></div>
                    <Button variant="destructive" size="sm" disabled={updating || !lex.stats || (lex.stats.encounters === 0 && lex.stats.lookups === 0)} onClick={() => void resetExposure()}><Trash2 />Reset</Button>
                  </div>
                </div>
              </div>
              <DialogFooter showCloseButton />
            </DialogContent>
          </Dialog>
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_290px]">
        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-sm">Definitions</CardTitle></CardHeader>
            <CardContent className="space-y-3 pt-2">
              {lex.senses.map((sense, index) => <div key={index} className="flex items-start gap-3"><span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">{index + 1}</span><p className="text-sm leading-relaxed text-foreground/90">{sense.py && <span className="mr-2 font-medium text-primary/70">{formatPinyin(sense.py, pinyinStyle)}</span>}{sense.defs.join("; ")}</p></div>)}
              {!lex.senses.length && <p className="text-sm text-muted-foreground">No dictionary entry. This may be a name or out-of-vocabulary token.</p>}
              {lex.stats && <><Separator /><div className="flex flex-wrap gap-4 text-xs text-muted-foreground"><span className="flex items-center gap-1.5"><Eye className="size-3.5" />Seen {lex.stats.encounters} times</span><span className="flex items-center gap-1.5"><BookMarked className="size-3.5" />Looked up {lex.stats.lookups} times</span></div></>}
            </CardContent>
          </Card>

          {!!examples?.results.length && <section><SectionHeader title="Example sentences" description="Additional usage examples from Tatoeba" /><div className="space-y-2">{examples.results.map((example, index) => <Card key={index} className="bg-card/45"><CardContent className="py-3"><p className="font-zh text-base leading-relaxed">{example.zh}</p><p className="mt-1 text-xs text-muted-foreground">{example.en}</p></CardContent></Card>)}</div></section>}

          <section>
            <SectionHeader title="In your library" description="Every indexed encounter, linked back to its source" />
            <div className="space-y-2">
              {(concordance?.results ?? []).map((result) => <Card key={result.sentence_id} className="transition hover:border-primary/25"><CardContent className="py-3"><p className="font-zh text-base leading-relaxed">{result.zh}</p>{result.en && <p className="mt-1 text-xs text-muted-foreground">{result.en}</p>}<Button asChild variant="ghost" size="sm" className="mt-1 -ml-2 text-primary"><Link to={`/watch/${result.item_id}?t=${result.t0_ms}`}>{result.item_title ?? "Open source"} · {fmt(result.t0_ms)}<ArrowUpRight /></Link></Button></CardContent></Card>)}
              {concordance && !concordance.results.length && <Card className="border-dashed bg-card/30"><CardContent className="py-8 text-center text-sm text-muted-foreground"><LibraryBig className="mx-auto mb-2 size-5" />No indexed occurrences.</CardContent></Card>}
            </div>
          </section>
        </div>

        <aside className="space-y-3 lg:sticky lg:top-20 lg:self-start">
          <SectionHeader title="Stroke order" description="Tap a character to replay" />
          <CharacterStrokes word={lex.simplified} />
          <Card className="border-primary/10 bg-primary/[0.035]"><CardContent className="py-4"><div className="flex gap-2 text-xs leading-relaxed text-muted-foreground"><Sparkles className="mt-0.5 size-4 shrink-0 text-primary" /><p>Knowledge state changes affect familiarity scores throughout your library.</p></div></CardContent></Card>
        </aside>
      </div>
    </Page>
  );
}

function stateColor(state: string): string {
  if (state === "known") return "bg-emerald-400/12 text-emerald-300";
  if (state === "learning") return "bg-amber-400/12 text-amber-300";
  if (state === "ignored") return "bg-muted text-muted-foreground";
  return "bg-sky-400/12 text-sky-300";
}

function fmt(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
