import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post, put } from "../api/client";
import { exportFields, fieldLabels, type AnkiPreflight, type AnkiProfile } from "../anki-types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Switch } from "./ui/switch";

const selectClass = "min-h-11 w-full rounded-lg border border-input bg-background px-3 text-sm";
export default function AnkiSettingsCard() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["anki-profile"], queryFn: () => get<{ profile: AnkiProfile }>("/anki/export-profile") });
  const [draft, setDraft] = useState<AnkiProfile | null>(null);
  const [report, setReport] = useState<AnkiPreflight | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (query.data?.profile) setDraft(query.data.profile); }, [query.data]);
  const check = useMutation({ mutationFn: (profile: AnkiProfile) => post<AnkiPreflight>("/anki/preflight", profile), onSuccess: (value) => setReport(value) });
  const save = useMutation({ mutationFn: (profile: AnkiProfile) => put<{ profile: AnkiProfile }>("/anki/export-profile", profile), onSuccess: (value) => { queryClient.setQueryData(["anki-profile"], value); setSaved(true); setReport((value) => value ? { ...value, ok: true, errors: [] } : null); void queryClient.invalidateQueries({ queryKey: ["anki-inbox"] }); } });
  const change = (patch: Partial<AnkiProfile>) => { if (draft) { setDraft({ ...draft, ...patch }); setSaved(false); } };
  const checking = check.isPending || save.isPending;
  return <Card><CardHeader><CardTitle className="text-base">Anki export setup</CardTitle><CardDescription>Use an existing deck and note type. Map your fields, then check the card fronts and backs in Anki so they practise the skill you intend. The app does not change templates or create a personal note type.</CardDescription></CardHeader><CardContent className="space-y-4">
    {!draft ? <p role="status" className="text-sm text-muted-foreground">Loading Anki export preferences…</p> : <>
      <Button className="min-h-11" variant="outline" disabled={checking} onClick={() => { setSaved(false); check.mutate(draft); }}>Check Anki and load choices</Button>
      <p className="text-xs text-muted-foreground">Open Anki Desktop with AnkiConnect. Checking reads its catalog and does not add notes. Saved preferences apply to new submissions; submitted exports retain their reviewed destination.</p>
      <div className="grid gap-3 sm:grid-cols-2"><label className="space-y-1 text-sm"><span>Destination deck</span><select aria-label="Destination deck" className={selectClass} value={draft.deck} disabled={checking} onChange={(event) => change({ deck: event.target.value })}>{[...new Set([draft.deck, ...(report?.decks ?? [])])].map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="space-y-1 text-sm"><span>Note type</span><select aria-label="Note type" className={selectClass} value={draft.model} disabled={checking} onChange={(event) => { const model = event.target.value; const next = { ...draft, model, templates_reviewed: false }; setDraft(next); setSaved(false); check.mutate(next, { onSuccess: (value) => {
          const fields = Object.fromEntries(Object.entries(next.fields).filter(([, target]) => value.model_fields.includes(target)));
          if (!fields.Simplified && value.model_fields.includes("Front")) fields.Simplified = "Front";
          if (!fields.Meaning && value.model_fields.includes("Back")) fields.Meaning = "Back";
          setDraft({ ...next, fields });
        } }); }}>{[...new Set([draft.model, ...(report?.models ?? [])])].map((value) => <option key={value}>{value}</option>)}</select></label></div>
      <details className="rounded-lg border border-border p-3"><summary className="min-h-11 cursor-pointer text-sm font-medium">Map export fields</summary><p className="mb-3 text-xs text-muted-foreground">Map Chinese text in either script, or a source sentence, plus Meaning. Map the first Anki field to an identifier, Chinese text or source sentence. A selected word reading requires a Pinyin mapping. Unmapped optional content is omitted.</p><div className="grid gap-3 sm:grid-cols-2">{exportFields.map((field) => <label key={field} className="space-y-1 text-xs"><span>{fieldLabels[field]}</span><select aria-label={`Anki field for ${fieldLabels[field]}`} className={selectClass} value={draft.fields[field] ?? ""} disabled={checking} onChange={(event) => { const fields = { ...draft.fields }; if (event.target.value) fields[field] = event.target.value; else delete fields[field]; change({ fields }); }}><option value="">Not mapped</option>{[...new Set([...(draft.fields[field] ? [draft.fields[field]] : []), ...(report?.model_fields ?? [])])].map((name) => <option key={name}>{name}</option>)}</select></label>)}</div></details>
      <label className="flex min-h-11 items-start gap-3 text-sm"><input type="checkbox" className="mt-1 size-4 shrink-0 accent-teal-400" checked={draft.templates_reviewed} disabled={checking} onChange={(event) => change({ templates_reviewed: event.target.checked })} /><span>I reviewed the note type’s fronts and backs in Anki and they match my intended practice.</span></label>
      <div className="flex items-center justify-between gap-4"><div><label htmlFor="anki-word-tts" className="text-sm font-medium">Optional online word audio</label><p className="mt-1 text-xs text-muted-foreground">Off by default. Synthetic TTS may contact a remote service. Selected or corrected readings keep source audio and never use this substitute.</p></div><Switch id="anki-word-tts" disabled={checking} checked={draft.word_tts} onCheckedChange={(word_tts) => change({ word_tts })} /></div>
      {report && <div className="space-y-1" aria-live="polite">{report.errors.map((message) => <p key={message} className="text-sm text-amber-200">{message}</p>)}{report.warnings.map((message) => <p key={message} className="text-xs text-muted-foreground">{message}</p>)}</div>}
      <Button className="min-h-11" disabled={checking || !draft.templates_reviewed} onClick={() => { setSaved(false); save.mutate(draft); }}>Save Anki export setup</Button>
      {saved && <p role="status" className="text-sm text-primary">Anki export setup saved.</p>}
    </>}
    {(query.isError || check.isError || save.isError) && <div role="alert" className="space-y-2 text-sm text-amber-200"><p>{String((save.error ?? check.error ?? query.error)?.message ?? "Could not load Anki preferences")}</p><p>Your current preferences are retained. Open Anki and check again.</p></div>}
  </CardContent></Card>;
}
