import { useRef, useState } from "react";
import { post } from "../api/client";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

export default function ArtifactFeedback({ artifactId, sentenceId, rejected = false, label = "core explanation", onReject, onRetry }: { artifactId: number; sentenceId: number; rejected?: boolean; label?: string; onReject?: () => void; onRetry: () => void }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef<string | null>(null);
  const act = async () => {
    setBusy(true); setError(null);
    try {
      if (rejected) {
        requestId.current ??= crypto.randomUUID();
        await post(`/ai-artifacts/${artifactId}/retry`, { request_uuid: requestId.current, sentence_id: sentenceId });
        requestId.current = null; onRetry();
      } else {
        await post(`/ai-artifacts/${artifactId}/feedback`, { accepted: false, reason });
        onReject?.();
      }
    } catch (value) { setError(value instanceof Error ? value.message : "Could not save feedback"); }
    finally { setBusy(false); }
  };
  if (!artifactId) return null;
  return <section aria-label={rejected ? `Rejected AI ${label}` : `Review AI ${label}`} className="space-y-2 rounded-lg border border-border p-3">
    <p className="text-xs text-muted-foreground">{rejected ? "Rejection is saved. This result will stay hidden for this context. Another attempt can still contain errors." : "Spot an incorrect explanation? Reject it to keep it out of this sentence’s cache."}</p>
    {!rejected && <Input aria-label="Reason for rejecting this explanation" placeholder="What seems wrong? (optional)" maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} />}
    <Button variant="outline" size="sm" className="min-h-11" disabled={busy} onClick={() => void act()}>{busy ? "Saving…" : rejected ? "Request another attempt" : `Reject ${label}`}</Button>
    {error && <p role="alert" className="text-xs text-amber-200">{error}</p>}
  </section>;
}
