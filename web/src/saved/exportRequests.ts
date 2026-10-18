import type { ExportEntry } from "../api/queries";
const PREFIX = "anki-export-request-v1:";
export interface ExportRequest { request_uuid: string; profile_hash: string; entries: ExportEntry[]; created_at: string }
export function rememberExport(request: ExportRequest) { localStorage.setItem(PREFIX+request.request_uuid, JSON.stringify(request)); }
export function forgetExport(id: string) { localStorage.removeItem(PREFIX+id); }
export function pendingExports(): ExportRequest[] {
  const out: ExportRequest[] = [];
  for (let index = 0; index < localStorage.length; index++) {
    const key = localStorage.key(index);
    if (!key?.startsWith(PREFIX)) continue;
    try {
      const value = JSON.parse(localStorage.getItem(key) ?? "null") as ExportRequest;
      const hash = /^[a-f0-9]{64}$/;
      if (value && typeof value.request_uuid === "string" && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.request_uuid)
        && key === PREFIX+value.request_uuid && typeof value.created_at === "string" && Number.isFinite(Date.parse(value.created_at))
        && typeof value.profile_hash === "string" && hash.test(value.profile_hash) && Array.isArray(value.entries) && value.entries.length > 0 && value.entries.length <= 50
        && value.entries.every((entry) => entry && Number.isInteger(entry.saved_item_id) && entry.saved_item_id > 0 && typeof entry.source_hash === "string" && hash.test(entry.source_hash) && typeof entry.meaning === "string" && entry.meaning.length <= 2000)) out.push(value);
    } catch { /* A damaged reminder cannot change accepted server exports. */ }
  }
  return out.sort((a, b) => a.created_at.localeCompare(b.created_at));
}
