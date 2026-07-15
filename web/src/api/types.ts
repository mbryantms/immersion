// Hand-maintained mirrors of the FastAPI payloads (single repo, single client).

export interface Word {
  t: string;
  type: "zh" | "x";
  py?: string[];
  tones?: number[];
  gloss?: { py: string; defs: string[] }[];
  lex?: number;
  tr?: string;
}

export interface SentenceOut {
  id: number;
  ord: number;
  zh: string;
  tr: string | null;
  t0: number;
  t1: number;
  en: string | null;
  conf: number | null;
  anki?: boolean; // already exists as an Anki card
  words: Word[];
}

// The explanation arrives in two parallel halves: core (renders first) and
// extras (fills in below). Both cached server-side per zh text.
export interface ExplainCore {
  natural: string;
  literal: string;
  structure: string;
  words: { zh: string; role: string; py?: string; hsk?: number; pos?: string; defs?: string[] }[];
  particles: { zh: string; note: string }[];
  pinyin: string; // app-derived, not AI
  hsk: { level: number | null; offlist: string[] }; // app-derived
  provider: string;
  model: string | null;
  created_at: string;
}

export interface ExplainExtras {
  pronunciation: string[];
  nuance: string;
  variations: { zh: string; py?: string; note: string }[];
  pattern: { name: string; examples: { zh: string; py?: string; en: string }[] } | null;
  mistakes: string[];
  provider: string;
  model: string | null;
  created_at: string;
}

export interface SeriesSummary {
  id: number;
  root_id: number;
  kind: string; // 'video' | 'podcast' (from the root)
  title: string;
  level: number | null;
  episodes: number;
  ready: number;
  coverage?: number | null;
  cover_url: string | null;
}

export interface ContinueItem {
  item_id: number;
  title: string;
  series_id: number | null;
  position_ms: number;
  duration_ms: number | null;
  thumb_url: string;
}

export interface Library {
  roots: {
    id: number;
    slug: string;
    kind: string;
    path: string;
    include_glob: string | null;
    enabled: boolean;
    last_scan_at: string | null;
  }[];
  series: SeriesSummary[];
  continue: ContinueItem[];
}

export interface EpisodeSummary {
  id: number;
  title: string;
  ordinal: number | null;
  duration_ms: number | null;
  ready: boolean;
  available: boolean;
  has_zh: boolean;
  thumb_url: string;
  position_ms: number;
  completed: boolean;
  coverage?: number;
  tokens?: number;
  unknown_lexemes?: number;
}

export interface SeriesDetail {
  id: number;
  title: string;
  level: number | null;
  items: EpisodeSummary[];
}

export interface ItemDetail {
  id: number;
  title: string;
  kind: string;
  ordinal: number | null;
  duration_ms: number | null;
  ready: boolean;
  available: boolean;
  width: number | null;
  height: number | null;
  series: { id: number; title: string; level: number | null } | null;
  stream_url: string;
  thumb_url: string;
  tracks: { id: number; lang: string; source: string; format: string; offset_ms: number; selected: boolean }[];
  n_sentences: number;
  progress: { position_ms: number; completed: boolean; subtitle_mode: string | null };
  prev_item_id: number | null;
  next_item_id: number | null;
  rewatch_nudge: boolean;
  coverage?: number;
  tokens?: number;
  unknown_lexemes?: number;
}

export type KnowledgeStateName = "new" | "learning" | "known" | "ignored";

export interface KnowledgeMap {
  states: Record<string, KnowledgeStateName>;
  saved: number[];
}

export interface LexemeInfo {
  lexeme_id: number;
  simplified: string;
  traditional: string | null;
  pinyin: string | null;
  hsk: number | null;
  is_dict: boolean;
  pos?: string | null;
  freq_rank?: number | null;
  senses: { py: string | null; trad: string | null; defs: string[] }[];
  state: KnowledgeStateName;
  state_source: string | null;
  saved_item_id: number | null;
  stats?: { encounters: number; lookups: number; first_seen: string | null; last_seen: string | null };
}

export interface LookupResult {
  span: string;
  candidates: LexemeInfo[];
}

export interface SavedItemOut {
  id: number;
  kind: "word" | "sentence";
  lexeme_id: number | null;
  surface: string | null;
  note: string | null;
  tags: string[] | null;
  created_at: string;
  anki_note_id: number | null;
  review: {
    rung: number;
    passes: number;
    fails: number;
    graduated: boolean;
  } | null;
  contexts: {
    sentence_id: number | null;
    sentence_ord?: number;
    played?: boolean;
    item_id?: number;
    item_title?: string | null;
    zh?: string;
    en?: string | null;
    t0_ms?: number;
    t1_ms?: number;
    added_at: string;
  }[];
}

export interface ExportPreviewItem {
  saved_item_id: number;
  kind: "word" | "sentence";
  fields: Record<string, string>;
  sentence_id: number | null;
  can_clip: boolean;
  can_image: boolean;
  duplicates: number;
  duplicate_meanings: string[];
  already_exported: number | null;
}

export interface ExportPreview {
  deck: string;
  model: string;
  items: ExportPreviewItem[];
}

export interface ReviewContext {
  sentence_id: number;
  item_id: number;
  item_kind: string | null;
  item_available: boolean;
  stream_url: string | null;
  zh: string;
  en: string | null;
  t0_ms: number;
  t1_ms: number;
  words: Word[];
}

export interface ReviewItem {
  saved_item_id: number;
  kind: "word" | "sentence";
  surface: string | null;
  lexeme_id: number | null;
  mode: "context" | "dictation";
  rung: number;
  streak: number;
  context: ReviewContext | null;
}

export interface ReviewOutcome {
  rung: number;
  graduated: boolean;
  already_in_anki: boolean;
  suggest_drop: boolean;
  next_due_days: number;
}

export interface WeekStat {
  week: string;
  video_minutes: number;
  audio_minutes: number;
  lookup_per_100: number | null;
  reveal_per_100: number | null;
}

export interface DashboardStats {
  weeks: WeekStat[];
  totals: { lookups: number; sentences_played: number; saves: number };
  recurring_unknowns: {
    lexeme_id: number;
    simplified: string;
    pinyin: string | null;
    occurrences: number;
    items: number;
  }[];
  review_due: number;
  graduated_waiting: number;
  anki: { last_import: unknown; last_export: unknown };
}

export interface SearchResult {
  sentence_id: number;
  item_id: number;
  item_title: string | null;
  item_kind: string | null;
  zh: string;
  trad: string | null;
  en: string | null;
  t0_ms: number;
  t1_ms: number;
}

export interface JobOut {
  id: number;
  type: string;
  payload: Record<string, unknown> | null;
  status: "queued" | "running" | "done" | "failed";
  attempts: number;
  progress: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
