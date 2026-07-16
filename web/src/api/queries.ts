import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, patch, post, put } from "./client";
import type {
  ExportPreview,
  ItemDetail,
  JobOut,
  KnowledgeMap,
  KnowledgeStateName,
  Library,
  LookupResult,
  SavedItemOut,
  SentenceOut,
  SeriesDetail,
} from "./types";

export const useLibrary = () =>
  useQuery({ queryKey: ["library"], queryFn: () => get<Library>("/library") });

export const useSeries = (id: number) =>
  useQuery({ queryKey: ["series", id], queryFn: () => get<SeriesDetail>(`/series/${id}`) });

export const useItem = (id: number) =>
  useQuery({ queryKey: ["item", id], queryFn: () => get<ItemDetail>(`/items/${id}`) });

export const useSentences = (itemId: number) =>
  useQuery({
    queryKey: ["sentences", itemId],
    queryFn: () => get<{ item_id: number; zh_offset_ms: number; sentences: SentenceOut[] }>(
      `/items/${itemId}/sentences`),
    staleTime: Infinity, // immutable per content revision (server also ETags it)
  });

export const useKnowledge = (itemId: number) =>
  useQuery({
    queryKey: ["knowledge", itemId],
    queryFn: () => get<KnowledgeMap>(`/knowledge?item_id=${itemId}`),
  });

export const useLookup = () =>
  useMutation({
    mutationFn: (body: { sentence_id: number; start: number; end: number }) =>
      post<LookupResult>("/lookup", body),
  });

export function useSetKnowledge(itemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lexemeId, state }: { lexemeId: number; state: KnowledgeStateName }) =>
      put(`/knowledge/${lexemeId}`, { state }),
    onMutate: async ({ lexemeId, state }) => {
      // optimistic: recolor tokens immediately
      await qc.cancelQueries({ queryKey: ["knowledge", itemId] });
      const prev = qc.getQueryData<KnowledgeMap>(["knowledge", itemId]);
      if (prev) {
        qc.setQueryData<KnowledgeMap>(["knowledge", itemId], {
          ...prev,
          states: { ...prev.states, [lexemeId]: state },
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(["knowledge", itemId], ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: ["knowledge", itemId] }),
  });
}

export function useSaveItem(itemId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      kind: "word" | "sentence";
      lexeme_id?: number;
      surface?: string;
      sentence_id?: number;
    }) => post<{ id: number; created: boolean }>("/saved-items", body),
    onMutate: async (body) => {
      // optimistic: the token's saved highlight should be instant, like the
      // knowledge recolor — not gated on an invalidation round-trip
      if (body.kind !== "word" || !body.lexeme_id) return {};
      await qc.cancelQueries({ queryKey: ["knowledge", itemId] });
      const prev = qc.getQueryData<KnowledgeMap>(["knowledge", itemId]);
      if (prev && !prev.saved.includes(body.lexeme_id)) {
        const state = prev.states[body.lexeme_id];
        qc.setQueryData<KnowledgeMap>(["knowledge", itemId], {
          ...prev,
          saved: [...prev.saved, body.lexeme_id],
          states: state && state !== "new"
            ? prev.states
            : { ...prev.states, [body.lexeme_id]: "learning" },
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(["knowledge", itemId], ctx.prev),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["knowledge", itemId] });
      qc.invalidateQueries({ queryKey: ["saved"] });
    },
  });
}

export const useSaved = (kind?: string) =>
  useQuery({
    queryKey: ["saved", kind ?? "all"],
    queryFn: () => get<{ items: SavedItemOut[] }>(`/saved-items${kind ? `?kind=${kind}` : ""}`),
  });

export function useUnsave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del(`/saved-items/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }),
  });
}

export function useResetSavedReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del<{ saved_item_id: number; reset: boolean }>(`/saved-items/${id}/review`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["saved"] });
      qc.invalidateQueries({ queryKey: ["review-queue"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useResetSentencePlayed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sentenceId: number) => del<{ sentence_id: number; played: boolean }>(`/sentences/${sentenceId}/played`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }),
  });
}

export function usePatchSaved() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; note?: string; archived?: boolean }) =>
      patch(`/saved-items/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }),
  });
}

