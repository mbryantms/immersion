import { ArrowUpDown, Headphones, LibraryBig, Video } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ContinueCard, SeriesCard } from "@/components/media/MediaCards";
import { EmptyState, Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SeriesSummary } from "../api/types";
import { useLibrary } from "../api/queries";

type Sort = "level" | "coverage" | "title";
type Kind = "all" | "video" | "podcast";

export default function LibraryPage() {
  const { data, isLoading } = useLibrary();
  const [sort, setSort] = useState<Sort>("level");
  const [kind, setKind] = useState<Kind>("all");

  const series = useMemo(() => (data?.series ?? []).filter((item) => kind === "all" || item.kind === kind), [data, kind]);
  const sections = useMemo(() => makeSections(series, sort), [series, sort]);

  return (
    <Page>
      <PageHeader
        eyebrow="Immersion library"
        title="Choose your next context"
        description="Sort by familiarity when you want easier input, or browse by level when you want a structured progression."
        actions={
          <Select value={sort} onValueChange={(value) => setSort(value as Sort)}>
            <SelectTrigger className="w-44"><ArrowUpDown className="size-3.5" /><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="level">Level order</SelectItem><SelectItem value="coverage">Most familiar</SelectItem><SelectItem value="title">Title A–Z</SelectItem></SelectContent>
          </Select>
        }
      />

      {isLoading ? <LibrarySkeleton /> : (
        <>
          {!!data?.continue.length && (
            <section>
              <SectionHeader title="Continue" description="Resume recent video and podcast sessions" />
              <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-none">{data.continue.map((item) => <ContinueCard key={item.item_id} item={item} />)}</div>
            </section>
          )}

          <section>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <SectionHeader title="Browse series" description={`${series.length} collection${series.length === 1 ? "" : "s"}`} />
              <Tabs value={kind} onValueChange={(value) => setKind(value as Kind)}>
                <TabsList>
                  <TabsTrigger value="all"><LibraryBig className="mr-1 size-3.5" />All</TabsTrigger>
                  <TabsTrigger value="video"><Video className="mr-1 size-3.5" />Video</TabsTrigger>
                  <TabsTrigger value="podcast"><Headphones className="mr-1 size-3.5" />Podcasts</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {!series.length ? (
              <EmptyState title={kind === "all" ? "Your library is empty" : `No ${kind} series yet`} description="Add a media root in Admin and scan it to make new immersion material available." action={{ label: "Open Admin", href: "/admin" }} icon={<LibraryBig className="size-5" />} />
            ) : (
              <div className="space-y-8">
                {sections.map(({ heading, description, list }) => (
                  <section key={heading}>
                    <SectionHeader title={heading} description={description} />
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{list.map((item) => <SeriesCard key={item.id} series={item} />)}</div>
                  </section>
                ))}
              </div>
            )}
          </section>

          {!!series.length && <div className="flex justify-center"><Button asChild variant="ghost" size="sm" className="text-muted-foreground"><Link to="/search">Search inside every transcript</Link></Button></div>}
        </>
      )}
    </Page>
  );
}

function makeSections(series: SeriesSummary[], sort: Sort) {
  if (sort === "coverage") return [{ heading: "Most comprehensible first", description: "Based on words already known or ignored", list: [...series].sort((a, b) => (b.coverage ?? -1) - (a.coverage ?? -1)) }];
  if (sort === "title") return [{ heading: "All series", description: "Alphabetical order", list: [...series].sort((a, b) => a.title.localeCompare(b.title)) }];
  const byLevel = new Map<number | null, SeriesSummary[]>();
  for (const item of series) byLevel.set(item.level, [...(byLevel.get(item.level) ?? []), item]);
  return [...byLevel.keys()].sort((a, b) => (a ?? 99) - (b ?? 99)).map((level) => ({
    heading: level ? `Level ${level}` : "Open-ended input",
    description: level ? "Graded material" : "Podcasts and uncategorized media",
    list: byLevel.get(level)!,
  }));
}

function LibrarySkeleton() {
  return <div className="space-y-8"><div><Skeleton className="mb-3 h-4 w-28" /><div className="flex gap-3"><Skeleton className="h-52 w-64 rounded-2xl" /><Skeleton className="h-52 w-64 rounded-2xl" /></div></div><div><Skeleton className="mb-3 h-4 w-36" /><div className="grid grid-cols-2 gap-3 sm:grid-cols-4"><Skeleton className="h-52 rounded-2xl" /><Skeleton className="h-52 rounded-2xl" /><Skeleton className="h-52 rounded-2xl" /><Skeleton className="h-52 rounded-2xl" /></div></div></div>;
}
