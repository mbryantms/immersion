import { CaptionsOff, CheckCircle2, Clock3, Headphones, Play } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { ContinueItem, EpisodeSummary, SeriesSummary } from "@/api/types";
import { cn } from "@/lib/utils";

export function ContinueCard({ item, className }: { item: ContinueItem; className?: string }) {
  const percent = item.duration_ms ? Math.min(100, (100 * item.position_ms) / item.duration_ms) : 0;
  return (
    <Link to={`/watch/${item.item_id}`} className={cn("group block w-64 shrink-0 overflow-hidden rounded-2xl border border-border/70 bg-card/70 transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-xl hover:shadow-black/15", className)}>
      <div className="relative aspect-video overflow-hidden bg-muted">
        <img src={item.thumb_url} alt="" className="size-full object-cover transition duration-300 group-hover:scale-[1.025]" />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/20">
          <span className="flex size-10 scale-90 items-center justify-center rounded-full bg-background/90 text-primary opacity-0 shadow-xl transition group-hover:scale-100 group-hover:opacity-100"><Play className="ml-0.5 size-4 fill-current" /></span>
        </span>
        <Progress value={percent} className="absolute inset-x-0 bottom-0 h-1 rounded-none bg-black/35" />
      </div>
      <div className="px-3 py-2.5">
        <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{percent > 0 ? `${Math.round(percent)}% complete` : "Ready to begin"}</p>
      </div>
    </Link>
  );
}

export function SeriesCard({ series }: { series: SeriesSummary }) {
  return (
    <Link to={`/series/${series.id}`} className="group overflow-hidden rounded-2xl border border-border/70 bg-card/70 transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-xl hover:shadow-black/15">
      <div className="relative aspect-video overflow-hidden bg-muted">
        {series.cover_url ? (
          <img src={series.cover_url} alt="" className="size-full object-cover transition duration-300 group-hover:scale-[1.025]" />
        ) : (
          <div className="flex size-full items-center justify-center bg-gradient-to-br from-primary/10 to-muted font-zh text-3xl text-muted-foreground">{series.title[0]}</div>
        )}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-2">
          {series.kind === "podcast" ? (
            <Badge className="gap-1 border-white/8 bg-black/65 text-[10px] text-stone-200 backdrop-blur"><Headphones className="size-3" /> Podcast</Badge>
          ) : <span />}
          {series.coverage != null && <Badge className="border-white/8 bg-black/65 text-[10px] tabular-nums text-teal-200 backdrop-blur">{Math.round(series.coverage * 100)}% familiar</Badge>}
        </div>
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-medium text-foreground">{series.title}</p>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{series.episodes} episode{series.episodes === 1 ? "" : "s"}</span>
          <span>{series.ready}/{series.episodes} ready</span>
        </div>
        <Progress value={series.episodes ? (series.ready / series.episodes) * 100 : 0} className="mt-2 bg-muted" />
      </div>
    </Link>
  );
}

export function EpisodeCard({ episode, index }: { episode: EpisodeSummary; index: number }) {
  const percent = episode.duration_ms ? Math.min(100, (episode.position_ms / episode.duration_ms) * 100) : 0;
  const content = (
    <>
      <div className="relative aspect-video overflow-hidden bg-muted">
        <img src={episode.thumb_url} alt="" className="size-full object-cover transition duration-300 group-hover:scale-[1.025]" />
        {episode.ready && <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition group-hover:bg-black/20"><span className="flex size-10 scale-90 items-center justify-center rounded-full bg-background/90 text-primary opacity-0 shadow-xl transition group-hover:scale-100 group-hover:opacity-100"><Play className="ml-0.5 size-4 fill-current" /></span></span>}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-2">
          <Badge className="bg-black/65 text-[10px] text-stone-200 backdrop-blur">Episode {episode.ordinal ?? index + 1}</Badge>
          {episode.completed && <CheckCircle2 className="size-5 fill-emerald-400 text-emerald-950" />}
        </div>
        {percent > 0 && <Progress value={percent} className="absolute inset-x-0 bottom-0 h-1 rounded-none bg-black/35" />}
      </div>
      <div className="p-3">
        <p className="truncate text-sm font-medium text-foreground">{episode.title}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
          {episode.duration_ms && <span className="flex items-center gap-1"><Clock3 className="size-3" />{Math.round(episode.duration_ms / 60000)} min</span>}
          {!episode.ready && <span className="flex items-center gap-1 text-amber-300/80">{episode.has_zh ? "Processing" : <><CaptionsOff className="size-3" />No subtitles</>}</span>}
          {episode.coverage !== undefined && <span className="ml-auto text-primary/80">{Math.round(episode.coverage * 100)}% familiar</span>}
        </div>
        {episode.unknown_lexemes !== undefined && <p className="mt-1 text-[10px] text-muted-foreground">{episode.unknown_lexemes} words not yet known</p>}
      </div>
    </>
  );

  const className = cn("group overflow-hidden rounded-2xl border border-border/70 bg-card/70 transition", episode.ready ? "hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-xl hover:shadow-black/15" : "opacity-55");
  return episode.ready ? <Link to={`/watch/${episode.id}`} className={className}>{content}</Link> : <div className={className}>{content}</div>;
}
