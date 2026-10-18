import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { post } from "../api/client";
import type { ItemDetail } from "../api/types";
import { Button } from "@/components/ui/button";

export default function SourcePanel({ item }: { item: ItemDetail }) {
  const client = useQueryClient();
  const [zh, setZh] = useState("");
  const [en, setEn] = useState("");
  const [pending, setPending] = useState(false);
  const [status, setStatus] = useState("");
  useEffect(() => { setZh(String(item.active_tracks?.zh ?? "")); setEn(String(item.active_tracks?.en ?? "")); }, [item.active_tracks?.zh, item.active_tracks?.en]);
  const run = async (repair: boolean) => {
    if (pending) return;
    setPending(true); setStatus("");
    try {
      await post(`/items/${item.id}/${repair ? "repair-media" : "tracks"}`, repair ? undefined : { zh_track_id: Number(zh), en_track_id: en ? Number(en) : null });
      setStatus(repair ? "Playback repair queued. Check Admin for progress, then reload the player." : "Updating the transcript. Your source selections are saved.");
      await client.invalidateQueries({ queryKey: ["item", item.id] });
    } catch (error) { setStatus(error instanceof Error ? error.message : "Could not update this source."); }
    finally { setPending(false); }
  };
  return <details className="mb-3 rounded-xl border border-border bg-card px-4 py-2">
    <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium">Subtitle sources and playback repair</summary>
    <p className="mb-3 text-xs text-muted-foreground">Choose the Chinese track you hear. External subtitles, embedded captions, and automatic transcripts have different reliability.</p>
    {item.source_status && <p role="status" className="mb-3 text-sm text-amber-200">{item.source_status}</p>}
    <div className="grid gap-3 sm:grid-cols-2">{(["zh", "en"] as const).map((language) => <label key={language} className="space-y-1 text-sm">{language === "zh" ? "Chinese subtitle source" : "English subtitle source"}
      <select aria-label={language === "zh" ? "Chinese subtitle source" : "English subtitle source"} value={language === "zh" ? zh : en} onChange={(event) => language === "zh" ? setZh(event.target.value) : setEn(event.target.value)} className="block min-h-11 w-full min-w-0 rounded-md border border-border bg-background px-2">
        <option value="">{language === "zh" ? "Choose available Chinese track" : "No English track"}</option>
        {item.tracks.filter((track) => track.lang === language).map((track) => <option key={track.id} value={track.id} disabled={track.available === false}>{track.source} · {track.label ?? `Track ${track.id}`}{track.available === false ? " (unavailable)" : ""}</option>)}
      </select>
    </label>)}</div>
    <div className="my-3 flex flex-wrap gap-2"><Button className="min-h-11" disabled={pending || !zh} variant="secondary" onClick={() => run(false)}>Use selected tracks</Button><Button className="min-h-11" disabled={pending || !item.available} variant="outline" onClick={() => run(true)}>Repair playback</Button></div>
    {status && <p role="status" className="mb-3 text-sm text-muted-foreground">{status}</p>}
  </details>;
}
