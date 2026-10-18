import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../api/client";
import type { GuidedScene } from "../api/types";
import { LoadingPage, Page } from "../components/layout/Page";
import { QueryError } from "../components/ErrorBoundary";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import { voiceKey } from "../guided/recordings";
import ShadowingRecorder from "../guided/ShadowingRecorder";
import QuestionEditor from "../guided/QuestionEditor";
import SceneVocabulary from "../guided/SceneVocabulary";
import { track, uuid } from "../lib/events";

const stages = ["watch", "clarify", "reduce", "check", "complete"] as const;
const names = { watch: "Watch or listen", clarify: "Clarify", reduce: "Less support", check: "Check meaning", complete: "Revisit later" };
type Pending = { path: string; body: Record<string, unknown> };

export default function ScenePage() {
  const sceneId = Number(useParams().id);
  const query = useQuery({ queryKey: ["scene", sceneId], queryFn: () => get<GuidedScene>(`/scenes/${sceneId}`), refetchOnWindowFocus: false });
  const qc = useQueryClient();
  const media = useRef<HTMLMediaElement | null>(null);
  const heading = useRef<HTMLHeadingElement | null>(null);
  const pending = useRef<Pending | null>(null);
  const [choice, setChoice] = useState<number | null>(null);
  const [mediaError, setMediaError] = useState(false);
  const [reportReason, setReportReason] = useState("");
  const mutation = useMutation({ mutationFn: (request: Pending) => post<GuidedScene>(request.path, request.body), onSuccess: (data) => {
    pending.current = null; qc.setQueryData(["scene", sceneId], data);
    for (const key of [["scenes"], ["dashboard"]]) void qc.invalidateQueries({ queryKey: key });
  } });
  const scene = query.data;
  useEffect(() => { media.current?.pause(); if (media.current && media.current.readyState >= 1 && scene) media.current.currentTime = scene.snapshot.t0/1000; setChoice(null); setMediaError(false); heading.current?.focus({ preventScroll: true }); }, [scene?.stage, scene?.id]);
  useEffect(() => () => { media.current?.pause(); }, []);
  if (query.isPending) return <LoadingPage label="Loading guided scene" />;
  if (query.isError || !scene) return <QueryError onRetry={() => void query.refetch()} />;
  const act = (action: string, fields: Record<string, unknown> = {}) => {
    if (pending.current) return;
    const request = { path: `/scenes/${sceneId}/${action}`, body: { request_uuid: uuid(), expected_revision: scene.revision, ...fields } };
    pending.current = request; mutation.mutate(request);
  };
  const MediaSurface = scene.snapshot.kind === "audio" ? "audio" : "video";
  const busy = mutation.isPending || !!pending.current;
  const stageIndex = stages.indexOf(scene.stage);
  const showChinese = scene.stage === "watch" || scene.stage === "clarify" || scene.goal === "read" || !!scene.support[`${scene.stage}_text`];
  const showEnglish = scene.stage === "watch" || scene.stage === "clarify" || !!scene.support[`${scene.stage}_translation`];
  const feedback = scene.support.answer_feedback;
  const nextStage = stages[stageIndex+1];
  const boundMedia = () => {
    const element = media.current;
    if (!element) return;
    if (Number.isFinite(element.duration) && element.duration > 0 && scene.snapshot.t1 > element.duration*1000+100) { element.pause(); setMediaError(true); return; }
    if (element.currentTime*1000 >= scene.snapshot.t1) { element.pause(); if (element.currentTime*1000 > scene.snapshot.t1+30) element.currentTime = scene.snapshot.t1/1000; }
    else if (element.currentTime*1000 < scene.snapshot.t0-100) element.currentTime = scene.snapshot.t0/1000;
  };
  return <Page size="medium">
    <div className="flex flex-wrap items-center justify-between gap-3"><Button asChild variant="ghost" className="min-h-11"><Link to="/practice">All guided practice</Link></Button><Button asChild variant="outline" className="min-h-11"><Link to={`/watch/${scene.item_id}?t=${scene.snapshot.t0}`}>Open full source</Link></Button></div>
    <header className="space-y-3"><div className="flex flex-wrap gap-2"><Badge variant="secondary">{scene.goal === "read" ? "Reading scene" : "Listening scene"}</Badge><Badge variant="outline">{Math.round((scene.snapshot.t1-scene.snapshot.t0)/1000)} seconds</Badge>{scene.revisits>0 && <Badge variant="outline">Delayed revisit {scene.revisits}</Badge>}</div><h1 ref={heading} tabIndex={-1} className="text-2xl font-semibold outline-none">{names[scene.stage]}</h1><p className="break-words text-sm text-muted-foreground">{scene.snapshot.title}</p><Progress value={(stageIndex+1)/stages.length*100} aria-label="Guided scene progress" /><ol className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">{stages.map((stage, index) => <li key={stage} aria-current={stage === scene.stage ? "step" : undefined} className={stage === scene.stage ? "font-semibold text-primary" : ""}>{index+1}. {names[stage]}</li>)}</ol></header>
    {mutation.isError && <div role="alert" className="space-y-3 rounded-xl border border-destructive/30 p-4 text-sm"><p>Your change could not be confirmed. Retry the same request, or reload if another tab changed this scene.</p><div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={mutation.isPending} onClick={() => pending.current && mutation.mutate(pending.current)}>Retry change</Button><Button className="min-h-11" variant="ghost" onClick={() => { pending.current = null; mutation.reset(); void query.refetch(); }}>Reload scene</Button></div></div>}
    {!scene.source_current && <p role="status" className="rounded-xl border border-amber-400/30 p-4 text-sm leading-relaxed text-amber-200">The source changed. This original scene snapshot is preserved. Audio and keyed grading are paused to avoid practicing against different text; create a new scene from the source to continue with updated material.</p>}
    {scene.stage !== "complete" ? <>
      <Card><CardHeader><CardTitle className="text-base">Your scene</CardTitle></CardHeader><CardContent className="space-y-4">
        {scene.stream_url ? <MediaSurface ref={(element: HTMLMediaElement | null) => { media.current = element; }} src={scene.stream_url} controls playsInline preload="metadata" className={`w-full rounded-xl bg-black ${scene.snapshot.kind === "audio" ? "h-20" : "max-h-[55vh]"}`} onLoadedMetadata={() => { const element = media.current; if (!element) return; if (Number.isFinite(element.duration) && scene.snapshot.t1 > element.duration*1000+100) { setMediaError(true); return; } element.currentTime = scene.snapshot.t0/1000; }} onTimeUpdate={boundMedia} onSeeking={boundMedia} onError={() => setMediaError(true)} onPlay={() => track("scene_playback", { item_id: scene.item_id, study_mode: scene.goal, data: { scene_id: scene.id, stage: scene.stage, source_t0: scene.snapshot.t0, source_t1: scene.snapshot.t1 } })} /> : <p className="text-sm text-muted-foreground">Source audio is unavailable. The saved text remains available for reading and reflection.</p>}
        {scene.stream_url && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => { const element = media.current; if (!element) return; element.currentTime = scene.snapshot.t0/1000; setMediaError(false); void element.play().catch(() => setMediaError(true)); act("hint", { kind: "replay" }); }}>Replay scene</Button>}
        {mediaError && <p role="alert" className="text-sm text-amber-200">Playback failed. Try the full source, or use reading and reflection. A playback click does not count as understanding.</p>}
        <p className="text-xs leading-relaxed text-muted-foreground">Playback is bounded to this scene. Subtitles burned into the original video cannot be hidden. Translations may be loose or automatic.</p>
        {showChinese ? <div lang="zh" className="space-y-3">{scene.snapshot.lines.map((line) => <div key={line.id}><p className="font-zh text-lg leading-loose">{line.zh}</p>{showEnglish && line.en && <p lang="en" className="text-sm leading-relaxed text-muted-foreground">{line.en}<span className="ml-2 text-[10px]">{line.translation_source === "ai" ? "AI translation" : line.translation_source === "user" ? "Local translation" : "Source translation"}</span></p>}</div>)}</div> : <p className="py-8 text-center text-sm text-muted-foreground">Listen for the meaning. The scene transcript is hidden.</p>}
        {(scene.stage === "reduce" || scene.stage === "check") && <div className="flex flex-wrap gap-2">{!showChinese && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => act("hint", { kind: "text" })}>Reveal Chinese as a hint</Button>}{!showEnglish && <Button className="min-h-11" variant="outline" disabled={busy} onClick={() => act("hint", { kind: "translation" })}>Reveal translation as a hint</Button>}</div>}
        {showEnglish && !showChinese && <div className="space-y-2">{scene.snapshot.lines.map((line) => line.en && <p key={line.id} lang="en" className="text-sm text-muted-foreground">{line.en}</p>)}</div>}
      </CardContent></Card>
      {scene.stage === "watch" && <p className="text-sm leading-relaxed text-muted-foreground">Watch or listen for the overall situation. This is a self-paced study cycle; moving to the next step does not certify that you understood it.</p>}
      {(scene.stage === "watch" || scene.stage === "clarify") && <ShadowingRecorder key={voiceKey(scene)} scene={scene} pauseSource={() => media.current?.pause()} replaySource={() => { const element = media.current; if (!element || busy) return; element.currentTime = scene.snapshot.t0/1000; void element.play().catch(() => setMediaError(true)); act("hint", { kind: "replay" }); }} />}
      {scene.stage === "clarify" && <SceneVocabulary sceneId={scene.id} />}
      {scene.stage === "reduce" && <p className="text-sm leading-relaxed text-muted-foreground">{scene.goal === "listen" ? "Listen again without the transcript." : "Read again without the English translation."} Try to state what happened and who did what. Use a deliberate hint when needed; assistance is retained with the result.</p>}
      {scene.stage === "check" && <Card><CardHeader><CardTitle className="text-base">Check the meaning you formed</CardTitle></CardHeader><CardContent className="space-y-4">
        {scene.question && !scene.support.checked && <section className="space-y-4" aria-label="Local meaning question"><p className="text-xs leading-relaxed text-muted-foreground">Locally authored and reviewed · not externally validated. Its author has seen the answer. This checks practiced material, not transfer to an unseen scene.</p><fieldset className="space-y-3"><legend className="mb-3 text-base font-medium">{scene.question.prompt}</legend>{scene.question.choices.map((text, index) => <label key={index} className="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border border-border p-4 text-sm"><input type="radio" name="meaning-choice" checked={choice === index} onChange={() => setChoice(index)} disabled={busy} /><span>{text}</span></label>)}</fieldset><Button className="min-h-11" disabled={choice === null || busy || !scene.source_current || (scene.goal === "listen" && (!scene.stream_url || mediaError))} onClick={() => act("answer", { question_id: scene.question!.id, question_revision: scene.question!.revision, choice })}>Check this answer</Button></section>}
        {feedback && !scene.support.question_reported && <section aria-label="Meaning answer feedback" className="space-y-3"><p className="font-medium text-primary">{feedback.correct ? "Matches the local answer key" : "Compare the interpretations"}</p>{feedback.explanations.map((explanation, index) => <p key={index} className="text-sm leading-relaxed"><strong>{index === feedback.answer ? "Key answer" : "Alternative"}: </strong>{explanation}</p>)}</section>}
        {!!scene.support.question_reported && <p role="status" className="text-sm text-amber-200">Question suspended. Its earlier keyed results are excluded from summaries; you can record a reflection instead.</p>}
        {!scene.support.checked && <div className="space-y-3"><p className="text-sm leading-relaxed text-muted-foreground">{scene.question ? "Or record a reflection instead of a keyed result." : "There is no reviewed question for this scene. Reflect on the meaning; this is self-report rather than an objective test."}</p><div className="flex flex-wrap gap-3"><Button className="min-h-11" variant="outline" disabled={busy} onClick={() => act("reflection", { understood: false })}>I need more support</Button><Button className="min-h-11" disabled={busy} onClick={() => act("reflection", { understood: true })}>I could explain the meaning</Button></div></div>}
        {scene.support.checked && typeof scene.support.reflection === "boolean" && <p role="status" className="text-sm text-primary">Reflection saved: {scene.support.reflection ? "you could explain the meaning" : "you need more support"}. This is a self-report on a practiced scene.</p>}
        {scene.question && <details className="rounded-lg border border-border p-3"><summary className="min-h-11 cursor-pointer py-3 text-xs">Report an ambiguous or incorrect question</summary><label className="block space-y-2 text-sm"><span>Question issue</span><textarea className="min-h-20 w-full rounded-md border border-input bg-transparent p-3" value={reportReason} maxLength={1000} onChange={(event) => setReportReason(event.target.value)} /></label><Button className="mt-3 min-h-11" variant="outline" disabled={busy || !reportReason.trim()} onClick={() => act("report-question", { question_id: scene.question!.id, reason: reportReason.trim() })}>Report and suspend question</Button></details>}
      </CardContent></Card>}
      {(scene.stage === "watch" || scene.stage === "clarify") && !scene.support.checked && <QuestionEditor scene={scene} disabled={busy} onSave={(question) => act("questions", { question, reviewed: true })} />}
      {nextStage && <Button className="min-h-12 w-full sm:w-auto" disabled={busy || (nextStage === "complete" && !scene.support.checked)} onClick={() => act("step", { stage: nextStage })}>{mutation.isPending ? "Saving…" : nextStage === "complete" ? "Finish and schedule a revisit" : `Continue: ${names[nextStage]}`}</Button>}
    </> : <Card><CardHeader><CardTitle className="text-xl">This scene is ready to revisit later</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm leading-relaxed text-muted-foreground">Your practice and assistance are recorded separately from vocabulary knowledge. The next revisit is {scene.due_at?.slice(0,10)}. Repeated practice of this same scene does not establish understanding of new material.</p><Button className="min-h-11" disabled={busy || !scene.due_at || new Date(scene.due_at).getTime()>Date.now()} onClick={() => act("revisit")}>Start due revisit</Button><Button asChild className="ml-2 min-h-11" variant="outline"><Link to="/practice">Explore Mandarin constructions</Link></Button></CardContent></Card>}
  </Page>;
}
