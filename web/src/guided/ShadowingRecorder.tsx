import { useEffect, useRef, useState } from "react";
import type { GuidedScene } from "../api/types";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { track } from "../lib/events";
import { deleteVoiceTake, loadVoiceTake, saveVoiceTake, voiceKey, type VoiceTake } from "./recordings";

type Status = "idle" | "requesting" | "recording" | "saving";
const MAX_MS = 60_000;
const MAX_BYTES = 8 * 1024 * 1024;

export default function ShadowingRecorder({ scene, pauseSource, replaySource }: { scene: GuidedScene; pauseSource: () => void; replaySource: () => void }) {
  const key = voiceKey(scene);
  const [status, setStatus] = useState<Status>("idle");
  const [take, setTake] = useState<VoiceTake | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [stored, setStored] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const generation = useRef(0);
  const alive = useRef(false);
  const discard = useRef(false);
  const started = useRef(0);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useRef(false);
  const capability = typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
  const release = () => { stream.current?.getTracks().forEach((track) => track.stop()); stream.current = null; if (timeout.current) clearTimeout(timeout.current); timeout.current = null; };
  const stop = () => {
    if (recorder.current?.state !== "recording") return;
    if (alive.current) setStatus("saving");
    try { recorder.current.stop(); }
    catch {
      discard.current = true; release(); recorder.current = null; active.current = false;
      if (alive.current) { setStatus("idle"); setError("Recording could not finish. Your previous take is retained; try again."); }
    }
  };
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    const loadGeneration = generation.current;
    setTake(null); setStored(false); setError(null);
    void loadVoiceTake(key).then((saved) => { if (!cancelled && !active.current && generation.current === loadGeneration) { setTake(saved ?? null); setStored(!!saved); } }).catch(() => { if (!cancelled) setError("Browser recording storage is unavailable. You can record and download a take before leaving."); });
    const hidden = () => { if (document.hidden) stop(); };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      document.removeEventListener("visibilitychange", hidden);
      cancelled = true; alive.current = false; generation.current++;
      // SPA navigation finalizes an active take. Browser shutdown may interrupt
      // finalization, so the UI asks the learner to stop before reloading.
      stop();
      release(); audio.current?.pause();
    };
  }, [key]);
  useEffect(() => {
    if (!take) { setUrl(null); return; }
    const next = URL.createObjectURL(take.blob); setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [take]);
  useEffect(() => {
    if (status !== "recording") return;
    const timer = setInterval(() => setElapsed(Math.min(MAX_MS, performance.now()-started.current)), 250);
    return () => clearInterval(timer);
  }, [status]);

  const record = async () => {
    if (active.current || !capability) return;
    active.current = true; discard.current = false; setError(null); setStatus("requesting");
    pauseSource(); audio.current?.pause();
    const attempt = ++generation.current;
    try {
      const input = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!alive.current || generation.current !== attempt) { input.getTracks().forEach((track) => track.stop()); return; }
      stream.current = input;
      const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) => MediaRecorder.isTypeSupported?.(type));
      const current = new MediaRecorder(input, mime ? { mimeType: mime, audioBitsPerSecond: 128000 } : undefined);
      recorder.current = current;
      const chunks: Blob[] = [];
      let bytes = 0;
      let failed = false;
      current.ondataavailable = (event) => {
        if (recorder.current !== current) return;
        bytes += event.data.size;
        if (bytes > MAX_BYTES) { failed = true; if (alive.current) setError("This take exceeded the local size limit. Your previous saved take is retained; try a shorter recording."); if (current.state === "recording") stop(); }
        else if (event.data.size) chunks.push(event.data);
      };
      current.onerror = () => { if (recorder.current !== current) return; failed = true; if (alive.current) setError("Recording failed. Your previous take is retained. Check the microphone and try again."); if (alive.current) setStatus("saving"); if (current.state === "recording") stop(); else release(); };
      current.onstop = async () => {
        if (recorder.current !== current) { input.getTracks().forEach((track) => track.stop()); return; }
        release(); recorder.current = null;
        const durationMs = Math.min(MAX_MS, Math.max(0, performance.now()-started.current));
        if (discard.current || failed || !bytes) {
          active.current = false;
          if (alive.current) { setStatus("idle"); if (!bytes && !discard.current && !failed) setError("No audio was captured. Your previous take is retained."); }
          return;
        }
        const completed: VoiceTake = { key, sceneId: scene.id, title: scene.snapshot.title,
          source: { itemId: scene.item_id, fingerprint: scene.snapshot.fingerprint, t0: scene.snapshot.t0, t1: scene.snapshot.t1, lines: scene.snapshot.lines.map(({ id, revision, zh }) => ({ id, revision, zh })) },
          blob: new Blob(chunks, { type: current.mimeType || chunks[0]?.type || "application/octet-stream" }), durationMs, createdAt: new Date().toISOString() };
        if (alive.current) { setTake(completed); setStored(false); setStatus("saving"); }
        try { await saveVoiceTake(completed); if (alive.current) setStored(true); }
        catch { if (alive.current) setError("The take is ready, but browser storage could not save it. Download it before leaving. Your previous stored take is retained."); }
        finally { active.current = false; if (alive.current) setStatus("idle"); }
        track("shadowing_recorded", { item_id: scene.item_id, data: { scene_id: scene.id, duration_ms: Math.round(durationMs), source_fingerprint: scene.snapshot.fingerprint, assessed: false } });
      };
      started.current = performance.now(); setElapsed(0); setStatus("recording");
      current.start(1000);
      timeout.current = setTimeout(() => { if (current.state === "recording") { if (alive.current) setStatus("saving"); stop(); } }, MAX_MS);
    } catch {
      if (generation.current !== attempt) return;
      release(); recorder.current = null; active.current = false;
      if (alive.current) { setStatus("idle"); setError("Microphone access did not start. Check browser permission and a secure localhost/HTTPS connection, then try again. Your previous take is retained."); }
    }
  };
  const cancel = () => {
    if (status === "requesting") { generation.current++; active.current = false; setStatus("idle"); return; }
    discard.current = true; stop();
  };
  const remove = async () => {
    setDeleting(true); audio.current?.pause();
    try { await deleteVoiceTake(key); setTake(null); setStored(false); setError(null); }
    catch { setError("Could not remove the stored take. Try again; its audio is retained."); }
    finally { setDeleting(false); }
  };
  const extension = take?.blob.type.includes("mp4") ? "m4a" : take?.blob.type.includes("webm") ? "webm" : "audio";
  return <Card><CardHeader><CardTitle className="text-base">Shadow and compare</CardTitle><CardDescription>Listen to the source, imitate a short phrase, then compare your own recording.</CardDescription></CardHeader><CardContent className="space-y-4">
    <p className="text-xs leading-relaxed text-muted-foreground">Audio stays in this browser; it is not uploaded or sent to an AI provider. One completed take is kept for this exact scene snapshot. Recording stops when this page is hidden. Stop to save before reloading; download a copy to keep outside browser storage.</p>
    {!capability && <p role="status" className="text-sm text-amber-200">Recording is unavailable here. Use a browser that supports microphone recording on localhost or HTTPS.</p>}
    {error && <p role="alert" className="text-sm leading-relaxed text-amber-200">{error}</p>}
    <div className="flex flex-wrap gap-2"><Button className="min-h-11" variant="outline" disabled={!scene.stream_url || status !== "idle"} onClick={() => { audio.current?.pause(); replaySource(); }}>Listen to source</Button>
      {status === "idle" ? <Button className="min-h-11" disabled={!capability || deleting} onClick={() => void record()}>{take ? "Record another take" : "Record my voice"}</Button> : <><p role="status" className="flex min-h-11 items-center text-sm">{status === "requesting" ? "Waiting for microphone permission…" : status === "saving" ? "Saving your take…" : `Recording ${Math.floor(elapsed/1000)} / 60 seconds`}</p>{status === "recording" && <Button className="min-h-11" onClick={stop}>Stop and save take</Button>}{status !== "saving" && <Button className="min-h-11" variant="outline" onClick={cancel}>Cancel recording</Button>}</>}
    </div>
    {take && url && <section aria-label="Your voice recording" className="space-y-3 rounded-xl border border-border p-4"><p className="text-sm font-medium">Your take · {Math.max(1, Math.round(take.durationMs/1000))} seconds</p><audio ref={audio} controls src={url} preload="metadata" className="h-12 w-full" aria-label="Play your recorded take" onPlay={pauseSource} /><p role="status" className="text-xs text-muted-foreground">{stored ? "Saved in this browser for this source snapshot." : "Available in this tab; download before leaving."}</p><div className="flex flex-wrap gap-2"><Button asChild variant="outline" className="min-h-11"><a href={url} download={`immersion-scene-${scene.id}-take.${extension}`}>Download take</a></Button><Button variant="ghost" className="min-h-11" disabled={status !== "idle" || deleting} onClick={() => void remove()}>Remove take</Button></div></section>}
    <p className="text-xs leading-relaxed text-muted-foreground">Compare rhythm, syllable clarity and where tones change in context. This is self-comparison: recording does not assess pronunciation or tone accuracy. A new completed take replaces the previous one; a denied or cancelled attempt keeps it.</p>
  </CardContent></Card>;
}
