import { ArrowLeft, Check, CircleX, Coffee, Headphones, LoaderCircle, Send, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { QueryError } from "@/components/ErrorBoundary";
import { LoadingPage, Page } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { postReviewOutcome, useReviewQueue } from "../api/queries";
import type { ReviewItem } from "../api/types";
import { uuid } from "../lib/events";
import { formatPinyin } from "../lib/pinyin";
import { usePrefs } from "../lib/prefs";
import { maskedParts } from "../player/studyMode";
import ExportTray from "../saved/ExportTray";

export default function ReviewPage() {
  const { data, isError, refetch } = useReviewQueue();
  const queryClient = useQueryClient();
  const pinyinStyle = usePrefs((prefs) => prefs.pinyinStyle);
  // Freeze the queue for this session: background changes must not skip cards.
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [position, setPosition] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [audioError, setAudioError] = useState(false);
  const [graduatedIds, setGraduatedIds] = useState<number[]>([]);
  const [trayIds, setTrayIds] = useState<number[] | null>(null);
  const [passed, setPassed] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopAt = useRef<number | null>(null);
  const requestId = useRef(uuid());
  const current = items?.[position];
  const context = current?.context;
  const hasAudio = !!context?.stream_url && context.item_available;
  const listening = current?.mode === "listen" && hasAudio;

  useEffect(() => { if (data && items === null) setItems(data.items); }, [data, items]);

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
    if (!audio || !context || !hasAudio) return;
    audio.currentTime = context.t0_ms / 1000;
    stopAt.current = context.t1_ms;
    setAudioError(false);
    void audio.play().catch(() => setAudioError(true));
  }, [context, hasAudio]);

  useEffect(() => {
    setRevealed(false);
    setSaveError(null);
    setAudioError(false);
    requestId.current = uuid();
    const audio = audioRef.current;
    // Word cloze answers are not spoken before recall. Sentence listening is
    // explicitly audio-first, with a visible replay fallback if autoplay fails.
    const timer = listening ? setTimeout(play, 300) : undefined;
    return () => {
      clearTimeout(timer);
      audio?.pause();
      stopAt.current = null;
    };
  }, [current?.saved_item_id, listening, play]);

  const grade = async (result: "pass" | "fail") => {
    if (!current || !revealed || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const outcome = await postReviewOutcome(current.saved_item_id, {
        result, mode: listening ? "listen" : "context", request_uuid: requestId.current,
        task: listening ? "listening_recall" : current.kind === "word" && context?.zh.includes(current.surface ?? "") ? "reading_recall" : "meaning_recall",
        assistance: "none_reported", sentence_id: context?.sentence_id,
        source_revision: context?.source_revision, context_zh: context?.zh,
      });
      if (outcome.graduated && !outcome.already_in_anki) {
        setGraduatedIds((previous) => [...new Set([...previous, current.saved_item_id])]);
      }
      if ((outcome.result ?? result) === "pass") setPassed((count) => count + 1);
      audioRef.current?.pause();
      setPosition((value) => value + 1);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["saved"] });
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    } catch {
      setSaveError("Your result could not be confirmed. Retry the same choice, or reload the queue if this item was reviewed elsewhere.");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const reloadQueue = async () => {
    const result = await refetch();
    if (result.data) {
      setItems(result.data.items);
      setPosition(0);
      setRevealed(false);
      setSaveError(null);
      requestId.current = uuid();
    }
  };

  if (isError && items === null) return <QueryError onRetry={() => void refetch()} />;
  if (items === null) return <LoadingPage label="Preparing review" />;

  if (!current) {
    return (
      <Page size="narrow" className="flex min-h-[65vh] items-center justify-center">
        <Card className="w-full border-primary/15 bg-gradient-to-br from-primary/[0.07] to-card text-center">
          <CardContent className="flex flex-col items-center py-12">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Coffee className="size-7" /></div>
            <h1 className="mt-5 text-2xl font-semibold">{position ? "Session complete" : "Nothing due right now"}</h1>
            <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">{position ? `You reviewed ${position} items: ${passed} recalled and ${position - passed} to practise again. Return to your listening and reading while those memories settle.` : "Your queue is clear. Save useful words or sentences as you explore your library."}</p>
            {graduatedIds.length > 0 && <Button className="mt-5" onClick={() => setTrayIds(graduatedIds)}><Send />Export {graduatedIds.length} to Anki</Button>}
            <Button asChild variant="ghost" className="mt-3"><Link to="/"><ArrowLeft />Back home</Link></Button>
          </CardContent>
        </Card>
        {trayIds && <ExportTray savedItemIds={trayIds} onClose={() => setTrayIds(null)} />}
      </Page>
    );
  }

  const cloze = !listening && current.kind === "word" && !!context && !!current.surface && context.zh.includes(current.surface);
  const word = context?.words.find((word) => word.type === "zh" && word.t === current.surface);
  const senses = current.answer?.senses.length ? current.answer.senses : word?.gloss ?? [];
  const pinyin = word?.py?.join(" ") || formatPinyin(current.answer?.pinyin, pinyinStyle);
  const feedbackAvailable = current.kind === "word" ? senses.length > 0 || !!context?.en : !!context?.en;

  return (
    <Page size="narrow">
      <header className="space-y-4">
        <h1 className="text-2xl font-semibold">Review in context</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="ghost" size="sm" className="-ml-2"><Link to="/"><ArrowLeft />Exit review</Link></Button>
          <span className="grow" />
          <Badge variant="secondary"><Headphones className="size-3" />{listening ? "Listening recall" : cloze ? "Reading recall" : "Meaning recall"}</Badge>
          <Badge variant="outline">Step {current.rung + 1}</Badge>
        </div>
        <div className="flex items-center gap-3"><Progress value={items.length ? position / items.length * 100 : 0} aria-label="Review session progress" className="h-1.5" /><span className="shrink-0 text-sm tabular-nums text-muted-foreground">{position + 1} / {items.length}</span></div>
      </header>

      <Card className="min-h-[360px] border-border bg-card shadow-xl shadow-black/10" aria-busy={saving}>
        {hasAudio && <audio ref={audioRef} src={context!.stream_url!} preload="metadata" onError={() => setAudioError(true)} />}
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-xl">{listening ? "What did you hear?" : cloze ? "Recall the missing word" : "What does this mean?"}</CardTitle>
              <CardDescription className="mt-2 leading-relaxed">{listening ? "Listen, form a meaning, then reveal the sentence." : cloze ? "Try to recall the word before revealing the answer or playing its audio." : "Recall the meaning before checking the answer."}</CardDescription>
            </div>
            {hasAudio && (listening || revealed) && <Button variant="secondary" size="icon-lg" className="shrink-0 rounded-full" onClick={play} aria-label="Replay sentence audio"><Volume2 /></Button>}
          </div>
          {audioError && <p role="status" className="mt-3 text-sm text-amber-200">Audio did not start. Try Replay, or reveal the text to continue.</p>}
          {!hasAudio && <p className="mt-3 text-xs text-muted-foreground">Text practice · source audio is unavailable.</p>}
        </CardHeader>
        <CardContent className="space-y-6 pt-4">
          <div className="flex min-h-28 items-center justify-center rounded-xl bg-background/40 px-4 py-6 text-center">
            {listening && !revealed ? <p className="text-muted-foreground">Listen first. The text is hidden.</p> : <p lang="zh" className="font-zh text-2xl leading-relaxed sm:text-3xl">{cloze && !revealed ? <Cloze text={context!.zh} surface={current.surface!} /> : context?.zh || current.surface || "Saved sentence"}</p>}
          </div>
          {!revealed ? <Button size="lg" className="w-full" onClick={() => setRevealed(true)}>Reveal {current.kind === "word" ? "answer" : "sentence"}</Button> : (
            <>
              <section aria-label="Answer feedback" className="space-y-3 rounded-xl border border-primary/20 bg-primary/5 p-4">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-primary">Check your understanding</h2>
                {current.kind === "word" && <p><span lang="zh" className="font-zh text-2xl">{current.surface}</span>{pinyin && <span className="ml-3 text-muted-foreground">{pinyin}</span>}</p>}
                {senses.length > 0 && <ul className="space-y-2 text-sm leading-relaxed">{senses.map((sense, index) => <li key={index}>{sense.py && <span className="mr-2 text-primary/90">{formatPinyin(sense.py, pinyinStyle)}</span>}{sense.defs.join("; ")}</li>)}</ul>}
                {context?.en && <p lang="en" className="border-t border-border pt-3 text-sm leading-relaxed text-muted-foreground">{context.en}</p>}
                {!feedbackAvailable && <p className="text-sm leading-relaxed text-amber-200">No definition or translation is available. Check the source before marking this recalled.</p>}
                {senses.length > 1 && <p className="text-xs text-muted-foreground">Dictionary alternatives are shown; choose the meaning that fits this sentence.</p>}
              </section>
              {saveError && <div role="alert" className="space-y-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4"><p className="text-sm leading-relaxed">{saveError}</p><Button variant="outline" onClick={() => void reloadQueue()}>Reload queue</Button></div>}
              <div className="grid grid-cols-2 gap-3 border-t border-border pt-5">
                <Button size="lg" variant="secondary" disabled={saving} onClick={() => void grade("fail")}><CircleX />Practise again</Button>
                <Button size="lg" disabled={saving} onClick={() => void grade("pass")}>{saving ? <LoaderCircle className="animate-spin" /> : <Check />}{saving ? "Saving…" : "Recalled"}</Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
      <p className="text-center text-sm leading-relaxed text-muted-foreground">Use “Recalled” when you understood before revealing. Initial practice is followed by reviews after 1, 3, and 7 days.</p>
    </Page>
  );
}

function Cloze({ text, surface }: { text: string; surface: string }) {
  return <>{maskedParts(text, surface).map((part, index) => <span key={index}>{index > 0 && <span aria-label="missing word" className="mx-1 inline-block min-w-12 rounded-md border border-dashed border-primary/40 bg-primary/5 px-2 text-primary">{"＿".repeat(Math.min(6, Math.max(2, surface.length)))}</span>}{part}</span>)}</>;
}
