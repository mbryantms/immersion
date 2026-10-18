import SceneInbox from "../components/SceneInbox";
import LearnerProfileCard from "../components/LearnerProfileCard";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpen, BookmarkPlus, Brain, Clock3, Headphones, Layers3, Search, Sparkles, Target } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { ContinueCard } from "@/components/media/MediaCards";
import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { post } from "../api/client";
import { useDashboard, useLibrary, useRecommendations } from "../api/queries";
import { formatPinyin } from "../lib/pinyin";
import { usePrefs } from "../lib/prefs";

export default function HomePage() {
  const [population, setPopulation] = useState<"library" | "encountered">("library");
  const { data: stats, isLoading: statsLoading } = useDashboard(population);
  const { data: library, isLoading: libraryLoading } = useLibrary();
  const { data: recs } = useRecommendations();
  const pinyinStyle = usePrefs((p) => p.pinyinStyle);
  const qc = useQueryClient();
  const [queued, setQueued] = useState<Set<number>>(new Set());
  const weeks = stats?.weeks.slice(-6) ?? [];
  const maxMinutes = Math.max(1, ...weeks.map((week) => week.video_minutes + week.audio_minutes));

  const addToReview = (lexemeId: number, surface: string) => {
    post("/saved-items", { kind: "word", lexeme_id: lexemeId, surface })
      .then(() => {
        setQueued((prev) => new Set(prev).add(lexemeId));
        qc.invalidateQueries({ queryKey: ["dashboard"] });
        qc.invalidateQueries({ queryKey: ["saved"] });
        toast.success(`${surface} added to your review queue`);
      })
      .catch(() => toast.error(`Couldn't save ${surface}`));
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Today’s immersion"
        title="Build Mandarin from real context"
        description="Explore real Mandarin, revisit useful words, and practise understanding with less support over time."
        actions={
          <>
            <Button asChild variant="outline"><Link to="/search"><Search />Search corpus</Link></Button>
            <Button asChild><Link to="/library"><BookOpen />Open library</Link></Button>
          </>
        }
      />

      <details className="rounded-xl border border-border bg-card/40 p-4"><summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">Personalise your Mandarin practice</summary><LearnerProfileCard /></details>

      <section className="grid gap-4 lg:grid-cols-[1.35fr_.65fr]">
        <Card className="relative overflow-hidden border-primary/15 bg-gradient-to-br from-primary/[0.11] via-card to-card">
          <div className="pointer-events-none absolute -right-14 -top-20 size-64 rounded-full bg-primary/10 blur-3xl" />
          <CardHeader className="relative">
            <div className="flex items-center gap-2 text-xs font-medium text-primary"><Brain className="size-4" />Retrieval practice</div>
            <CardTitle className="mt-3 text-3xl tabular-nums">{statsLoading ? <Skeleton className="h-9 w-16" /> : stats?.review_due ?? 0}</CardTitle>
            <CardDescription>{stats?.review_due ? "context cards are ready for a short review" : "Nothing due—spend the time getting more input"}</CardDescription>
          </CardHeader>
          <CardContent className="relative flex flex-wrap items-center gap-2 pt-2">
            {stats?.review_due ? <Button asChild><Link to="/review">Start a 3–10 minute review<ArrowRight /></Link></Button> : <Button disabled>No review due</Button>}
            {!!stats?.graduated_waiting && <Button asChild variant="ghost"><Link to="/saved">{stats.graduated_waiting} ready for Anki</Link></Button>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Learning activity</CardTitle>
              <Badge variant="secondary" className="text-[10px]">last 6 weeks</Badge>
            </div>
            <CardDescription>Media minutes played · an activity estimate</CardDescription>
          </CardHeader>
          <CardContent className="pt-2">
            {statsLoading ? <Skeleton className="h-24 w-full" /> : weeks.length ? (
              <div className="flex h-24 items-end gap-2" aria-label="Weekly input minutes">
                {weeks.map((week) => {
                  const video = week.video_minutes;
                  const audio = week.audio_minutes;
                  const total = video + audio;
                  return (
                    <div key={week.week} className="flex min-w-0 flex-1 flex-col items-center gap-1.5" title={`${Math.round(total)} minutes`}>
                      <div className="flex h-16 w-full max-w-8 flex-col justify-end overflow-hidden rounded-md bg-muted/70">
                        <div className="bg-violet-400/70" style={{ height: `${(audio / maxMinutes) * 100}%` }} />
                        <div className="bg-primary/80" style={{ height: `${(video / maxMinutes) * 100}%` }} />
                      </div>
                      <span className="text-[9px] text-muted-foreground">{week.week.slice(5)}</span>
                    </div>
                  );
                })}
              </div>
            ) : <p className="py-8 text-center text-xs text-muted-foreground">Your input history will appear here.</p>}
            <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground"><span className="flex items-center gap-1"><i className="size-1.5 rounded-full bg-primary" />Video</span><span className="flex items-center gap-1"><i className="size-1.5 rounded-full bg-violet-400" />Podcast</span></div>
          </CardContent>
        </Card>
      </section>

      <SceneInbox compact />

      {!!recs?.items.length && (
        <section>
          <SectionHeader
            title="Suggested samples"
            description="Ranked by unfamiliar words, dense stretches, subtitle pace, your goal and optional ratings. Try 1–2 minutes to judge the fit."
          />
          <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-none">
            {recs.items.map((rec) => (
              <article key={rec.item_id} className="w-72 shrink-0 overflow-hidden rounded-2xl border border-border/70 bg-card/55">
                <Link to={`/watch/${rec.item_id}`} className="group block transition hover:bg-muted/30">
                  <div className="relative aspect-video overflow-hidden bg-muted">
                    <img src={rec.thumb_url} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-[1.03]" />
                    <Badge className="absolute right-2 top-2 border-0 bg-black/80 text-[10px] text-teal-200"><Target className="size-3" />{Math.round(rec.coverage * 100)}% vocabulary familiarity</Badge>
                  </div>
                  <div className="space-y-1 px-3.5 py-3">
                    <p className="truncate text-sm font-medium">{rec.title}</p>
                    <p className="text-[11px] text-muted-foreground">{rec.series_title ?? (rec.kind === "audio" ? "Podcast" : "Video")} · {rec.unknown_lexemes} unmarked word types</p>
                    {rec.unknowns_per_minute != null && <p className="text-xs text-foreground/80">{rec.unknowns_per_minute} unfamiliar occurrences/min</p>}
                  </div>
                </Link>
                <details className="border-t border-border px-3.5 text-xs"><summary className="min-h-11 cursor-pointer py-3">Why this sample?</summary>
                  <ul className="mb-3 list-disc space-y-2 pl-4 text-muted-foreground">{rec.reasons?.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  {rec.subtitle_characters_per_minute != null && <p className="mb-2 text-muted-foreground">Subtitle pace: {rec.subtitle_characters_per_minute} characters/min of cue time. Source: {rec.subtitle_source}.</p>}
                  {rec.source_warning && <p className="mb-2 text-amber-200">Automatic or unverified source; check the transcript against the audio.</p>}
                  <p className="mb-3 leading-relaxed text-muted-foreground">{rec.uncertainty ?? "Vocabulary familiarity is an estimate, not measured comprehension."} Ignored words are excluded from the vocabulary percentage.</p>
                </details>
              </article>
            ))}
          </div>
        </section>
      )}

      {(libraryLoading || !!library?.continue.length) && (
        <section>
          <SectionHeader title="Continue immersing" description="Pick up exactly where you left off" action={<Button asChild variant="ghost" size="sm"><Link to="/library">View library<ArrowRight /></Link></Button>} />
          {libraryLoading ? <div className="flex gap-3 overflow-hidden"><Skeleton className="h-52 w-64 shrink-0 rounded-2xl" /><Skeleton className="h-52 w-64 shrink-0 rounded-2xl" /></div> : (
            <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-none">{library?.continue.map((item) => <ContinueCard key={item.item_id} item={item} />)}</div>
          )}
        </section>
      )}

      <Card>
        <CardHeader><CardTitle className="text-base">Practice evidence</CardTitle><CardDescription>Last 8 weeks · task-specific results, with no combined mastery score</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          {!stats?.practice_evidence?.length && <p className="text-sm text-muted-foreground">Review and dictation results will appear here. Playing media alone records exposure.</p>}
          <div className="grid gap-3 sm:grid-cols-2">{stats?.practice_evidence?.map((evidence) => <div key={`${evidence.task}:${evidence.method}:${evidence.assistance}`} className="rounded-lg border border-border p-3 text-sm"><p className="font-medium capitalize">{evidence.task.replaceAll("_", " ")}</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{evidence.attempts} attempts · {evidence.method === "self_report" ? "self-reported result" : evidence.method === "automatic_edit_distance" ? "automatic character matching" : evidence.method === "curated_answer_key" ? "curated example key · practice" : "local learner-authored key · unvalidated"} · assistance: {evidence.assistance.replaceAll("_", " ")}</p><p className="mt-2 text-xs">{Math.round(evidence.mean_score*100)}% average {evidence.method === "self_report" ? evidence.task === "scene_meaning_reflection" ? "self-reported understanding" : "reported recall" : evidence.method === "automatic_edit_distance" ? "transcription accuracy" : "answer-key agreement"}</p></div>)}</div>
          {!!stats?.excluded_question_results && <p className="text-xs leading-relaxed text-amber-200">{stats.excluded_question_results} reported-question results are excluded from these averages. Original attempts remain in the audit history.</p>}
          <p className="text-xs leading-relaxed text-muted-foreground">These results reflect practised material. Listening comprehension, pronunciation and spontaneous production require separate assessment. Lookups can signal curiosity or a new meaning.</p>
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={<Layers3 />} label="Sentences played" value={stats?.totals.sentences_played} hint="context encounters" loading={statsLoading} />
        <MetricCard icon={<Sparkles />} label="Words explored" value={stats?.totals.lookups} hint="dictionary lookups" loading={statsLoading} />
        <MetricCard icon={<Clock3 />} label="Items saved" value={stats?.totals.saves} hint="in your learning queue" loading={statsLoading} />
      </section>

      {stats && (
        <section>
          <SectionHeader title="Words to explore" description={population === "library" ? "Unmarked or learning words across your indexed library. Indexing does not mean you have encountered them." : "Words with recorded playback since the evidence update. Counts below describe their indexed library occurrences."} />
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Word population">
            <Button className="min-h-11" variant={population === "library" ? "default" : "outline"} aria-pressed={population === "library"} onClick={() => setPopulation("library")}>In your library</Button>
            <Button className="min-h-11" variant={population === "encountered" ? "default" : "outline"} aria-pressed={population === "encountered"} onClick={() => setPopulation("encountered")}>You have encountered</Button>
          </div>
          {!stats.recurring_unknowns.length && <p role="status" className="py-4 text-sm text-muted-foreground">No words in this population yet. Playback records exposure; common beginner words remain eligible.</p>}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {stats.recurring_unknowns.map((word) => (
              <div key={word.lexeme_id} className="group flex items-center gap-3 rounded-xl border border-border/70 bg-card/55 px-3.5 py-3 transition hover:border-primary/30 hover:bg-card">
                <Link to={`/word/${word.lexeme_id}`} className="flex min-w-0 flex-1 items-center gap-3">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/8 font-zh text-xl text-foreground">{word.simplified}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-stone-300">{formatPinyin(word.pinyin, pinyinStyle) || "Recurring word"}</span>
                    <span className="text-[11px] text-muted-foreground">{word.occurrences} indexed occurrences in {word.items} sources</span>
                  </span>
                </Link>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  disabled={queued.has(word.lexeme_id)}
                  onClick={() => addToReview(word.lexeme_id, word.simplified)}
                  title={queued.has(word.lexeme_id) ? "In your review queue" : "Add to review queue"}
                  aria-label={`Add ${word.simplified} to review queue`}
                  className="shrink-0 text-muted-foreground hover:text-teal-300"
                >
                  <BookmarkPlus className={queued.has(word.lexeme_id) ? "text-teal-500" : ""} />
                </Button>
              </div>
            ))}
          </div>
        </section>
      )}

      <Card className="flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
        <div className="flex size-10 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300"><Headphones className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Anki bridge</p>
          <p className="text-xs text-muted-foreground">{stats?.anki.last_import ? `Anki vocabulary last synchronized ${String((stats.anki.last_import as { at?: string })?.at ?? "").slice(0, 10)}` : "Open Anki Desktop, then import known words from Admin."}</p>
        </div>
        <Button asChild variant="outline" size="sm"><Link to="/saved">Review export queue</Link></Button>
      </Card>
    </Page>
  );
}

function MetricCard({ icon, label, value, hint, loading }: { icon: React.ReactNode; label: string; value?: number; hint: string; loading: boolean }) {
  return (
    <Card><CardContent className="flex items-center gap-3 py-4"><div className="flex size-9 items-center justify-center rounded-xl bg-primary/8 text-primary [&_svg]:size-4">{icon}</div><div>{loading ? <Skeleton className="mb-1 h-5 w-12" /> : <p className="text-xl font-semibold tabular-nums">{value ?? 0}</p>}<p className="text-xs text-muted-foreground">{label} · {hint}</p></div></CardContent></Card>
  );
}
