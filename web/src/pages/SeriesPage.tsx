import { ArrowLeft, CheckCircle2, ListVideo, PlayCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { EpisodeCard } from "@/components/media/MediaCards";
import { EmptyState, LoadingPage, Page, PageHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSeries } from "../api/queries";

type View = "all" | "ready" | "unfinished";

export default function SeriesPage() {
  const id = Number(useParams().id);
  const { data, isLoading } = useSeries(id);
  const [view, setView] = useState<View>("all");
  const items = useMemo(() => (data?.items ?? []).filter((item) => view === "all" || (view === "ready" ? item.ready : !item.completed)), [data, view]);

  if (isLoading) return <LoadingPage label="Loading series" />;
  if (!data) return null;

  const ready = data.items.filter((item) => item.ready).length;
  const completed = data.items.filter((item) => item.completed).length;
  const next = data.items.find((item) => item.ready && !item.completed);

  return (
    <Page>
      <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit text-muted-foreground"><Link to="/library"><ArrowLeft />Back to library</Link></Button>
      <PageHeader
        eyebrow={data.level ? `Graded series · Level ${data.level}` : "Immersion series"}
        title={data.title}
        description={`${data.items.length} episodes · ${ready} ready to watch · ${completed} completed`}
        actions={next && <Button asChild><Link to={`/watch/${next.id}`}><PlayCircle />{next.position_ms > 0 ? "Continue series" : "Start next episode"}</Link></Button>}
      />

      <Card className="bg-card/45">
        <CardContent className="grid gap-4 py-4 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <div className="mb-2 flex items-center justify-between text-xs"><span className="text-muted-foreground">Series progress</span><span className="font-medium tabular-nums">{completed} of {data.items.length}</span></div>
            <Progress value={data.items.length ? (completed / data.items.length) * 100 : 0} className="h-1.5" />
          </div>
          <div className="flex gap-2"><Badge variant="secondary"><CheckCircle2 className="size-3" />{completed} complete</Badge><Badge variant="secondary"><ListVideo className="size-3" />{ready} available</Badge></div>
        </CardContent>
      </Card>

      <section>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Episodes</h2>
          <Tabs value={view} onValueChange={(value) => setView(value as View)}><TabsList><TabsTrigger value="all">All</TabsTrigger><TabsTrigger value="ready">Ready</TabsTrigger><TabsTrigger value="unfinished">Unfinished</TabsTrigger></TabsList></Tabs>
        </div>
        {items.length ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{items.map((episode, index) => <EpisodeCard key={episode.id} episode={episode} index={index} />)}</div> : <EmptyState title="No episodes in this view" description="Try another filter to see the rest of the series." />}
      </section>
    </Page>
  );
}
