import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "../api/client";
import type { LexemeInfo } from "../api/types";
import { useMiningBudget } from "../components/MiningBudgetCard";
import { Button } from "../components/ui/button";
import { formatPinyin } from "../lib/pinyin";
import { usePrefs } from "../lib/prefs";

type Candidate = LexemeInfo & { surface: string; sentence_id: number; occurrences: number };
function CandidateWord({ word, sceneId, overBudget, stale }: { word: Candidate; sceneId: number; overBudget: boolean; stale: boolean }) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState("");
  const [override, setOverride] = useState(false);
  const pinyinStyle = usePrefs((prefs) => prefs.pinyinStyle);
  const choices = word.senses.flatMap((sense) => sense.defs.map((meaning) => ({ reading: sense.py, meaning }))).slice(0, 12);
  const save = useMutation({
    mutationFn: () => { const choice = choices[Number(selected)]; return post("/saved-items", { kind: "word", lexeme_id: word.lexeme_id, surface: word.surface, sentence_id: word.sentence_id, selected_reading: choice.reading || undefined, selected_meaning: choice.meaning }); },
    onSuccess: () => { for (const key of [["mining-budget"], ["scene-vocabulary", sceneId], ["saved"], ["dashboard"], ["knowledge"], ["review-queue"]]) void qc.invalidateQueries({ queryKey: key }); },
  });
  return <div className="space-y-3 rounded-xl border border-border p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><Link className="font-zh text-xl text-primary" to={`/word/${word.lexeme_id}`}>{word.surface}</Link><span className="text-xs text-muted-foreground">{word.occurrences} occurrences in this scene</span></div>
    <label className="block space-y-2 text-sm"><span>Reading and meaning for {word.surface}</span><select className="min-h-11 w-full max-w-full rounded-md border border-input bg-background p-2 text-sm" value={selected} onChange={(event) => setSelected(event.target.value)} disabled={save.isSuccess || !!word.saved_item_id}><option value="">Choose the meaning that fits</option>{choices.map((choice, index) => <option key={index} value={index}>{formatPinyin(choice.reading, pinyinStyle)} · {choice.meaning}</option>)}</select></label>
    {!choices.length && <p className="text-xs text-muted-foreground">No dictionary meaning is available; check the source before mining this word.</p>}
    {overBudget && !word.saved_item_id && <label className="flex min-h-11 items-center gap-3 text-xs"><input type="checkbox" checked={override} onChange={(event) => setOverride(event.target.checked)} />Save this word beyond today's suggestion</label>}
    {save.isError && <p role="alert" className="text-sm text-destructive">Could not save this word. Your choice is retained; try again.</p>}
    <Button className="min-h-11" variant="outline" disabled={stale || selected === "" || save.isPending || save.isSuccess || !!word.saved_item_id || (overBudget && !override)} onClick={() => save.mutate()}>{save.isSuccess || word.saved_item_id ? "Saved for review" : save.isPending ? "Saving…" : "Save this meaning"}</Button>
  </div>;
}

export default function SceneVocabulary({ sceneId }: { sceneId: number }) {
  const query = useQuery({ queryKey: ["scene-vocabulary", sceneId], queryFn: () => get<{ items: Candidate[]; suggested_max: number; source_current: boolean }>(`/scenes/${sceneId}/vocabulary`) });
  const budget = useMiningBudget();
  const [expanded, setExpanded] = useState(false);
  return <section aria-label="Useful scene words" className="space-y-4"><div><h2 className="text-lg font-semibold">Clarify a few useful expressions</h2><p className="mt-2 text-sm leading-relaxed text-muted-foreground">{query.data?.suggested_max === 0 ? "Your daily intake suggestion is used. Clarify without saving, or deliberately choose a word beyond it." : `Start with up to ${query.data?.suggested_max ?? 3} useful words.`} Select a meaning for this context; you do not need to save every unfamiliar word.</p>{budget.data && <p className="mt-2 text-xs text-muted-foreground">{budget.data.used} new word cards today · {budget.data.remaining} within your daily suggestion. <Link className="underline" to="/settings">Adjust intake</Link></p>}</div>
    {query.isPending && <p role="status">Loading dictionary candidates…</p>}
    {query.isError && <p role="alert">Could not load candidate words. <button className="underline" onClick={() => void query.refetch()}>Retry</button></p>}
    {query.data && !query.data.items.length && <p className="text-sm text-muted-foreground">No unmarked dictionary words to suggest. You can continue without saving anything.</p>}
    {query.data && !query.data.source_current && <p role="status" className="text-sm text-amber-200">The source changed. Your scene snapshot remains readable; start a new scene before saving its words.</p>}
    {query.data?.items.slice(0, expanded ? 8 : 3).map((word) => <CandidateWord key={word.lexeme_id} word={word} sceneId={sceneId} overBudget={budget.data?.remaining === 0} stale={!query.data.source_current} />)}
    {(query.data?.items.length ?? 0)>3 && <Button className="min-h-11" variant="ghost" onClick={() => setExpanded(!expanded)}>{expanded ? "Show fewer candidates" : "Show other candidates"}</Button>}
    <p className="text-xs leading-relaxed text-muted-foreground">Suggestions use repetition within this scene and exclude already familiar/ignored words. Dictionary alternatives need your contextual judgment. Saving is preparation, not evidence of learning.</p>
  </section>;
}
