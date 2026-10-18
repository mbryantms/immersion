/** Browser-only audio. A completed take is bound to the immutable source snapshot. */
import type { GuidedScene } from "../api/types";

export interface VoiceTake {
  key: string;
  sceneId: number;
  title: string;
  source: { itemId: number; fingerprint: string | null; t0: number; t1: number; lines: { id: number; revision: number; zh: string }[] };
  blob: Blob;
  durationMs: number;
  createdAt: string;
}
export function voiceKey(scene: GuidedScene): string {
  return JSON.stringify(["voice-v1", scene.id, scene.item_id, scene.snapshot.fingerprint, scene.snapshot.t0, scene.snapshot.t1, scene.snapshot.lines.map((line) => [line.id, line.revision, line.zh])]);
}
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let blocked = false;
    const request = indexedDB.open("immersion-voice", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("takes", { keyPath: "key" });
    request.onsuccess = () => {
      if (blocked) { request.result.close(); return; }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error ?? new Error("Recording storage unavailable"));
    request.onblocked = () => { blocked = true; reject(new Error("Recording storage is blocked by another tab")); };
  });
}
async function operation<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database();
  return new Promise((resolve, reject) => {
    try {
      const tx = db.transaction("takes", mode);
      const request = work(tx.objectStore("takes"));
      tx.oncomplete = () => { db.close(); resolve(request.result); };
      tx.onerror = tx.onabort = () => { db.close(); reject(tx.error ?? request.error ?? new Error("Recording storage failed")); };
    } catch (error) { db.close(); reject(error); }
  });
}
export async function loadVoiceTake(key: string): Promise<VoiceTake | undefined> {
  const saved = await operation<VoiceTake | undefined>("readonly", (store) => store.get(key));
  if (!saved) return undefined;
  if (saved.key !== key || !(saved.blob instanceof Blob) || !saved.blob.size || saved.blob.size>8*1024*1024 || !Number.isFinite(saved.durationMs) || saved.durationMs<0 || saved.durationMs>60000) throw new Error("Stored recording is unreadable");
  return saved;
}
export const saveVoiceTake = (take: VoiceTake) => operation<IDBValidKey>("readwrite", (store) => store.put(take));
export const deleteVoiceTake = (key: string) => operation<undefined>("readwrite", (store) => store.delete(key));
