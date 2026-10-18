import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get } from "../api/client";
import type { SceneSummary } from "../api/types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

export const useScenes = () => useQuery({ queryKey: ["scenes"], queryFn: () => get<{ items: SceneSummary[] }>("/scenes") });

export default function SceneInbox({ compact = false }: { compact?: boolean }) {
  const query = useScenes();
  return <Card><CardHeader><CardTitle className="text-base">Guided scenes</CardTitle><CardDescription>Watch, clarify a few expressions, reduce support, check meaning, and revisit later.</CardDescription></CardHeader><CardContent className="space-y-3">
    {query.isPending && <p role="status" className="text-sm text-muted-foreground">Loading your scenes…</p>}
    {query.isError && <p role="alert" className="text-sm">Could not load scenes. <button className="underline" onClick={() => void query.refetch()}>Retry</button></p>}
    {query.data && !query.data.items?.length && <p className="text-sm text-muted-foreground">Choose “Study a short scene” in a video or podcast to begin. Construction practice is also available offline.</p>}
    {query.data?.items?.slice(0, compact ? 3 : 30).map((scene) => <Link key={scene.id} className="flex min-h-14 flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-3 text-sm transition hover:border-primary/40" to={`/scenes/${scene.id}`}><span className="min-w-0 break-words">{scene.title}<span className="mt-1 block text-xs text-muted-foreground">{Math.round(scene.duration_ms/1000)} seconds · {scene.goal === "read" ? "reading" : "listening"}</span></span><span className="text-xs text-primary">{scene.due ? "Revisit due" : scene.stage === "complete" ? `Revisit ${scene.due_at?.slice(0,10)}` : `Resume: ${scene.stage === "reduce" ? "less support" : scene.stage}`}</span></Link>)}
    {compact && <Button asChild variant="outline" className="min-h-11"><Link to="/practice">Scenes and Mandarin constructions</Link></Button>}
  </CardContent></Card>;
}
