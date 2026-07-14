import { ArrowUpRight, Headphones, Search, SearchX, Sparkles, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { EmptyState, Page, PageHeader } from "@/components/layout/Page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useSearch } from "../api/queries";

const examples = ["磨坊", "mò fáng", "I think"];

export default function SearchPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const { data, isFetching } = useSearch(query);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const next = input.trim();
    if (next) setQuery(next);
  };

  return (
    <Page size="medium">
      <PageHeader eyebrow="Corpus search" title="Find language in context" description="Search simplified or traditional Chinese, pinyin, or English across every indexed transcript." />

      <Card className="border-primary/15 bg-gradient-to-br from-primary/[0.07] to-card">
        <CardContent className="py-5">
          <form onSubmit={submit} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input autoFocus value={input} onChange={(event) => setInput(event.target.value)} placeholder="Search 磨坊, mò fáng, or miller…" className="h-11 bg-background/45 pl-9 pr-9 font-zh text-base" />
              {input && <Button type="button" variant="ghost" size="icon-sm" className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground" onClick={() => setInput("")} aria-label="Clear search"><X /></Button>}
            </div>
            <Button type="submit" className="h-11 px-5" disabled={!input.trim() || isFetching}>{isFetching ? "Searching…" : "Search"}</Button>
          </form>
          {!query && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><Sparkles className="size-3.5" /><span>Try</span>{examples.map((example) => <Button key={example} variant="secondary" size="xs" className="font-zh" onClick={() => { setInput(example); setQuery(example); }}>{example}</Button>)}</div>}
        </CardContent>
      </Card>

      {isFetching ? <div className="space-y-2">{[1, 2, 3].map((item) => <Skeleton key={item} className="h-28 rounded-2xl" />)}</div> : data ? (
        <section>
          <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Results for “{data.query}”</h2><Badge variant="secondary">{data.results.length} matches</Badge></div>
          {!data.results.length ? <EmptyState title="No matching context" description="Try another form of the word, remove tone marks, or search a shorter phrase." icon={<SearchX className="size-5" />} /> : (
            <ul className="space-y-2">
              {data.results.map((result) => (
                <li key={result.sentence_id}>
                  <Card className="transition hover:border-primary/25 hover:bg-card">
                    <CardContent className="py-4">
                      <p className="font-zh text-lg leading-relaxed text-foreground">{result.zh}</p>
                      {result.en && <p className="mt-1 text-sm text-muted-foreground">{result.en}</p>}
                      <div className="mt-3 flex items-center gap-2">
                        {result.item_kind === "audio" && <Badge variant="secondary"><Headphones className="size-3" />Podcast</Badge>}
                        <Button asChild variant="ghost" size="sm" className="ml-auto text-primary"><Link to={`/watch/${result.item_id}?t=${result.t0_ms}`}>{result.item_title ?? "Open source"} · {fmt(result.t0_ms)}<ArrowUpRight /></Link></Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <EmptyState title="Search your immersion history" description="Results preserve the original sentence, translation, source, and timestamp so you can hear the language again." icon={<Search className="size-5" />} />
      )}
    </Page>
  );
}

function fmt(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
