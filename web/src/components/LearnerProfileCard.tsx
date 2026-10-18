import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { get, put } from "../api/client";
import type { LearnerProfile } from "../api/types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { usePrefs } from "../lib/prefs";

const defaults: LearnerProfile = { goal: "listen", level: "unknown", script: "source", interests: [] };

export default function LearnerProfileCard() {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["learner-profile"], queryFn: () => get<LearnerProfile>("/learner-profile") });
  const [draft, setDraft] = useState(defaults);
  const [topics, setTopics] = useState("");
  const setPrefs = usePrefs((state) => state.set);
  useEffect(() => { if (query.data) { setDraft(query.data); setTopics(query.data.interests.join(", ")); } }, [query.data]);
  const save = useMutation({
    mutationFn: () => put<LearnerProfile>("/learner-profile", { ...draft, interests: topics.split(",").map((topic) => topic.trim()).filter(Boolean).slice(0, 10) }),
    onSuccess: () => { if (draft.script !== query.data?.script) setPrefs({ traditional: draft.script === "traditional" }); void qc.invalidateQueries({ queryKey: ["learner-profile"] }); void qc.invalidateQueries({ queryKey: ["recommendations"] }); toast.success("Learning preferences saved"); },
  });
  return <Card>
    <CardHeader><CardTitle className="text-base">Your Mandarin goals</CardTitle><CardDescription>Optional. Recommendations use these preferences; no words are marked known from your level.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="space-y-2 text-sm"><span>Practice goal</span><select className="h-11 w-full rounded-md border border-input bg-background px-3" value={draft.goal} onChange={(event) => setDraft({ ...draft, goal: event.target.value as LearnerProfile["goal"] })}><option value="listen">Listening</option><option value="read">Reading</option><option value="dictate">Dictation</option></select></label>
        <label className="space-y-2 text-sm"><span>Starting level</span><select className="h-11 w-full rounded-md border border-input bg-background px-3" value={draft.level} onChange={(event) => setDraft({ ...draft, level: event.target.value as LearnerProfile["level"] })}><option value="unknown">Not sure</option><option value="beginner">Beginner</option><option value="intermediate">Intermediate</option><option value="advanced">Advanced</option></select></label>
        <label className="space-y-2 text-sm"><span>Character preference</span><select className="h-11 w-full rounded-md border border-input bg-background px-3" value={draft.script} onChange={(event) => setDraft({ ...draft, script: event.target.value as LearnerProfile["script"] })}><option value="source">Source characters</option><option value="simplified">Prefer simplified</option><option value="traditional">Traditional when available</option></select></label>
      </div>
      <label className="block space-y-2 text-sm"><span>Topics or series titles</span><Input className="min-h-11" value={topics} onChange={(event) => setTopics(event.target.value)} placeholder="Travel, cooking, a favourite series" maxLength={800} /><span className="block text-xs text-muted-foreground">Comma separated. Matches titles in your local library. Character preference does not rewrite source text.</span></label>
      {query.isError && <p role="alert" className="text-sm text-destructive">Could not load preferences. <button onClick={() => void query.refetch()} className="underline">Retry</button></p>}
      {save.isError && <p role="alert" className="text-sm text-destructive">Preferences could not be saved. Try again.</p>}
      <Button className="min-h-11" disabled={query.isPending || query.isError || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save learning preferences"}</Button>
    </CardContent>
  </Card>;
}