export const useJobs = () =>
  useQuery({
    queryKey: ["jobs"],
    queryFn: () => get<{ jobs: JobOut[]; active: boolean }>("/jobs"),
    refetchInterval: (q) => (q.state.data?.active ? 2000 : 15000),
  });

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { type: string; payload?: Record<string, unknown> }) =>
      post<JobOut | { deduped: boolean }>("/jobs", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export const useReviewQueue = () =>
  useQuery({
    queryKey: ["review-queue"],
    queryFn: () => get<{ due: number; items: import("./types").ReviewItem[] }>("/review/queue"),
    staleTime: 0,
  });

export const postReviewOutcome = (savedItemId: number, body: { result: "pass" | "fail"; mode?: string }) =>
  post<import("./types").ReviewOutcome>(`/review/${savedItemId}/outcome`, body);

export const useRecommendations = () =>
  useQuery({
    queryKey: ["recommendations"],
    queryFn: () => get<{ band: { low: number; high: number }; fallback: boolean; items: import("./types").Recommendation[] }>("/recommendations"),
    staleTime: 5 * 60_000, // coverage moves slowly; don't recompute per visit
  });

export const useDashboard = () =>
  useQuery({
    queryKey: ["dashboard"],
    queryFn: () => get<import("./types").DashboardStats>("/stats/dashboard"),
  });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => get<{ query: string; results: import("./types").SearchResult[] }>(
      `/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length > 0,
  });

export const useLexeme = (id: number) =>
  useQuery({
    queryKey: ["lexeme", id],
    queryFn: () => get<import("./types").LexemeInfo>(`/lexemes/${id}`),
    enabled: Number.isFinite(id),
  });

export const useExamples = (id: number) =>
  useQuery({
    queryKey: ["examples", id],
    queryFn: () => get<{ results: { zh: string; en: string; source: string }[] }>(
      `/lexemes/${id}/examples`),
    enabled: Number.isFinite(id),
    staleTime: Infinity,
  });

export const useConcordance = (id: number) =>
  useQuery({
    queryKey: ["concordance", id],
    queryFn: () => get<{ results: import("./types").SearchResult[] }>(`/lexemes/${id}/concordance`),
    enabled: Number.isFinite(id),
  });

export const fetchExportPreview = (savedItemIds: number[]) =>
  post<ExportPreview>("/anki/export-preview", { saved_item_ids: savedItemIds });

export interface ExportEntry {
  saved_item_id: number;
  fields: Record<string, string>;
  allow_duplicate?: boolean;
  include_media?: boolean;
}

export const startExport = (entries: ExportEntry[]) =>
  post<{ queued: boolean; job_id: number | null }>("/anki/export", { entries });

/** Poll one job to completion; resolves with the finished job. */
export async function awaitJob(jobId: number, timeoutMs = 180_000): Promise<JobOut> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const { jobs } = await get<{ jobs: JobOut[] }>(`/jobs?limit=50`);
    const job = jobs.find((j) => j.id === jobId);
    if (job && (job.status === "done" || job.status === "failed")) return job;
    if (Date.now() > deadline) throw new Error("job timed out");
    await new Promise((r) => setTimeout(r, 1500));
  }
}

export const setKnowledge = (lexemeId: number, state: KnowledgeStateName) =>
  put(`/knowledge/${lexemeId}`, { state });

export const clearKnowledge = (lexemeId: number) =>
  del<{ lexeme_id: number; state: KnowledgeStateName; source: string | null; cleared: boolean }>(`/knowledge/${lexemeId}`);

export const resetLexemeStats = (lexemeId: number) =>
  del<{ lexeme_id: number; reset: boolean }>(`/lexemes/${lexemeId}/stats`);

export const explainSentence = (sentenceId: number) =>
  post<import("./types").ExplainCore>(`/sentences/${sentenceId}/explain`);

export const explainSentenceExtras = (sentenceId: number) =>
  post<import("./types").ExplainExtras>(`/sentences/${sentenceId}/explain-extras`);

/** Fire-and-forget warmup: start generating the explanation so a later
 *  Explain click lands on the cache (or joins the in-flight call). Core
 *  first, extras chained after — parallel calls share one provider token
 *  budget and finish later than back-to-back. */
export const prefetchExplain = (sentenceId: number) => {
  explainSentence(sentenceId)
    .catch(() => {})
    .finally(() => explainSentenceExtras(sentenceId).catch(() => {}));
};

export const patchTrackOffset = (trackId: number, offsetMs: number) =>
  patch<{ id: number; offset_ms: number }>(`/tracks/${trackId}`, { offset_ms: offsetMs });

export const queueTranscribe = (itemId: number) =>
  post<{ queued: boolean }>(`/items/${itemId}/transcribe`);

export const saveProgress = (
  itemId: number,
  body: { position_ms: number; duration_ms?: number; completed?: boolean; subtitle_mode?: string },
) => put(`/progress/${itemId}`, body).catch(() => {});
