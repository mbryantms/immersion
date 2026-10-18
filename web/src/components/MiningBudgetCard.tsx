import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, put } from "../api/client";
import type { MiningBudget } from "../api/types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

export const useMiningBudget = () => useQuery({ queryKey: ["mining-budget"], queryFn: () => get<MiningBudget>("/mining/budget") });

export default function MiningBudgetCard() {
  const query = useMiningBudget();
  const qc = useQueryClient();
  const [value, setValue] = useState("5");
  useEffect(() => { if (query.data) setValue(String(query.data.daily_word_budget)); }, [query.data]);
  const save = useMutation({ mutationFn: () => put<MiningBudget>("/mining/budget", { daily_word_budget: Number(value) }), onSuccess: (data) => qc.setQueryData(["mining-budget"], data) });
  return <Card><CardHeader><CardTitle className="text-base">A manageable vocabulary intake</CardTitle><CardDescription>A daily suggestion for new word cards, not a learning score or a hard limit.</CardDescription></CardHeader><CardContent className="space-y-3">
    <label className="block space-y-2 text-sm"><span>Suggested new words per day</span><Input className="min-h-11 max-w-40" type="number" min={0} max={30} step={1} value={value} onChange={(event) => setValue(event.target.value)} /></label>
    {query.data && <p className="text-xs text-muted-foreground">{query.data.used} new word cards saved today · {query.data.remaining} within your suggestion · resets at 00:00 UTC. Archiving a card does not erase today's intake.</p>}
    {(query.isError || save.isError) && <p role="alert" className="text-sm text-destructive">Could not load or save the intake suggestion. Try again.</p>}
    {save.isSuccess && <p role="status" className="text-xs text-primary">Intake suggestion saved.</p>}
    <Button className="min-h-11" disabled={query.isPending || save.isPending || value === "" || !Number.isInteger(Number(value)) || Number(value)<0 || Number(value)>30} onClick={() => save.mutate()}>Save intake suggestion</Button>
  </CardContent></Card>;
}
