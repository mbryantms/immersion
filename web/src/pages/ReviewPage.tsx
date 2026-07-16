import { ArrowLeft, Check, CircleX, Coffee, Headphones, Play, Send, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { QueryError } from "@/components/ErrorBoundary";
import { LoadingPage, Page } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { postReviewOutcome, useReviewQueue } from "../api/queries";
import type { ReviewItem } from "../api/types";
import ExportTray from "../saved/ExportTray";

export default function ReviewPage() {
  const { data, isError, refetch } = useReviewQueue();
  const [position, setPosition] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [graduatedIds, setGraduatedIds] = useState<number[]>([]);
  const [trayIds, setTrayIds] = useState<number[] | null>(null);
  const [doneCount, setDoneCount] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopAt = useRef<number | null>(null);

  const items = data?.items ?? [];
  const current: ReviewItem | undefined = items[position];

  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const audio = audioRef.current;
      if (audio && stopAt.current !== null && audio.currentTime * 1000 >= stopAt.current) {
        audio.pause();
        stopAt.current = null;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const play = useCallback(() => {
    const audio = audioRef.current;
    const context = current?.context;
    if (!audio || !context?.stream_url) return;
    audio.currentTime = context.t0_ms / 1000;
    stopAt.current = context.t1_ms;
    void audio.play();
  }, [current]);

  useEffect(() => {
    setRevealed(false);
    const timer = setTimeout(play, 300);
    return () => clearTimeout(timer);
  }, [position, play]);

  const grade = async (result: "pass" | "fail") => {
    if (!current) return;
    const outcome = await postReviewOutcome(current.saved_item_id, { result, mode: current.mode });
    if (outcome.graduated && !outcome.already_in_anki) setGraduatedIds((previous) => [...previous, current.saved_item_id]);
    setDoneCount((count) => count + 1);
    setPosition((value) => value + 1);
  };

  if (isError) return <QueryError onRetry={() => void refetch()} />;
  if (!data) return <LoadingPage label="Preparing review" />;

  if (!current) {
    return (
      <Page size="narrow" className="flex min-h-[65vh] items-center justify-center">
        <Card className="w-full border-primary/15 bg-gradient-to-br from-primary/[0.07] to-card text-center">
          <CardContent className="flex flex-col items-center py-12">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Coffee className="size-7" /></div>
            <h1 className="mt-5 text-2xl font-semibold">{doneCount ? `Session complete` : "Nothing due right now"}</h1>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">{doneCount ? `You retrieved ${doneCount} item${doneCount === 1 ? "" : "s"}. Return to real input while those memories settle.` : "Your queue is clear. More listening and reading will create the next useful review."}</p>
            {graduatedIds.length > 0 && <Button className="mt-5" onClick={() => setTrayIds(graduatedIds)}><Send />Export {graduatedIds.length} graduate{graduatedIds.length === 1 ? "" : "s"} to Anki</Button>}
            <Button asChild variant="ghost" className="mt-2"><Link to="/"><ArrowLeft />Back home</Link></Button>
          </CardContent>
        </Card>
        {trayIds && <ExportTray savedItemIds={trayIds} onClose={() => { setTrayIds(null); void refetch(); }} />}
      </Page>
    );
  }

  const context = current.context;
  const listen = current.mode === "listen";
  const cloze = !listen && !!context && !!current.surface && context.zh.includes(current.surface);
  const wordInfo = cloze
    ? context.words.find((w) => w.type === "zh" && w.t === current.surface)
    : undefined;
  const progress = items.length ? ((position + 1) / items.length) * 100 : 0;

  return (
    <Page size="narrow">
      <header>
        <div className="mb-3 flex items-center gap-2">
          <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground"><Link to="/"><ArrowLeft />Exit</Link></Button>
          <span className="grow" />
          <Badge variant="secondary"><Headphones className="size-3" />{listen ? "Listening" : "Context"}</Badge>
          <Badge variant="outline">Step {current.rung + 1}</Badge>
        </div>
        <div className="flex items-center gap-3"><Progress value={progress} className="h-1.5" /><span className="shrink-0 text-xs tabular-nums text-muted-foreground">{position + 1} / {items.length}</span></div>
      </header>

      <Card className="min-h-[360px] border-border bg-card shadow-2xl shadow-black/15">
        {context?.stream_url && <audio ref={audioRef} src={context.stream_url} preload="auto" />}
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>{listen ? "Listen and recall" : cloze ? "Recall the missing word" : "Retrieve the meaning"}</CardTitle>
              <CardDescription>
                {listen
                  ? "Understand the line before revealing it."
                  : cloze
                    ? "Think of the word that belongs in the blank, then reveal."
                    : "What does this word mean?"}
              </CardDescription>
            </div>
            {context?.stream_url && <Button variant="secondary" size="icon-lg" className="shrink-0 rounded-full" onClick={play} aria-label="Replay audio"><Volume2 /></Button>}
          </div>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col pt-3">
          {listen && context ? (
            <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
              {revealed || !context.stream_url
                ? <p className="font-zh text-2xl leading-relaxed text-foreground sm:text-3xl">{context.zh}</p>
                : <p className="text-sm text-muted-foreground">Audio only — replay as often as you need.</p>}
              {revealed && context.en && <p className="mt-5 max-w-lg text-base text-muted-foreground">{context.en}</p>}
              {!revealed && <Button onClick={() => setRevealed(true)} variant="secondary" className="mt-7"><Play className="size-4" />Reveal sentence</Button>}
            </div>
          ) : cloze && context ? (
            <div className="space-y-4">
              <p className="font-zh text-2xl leading-relaxed text-foreground sm:text-3xl">
                {revealed ? highlight(context.zh, current.surface) : blank(context.zh, current.surface!)}
              </p>
              {!revealed && <Button onClick={() => setRevealed(true)} variant="secondary"><Play className="size-4" />Reveal word</Button>}
              {revealed && (
                <div className="rounded-xl border border-border bg-muted/25 p-4">
                  <div className="flex items-center gap-2">
                    <span className="font-zh text-lg text-foreground">{current.surface}</span>
                    {wordInfo?.py && <span className="text-sm text-muted-foreground">{wordInfo.py.join("")}</span>}
                  </div>
                  {context.en && <p className="mt-2 text-sm text-muted-foreground">{context.en}</p>}
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center py-8 text-center">
              {context ? <p className="font-zh text-2xl leading-relaxed text-foreground sm:text-3xl">{highlight(context.zh, current.surface)}</p> : <p className="font-zh text-4xl text-foreground">{current.surface}</p>}
              {revealed && context?.en && <p className="mt-5 max-w-lg text-base text-muted-foreground">{context.en}</p>}
              {!revealed && <Button onClick={() => setRevealed(true)} variant="secondary" className="mt-7"><Play className="size-4" />Reveal meaning</Button>}
            </div>
          )}

          {revealed && (
            <div className="mt-auto grid grid-cols-2 gap-3 border-t border-border pt-5">
              <Button size="lg" variant="secondary" className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={() => void grade("fail")}><CircleX />Not yet</Button>
              <Button size="lg" onClick={() => void grade("pass")}><Check />Got it</Button>
            </div>
          )}
        </CardContent>
      </Card>
      <p className="text-center text-xs text-muted-foreground">Review is intentionally short. Passing items move toward Anki; misses return with fresh context.</p>
    </Page>
  );
}

function highlight(zh: string, surface: string | null) {
  if (!surface || !zh.includes(surface)) return zh;
  const [before, ...rest] = zh.split(surface);
  return <>{before}<mark className="rounded-md bg-primary/15 px-1 text-primary">{surface}</mark>{rest.join(surface)}</>;
}

function blank(zh: string, surface: string) {
  const [before, ...rest] = zh.split(surface);
  return (
    <>
      {before}
      <span className="mx-0.5 rounded-md border border-dashed border-primary/40 bg-primary/5 px-1.5 tracking-widest text-primary/60">
        {"＿".repeat(Math.max(2, surface.length))}
      </span>
      {rest.join(surface)}
    </>
  );
}
