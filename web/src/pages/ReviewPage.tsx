import { ArrowLeft, Check, CircleX, Coffee, Headphones, Keyboard, Play, Send, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { QueryError } from "@/components/ErrorBoundary";
import { LoadingPage, Page } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { PASS_SCORE, scoreAttempt } from "../lib/dictation";
import { postReviewOutcome, useReviewQueue } from "../api/queries";
import type { ReviewItem } from "../api/types";
import ExportTray from "../saved/ExportTray";

export default function ReviewPage() {
  const { data, isError, refetch } = useReviewQueue();
  const [position, setPosition] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [typed, setTyped] = useState("");
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
    setTyped("");
    const timer = setTimeout(play, 300);
    return () => clearTimeout(timer);
  }, [position, play]);

  const grade = async (result: "pass" | "fail", score?: number) => {
    if (!current) return;
    const outcome = await postReviewOutcome(current.saved_item_id, { result, mode: current.mode, score });
    if (outcome.graduated && !outcome.already_in_anki) setGraduatedIds((previous) => [...previous, current.saved_item_id]);
    setDoneCount((count) => count + 1);
    setPosition((value) => value + 1);
  };

  const checkDictation = () => {
    if (!current?.context) return;
    setRevealed(true);
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
  const dictation = current.mode === "dictation";
  const cloze = !dictation && !!context && !!current.surface && context.zh.includes(current.surface);
  const result = dictation && revealed && context ? scoreAttempt(context.zh, typed) : null;
  const wordInfo = cloze
    ? context.words.find((w) => w.type === "zh" && w.t === current.surface)
    : undefined;
  const wordCorrect = cloze && revealed
    ? answerMatches(typed, current.surface!, wordInfo?.tr, wordInfo?.py?.join(""))
    : null;
  // auto-graded verdict; the learner can still override
  const verdict = dictation
    ? (result ? result.score >= PASS_SCORE : null)
    : wordCorrect;
  const progress = items.length ? ((position + 1) / items.length) * 100 : 0;

  return (
    <Page size="narrow">
      <header>
        <div className="mb-3 flex items-center gap-2">
          <Button asChild variant="ghost" size="sm" className="-ml-2 text-muted-foreground"><Link to="/"><ArrowLeft />Exit</Link></Button>
          <span className="grow" />
          <Badge variant="secondary">{dictation ? <><Keyboard className="size-3" />Dictation</> : <><Headphones className="size-3" />Context</>}</Badge>
          <Badge variant="outline">Step {current.rung + 1}</Badge>
        </div>
        <div className="flex items-center gap-3"><Progress value={progress} className="h-1.5" /><span className="shrink-0 text-xs tabular-nums text-muted-foreground">{position + 1} / {items.length}</span></div>
      </header>

      <Card className="min-h-[360px] border-border bg-card shadow-2xl shadow-black/15">
        {context?.stream_url && <audio ref={audioRef} src={context.stream_url} preload="auto" />}
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>{dictation ? "Write what you hear" : cloze ? "Fill in the missing word" : "Retrieve the meaning"}</CardTitle>
              <CardDescription>
                {dictation
                  ? "Listen first. Punctuation and spacing are ignored."
                  : cloze
                    ? "Type the word that belongs in the blank — hanzi or pinyin"
                    : "What does this word mean?"}
              </CardDescription>
            </div>
            {context?.stream_url && <Button variant="secondary" size="icon-lg" className="shrink-0 rounded-full" onClick={play} aria-label="Replay audio"><Volume2 /></Button>}
          </div>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col pt-3">
          {dictation ? (
            <div className="space-y-4">
              <div className="flex gap-2">
                <Input lang="zh-CN" value={typed} onChange={(event) => setTyped(event.target.value)} onKeyDown={(event) => event.key === "Enter" && !event.nativeEvent.isComposing && checkDictation()} placeholder="听写…" className="h-12 bg-background/40 font-zh text-lg" disabled={revealed} autoFocus />
                {!revealed && <Button className="h-12" onClick={checkDictation} disabled={!typed}>Check</Button>}
              </div>
              {result && context && <div className="rounded-xl border border-border bg-muted/25 p-4"><div className="mb-2 flex items-center gap-2"><Badge className={result.score >= PASS_SCORE ? "bg-emerald-400/15 text-emerald-300" : "bg-amber-400/15 text-amber-300"}>{Math.round(result.score * 100)}% match</Badge></div><p className="font-zh text-xl text-foreground">{context.zh}</p>{context.en && <p className="mt-1 text-sm text-muted-foreground">{context.en}</p>}</div>}
            </div>
          ) : cloze && context ? (
            <div className="space-y-4">
              <p className="font-zh text-2xl leading-relaxed text-foreground sm:text-3xl">
                {revealed ? highlight(context.zh, current.surface) : blank(context.zh, current.surface!)}
              </p>
              {!revealed && (
                <div className="flex gap-2">
                  <Input lang="zh-CN" value={typed} onChange={(event) => setTyped(event.target.value)} onKeyDown={(event) => event.key === "Enter" && !event.nativeEvent.isComposing && setRevealed(true)} placeholder="缺的词…" className="h-12 bg-background/40 font-zh text-lg" autoFocus />
                  <Button className="h-12" onClick={() => setRevealed(true)} disabled={!typed}>Check</Button>
                  <Button className="h-12" variant="ghost" onClick={() => { setTyped(""); setRevealed(true); }}>Don't know</Button>
                </div>
              )}
              {revealed && (
                <div className="rounded-xl border border-border bg-muted/25 p-4">
                  <div className="mb-2 flex items-center gap-2">
                    <Badge className={wordCorrect ? "bg-emerald-400/15 text-emerald-300" : "bg-amber-400/15 text-amber-300"}>
                      {wordCorrect ? "Correct" : typed ? `You wrote: ${typed}` : "Revealed"}
                    </Badge>
                    <span className="font-zh text-lg text-foreground">{current.surface}</span>
                    {wordInfo?.py && <span className="text-sm text-muted-foreground">{wordInfo.py.join("")}</span>}
                  </div>
                  {context.en && <p className="text-sm text-muted-foreground">{context.en}</p>}
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

          {revealed && verdict !== null ? (
            // objective modes: the verdict is computed; Continue submits it,
            // the ghost button lets the learner overrule an unfair grade
            <div className="mt-auto flex items-center gap-3 border-t border-border pt-5">
              <Button size="lg" className="flex-1" onClick={() => void grade(verdict ? "pass" : "fail", result?.score)}>
                {verdict ? <Check /> : <CircleX />}Continue
              </Button>
              <Button size="lg" variant="ghost" className="text-muted-foreground" onClick={() => void grade(verdict ? "fail" : "pass", result?.score)}>
                {verdict ? "Actually missed it" : "I did know it"}
              </Button>
            </div>
          ) : revealed || dictation ? (
            <div className="mt-auto grid grid-cols-2 gap-3 border-t border-border pt-5">
              <Button size="lg" variant="secondary" className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive" disabled={dictation && !revealed} onClick={() => void grade("fail", result?.score)}><CircleX />Not yet</Button>
              <Button size="lg" disabled={dictation && !revealed} onClick={() => void grade("pass", result?.score)}><Check />Got it</Button>
            </div>
          ) : null}
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

/** Accept the exact word (simplified or traditional) or its toneless pinyin. */
function answerMatches(typed: string, surface: string, trad?: string, pinyinMarks?: string): boolean {
  const cleaned = typed.replace(/\s+/g, "").trim();
  if (!cleaned) return false;
  if (/[㐀-鿿]/.test(cleaned)) return cleaned === surface || (!!trad && cleaned === trad);
  if (!pinyinMarks) return false;
  const strip = (s: string) =>
    s.normalize("NFD").replace(/\p{M}/gu, "").replace(/['\s·]/g, "").toLowerCase();
  return strip(cleaned) === strip(pinyinMarks);
}
