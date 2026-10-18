// Durable per-event outbox. Only acknowledged UUIDs are removed. Duplicate
// delivery across reloads/tabs/beacons is safe at the server's unique index.
interface LearnerEvent {
  client_uuid: string;
  type: string;
  session_id: string;
  item_id?: number;
  sentence_id?: number;
  lexeme_id?: number;
  position_ms?: number;
  subtitle_mode?: string;
  study_mode?: string;
  data?: Record<string, unknown>;
}

export function uuid(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const PREFIX = "immersion-event:";
const sessionId = uuid();
let queue: LearnerEvent[] = [];
let timer: number | undefined;
let inFlight = false;
let retryMs = 1000;
try {
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(PREFIX)) continue;
    try {
      const event = JSON.parse(localStorage.getItem(key) ?? "null") as LearnerEvent | null;
      if (event?.client_uuid && event.type) queue.push(event);
    } catch { /* An unreadable entry must not break playback. */ }
  }
} catch { /* Private browsing/storage restrictions: retain the in-memory queue. */ }

function schedule(delay: number) {
  timer ??= window.setTimeout(() => { timer = undefined; void flush(); }, delay);
}

export function track(type: string, fields: Omit<LearnerEvent, "client_uuid" | "type" | "session_id"> = {}) {
  const event = { client_uuid: uuid(), type, session_id: sessionId, ...fields };
  queue.push(event);
  try { localStorage.setItem(PREFIX + event.client_uuid, JSON.stringify(event)); } catch { /* memory fallback */ }
  schedule(10_000);
  if (queue.length >= 50) void flush();
}

export async function flush() {
  if (timer !== undefined) { clearTimeout(timer); timer = undefined; }
  if (inFlight || !queue.length) return;
  const batch = queue.slice(0, 50);
  const body = JSON.stringify(batch);
  if (document.visibilityState === "hidden" && navigator.sendBeacon) {
    // A true return means queued by the browser, not acknowledged by the API.
    // Retain persisted events for a normal, idempotent submission on return.
    const accepted = navigator.sendBeacon("/api/events/batch", new Blob([body], { type: "application/json" }));
    if (accepted) return;
  }
  inFlight = true;
  try {
    const response = await fetch("/api/events/batch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true,
    });
    if (!response.ok) throw new Error("Event submission failed");
    const ids = new Set(batch.map((event) => event.client_uuid));
    queue = queue.filter((event) => !ids.has(event.client_uuid));
    for (const id of ids) {
      try { localStorage.removeItem(PREFIX + id); } catch { /* duplicate delivery remains safe */ }
    }
    retryMs = 1000;
  } catch {
    retryMs = Math.min(retryMs * 2, 30_000);
  } finally {
    inFlight = false;
    if (queue.length) schedule(retryMs);
  }
}

document.addEventListener("visibilitychange", () => void flush());
window.addEventListener("online", () => void flush());
if (queue.length) schedule(1000);
