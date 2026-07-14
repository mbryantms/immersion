// Buffered learner-event queue: batches to POST /api/events/batch, flushed on
// an interval and via sendBeacon on unload. client_uuid makes replays safe.

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

// crypto.randomUUID exists only in secure contexts (https/localhost); over
// plain http on the tailnet we build a v4 UUID from getRandomValues instead.
function uuid(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const sessionId = uuid().slice(0, 8);
let queue: LearnerEvent[] = [];
let timer: number | undefined;

export function track(
  type: string,
  fields: Omit<LearnerEvent, "client_uuid" | "type" | "session_id"> = {},
) {
  queue.push({ client_uuid: uuid(), type, session_id: sessionId, ...fields });
  timer ??= window.setTimeout(flush, 10_000);
  if (queue.length >= 50) flush();
}

export function flush() {
  if (timer) {
    clearTimeout(timer);
    timer = undefined;
  }
  if (!queue.length) return;
  const batch = queue;
  queue = [];
  const body = JSON.stringify(batch);
  if (document.visibilityState === "hidden" && navigator.sendBeacon) {
    navigator.sendBeacon("/api/events/batch", new Blob([body], { type: "application/json" }));
  } else {
    fetch("/api/events/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {
      queue = batch.concat(queue); // retry on next flush
    });
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flush();
});
