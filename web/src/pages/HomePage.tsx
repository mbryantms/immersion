import { ArrowRight, BookOpen, Brain, Clock3, Headphones, Layers3, Search, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { ContinueCard } from "@/components/media/MediaCards";
import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard, useLibrary } from "../api/queries";

export default function HomePage() {
  const { data: stats, isLoading: statsLoading } = useDashboard();
  const { data: library, isLoading: libraryLoading } = useLibrary();
  const weeks = stats?.weeks.slice(-6) ?? [];
  const maxMinutes = Math.max(1, ...weeks.map((week) => week.video_minutes + week.audio_minutes));

  return (
    <Page>
      <PageHeader
        eyebrow="Today’s immersion"
        title="Build Mandarin from real context"
        description="Continue listening, retrieve a few saved words, and let repeated encounters—not isolated drills—guide what you learn next."
        actions={
          <>
            <Button asChild variant="outline"><Link to="/search"><Search />Search corpus</Link></Button>
            <Button asChild><Link to="/library"><BookOpen />Open library</Link></Button>
          </>
        }
      />

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
            <CardDescription>Minutes of comprehensible input</CardDescription>
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

      {(libraryLoading || !!library?.continue.length) && (
        <section>
          <SectionHeader title="Continue immersing" description="Pick up exactly where you left off" action={<Button asChild variant="ghost" size="sm"><Link to="/library">View library<ArrowRight /></Link></Button>} />
          {libraryLoading ? <div className="flex gap-3 overflow-hidden"><Skeleton className="h-52 w-64 shrink-0 rounded-2xl" /><Skeleton className="h-52 w-64 shrink-0 rounded-2xl" /></div> : (
            <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-none">{library?.continue.map((item) => <ContinueCard key={item.item_id} item={item} />)}</div>
          )}
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={<Layers3 />} label="Sentences played" value={stats?.totals.sentences_played} hint="context encounters" loading={statsLoading} />
        <MetricCard icon={<Sparkles />} label="Words explored" value={stats?.totals.lookups} hint="dictionary lookups" loading={statsLoading} />
        <MetricCard icon={<Clock3 />} label="Items saved" value={stats?.totals.saves} hint="in your learning queue" loading={statsLoading} />
      </section>

      {!!stats?.recurring_unknowns.length && (
        <section>
          <SectionHeader title="Words following you around" description="Unknown words recurring across multiple sources are usually worth noticing" />
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {stats.recurring_unknowns.map((word) => (
              <Link key={word.lexeme_id} to={`/word/${word.lexeme_id}`} className="group flex items-center gap-3 rounded-xl border border-border/70 bg-card/55 px-3.5 py-3 transition hover:border-primary/30 hover:bg-card">
                <span className="flex size-10 items-center justify-center rounded-xl bg-primary/8 font-zh text-xl text-foreground">{word.simplified}</span>
                <span className="min-w-0 flex-1"><span className="block truncate text-xs text-muted-foreground">{word.pinyin ?? "Recurring word"}</span><span className="text-[10px] text-muted-foreground">{word.occurrences} encounters in {word.items} sources</span></span>
                <ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
              </Link>
            ))}
          </div>
        </section>
      )}

      <Card className="flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
        <div className="flex size-10 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300"><Headphones className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Anki bridge</p>
          <p className="text-xs text-muted-foreground">{stats?.anki.last_import ? `Known words last synchronized ${String((stats.anki.last_import as { at?: string })?.at ?? "").slice(0, 10)}` : "Open Anki Desktop, then import known words from Admin."}</p>
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
