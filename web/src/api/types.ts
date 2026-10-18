// Hand-maintained mirrors of the FastAPI payloads (single repo, single client).

export interface Word {
  t: string;
  canonical?: string;
  start?: number; // Unicode codepoints, half-open source offsets
  end?: number;
  reading?: string;
  meaning?: string;
  reading_source?: string;
  type: "zh" | "x";
  py?: string[];
  tones?: number[];
  gloss?: { py: string; defs: string[] }[];
  lex?: number;
  tr?: string;
  ne?: "person" | "place" | "org"; // NER proper-name tag
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
  provenance?: { text_source: string; translation_source: string | null; timing_source: string; temporal_coverage: number | null; alignment_quality?: { matched_fraction: number; interpolated: boolean } | null; revision: number };
  anki?: boolean; // already exists as an Anki card
  words: Word[];
  script_variants?: Record<string, string>;
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
  tracks: { id: number; lang: string; source: string; format: string; offset_ms: number; selected: boolean; available?: boolean; label?: string }[];
  active_tracks?: { zh: number | null; en: number | null };
  source_status?: string | null;
  n_sentences: number;
  progress: { position_ms: number; completed: boolean; subtitle_mode: string | null };
  prev_item_id: number | null;
  next_item_id: number | null;
  rewatch_nudge: boolean;
  coverage?: number;
  tokens?: number;
  unknown_lexemes?: number;
}

// Familiarity is an exposure estimate. Lookups do not imply failure.
export type KnowledgeStateName = "new" | "learning" | "familiar" | "known" | "ignored";

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
  evidence?: {
    exposure: { independent_encounters: number; items: number; days: number; policy: string };
    recent_retrieval: { task: string; method: string; assistance: string; score: number; ts: string; scope: { reading?: string | null; meaning?: string | null; delayed?: boolean } }[];
    unassessed: string[];
    limitation: string;
  };
  stats?: { encounters: number; lookups: number; distinct_items: number; first_seen: string | null; last_seen: string | null };
}

export interface LookupResult {
  span: string;
  candidates: LexemeInfo[];
}

export interface SavedItemOut {
  archived?: boolean;
  id: number;
  kind: "word" | "sentence";
  lexeme_id: number | null;
  surface: string | null;
  selected_reading?: string | null;
  selected_meaning?: string | null;
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
  sentence_id: number | null;
  item_id: number | null;
  item_kind: string | null;
  item_available: boolean;
  stream_url: string | null;
  zh: string;
  en: string | null;
  t0_ms: number;
  t1_ms: number;
  words: Word[];
  script_variants?: Record<string, string>;
  source_revision?: number;
}

export interface ReviewItem {
  saved_item_id: number;
  kind: "word" | "sentence";
  surface: string | null;
  lexeme_id: number | null;
  mode: "context" | "listen";
  rung: number;
  streak: number;
  context: ReviewContext | null;
  answer?: { pinyin: string | null; senses: { py: string | null; defs: string[] }[] };
}

export interface ReviewOutcome {
  result?: "pass" | "fail";
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
  excluded_question_results?: number;
  practice_evidence?: { task: string; method: string; assistance: string; attempts: number; mean_score: number }[];
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

export interface LearnerProfile {
  goal: "read" | "listen" | "dictate";
  level: "unknown" | "beginner" | "intermediate" | "advanced";
  script: "source" | "simplified" | "traditional";
  interests: string[];
}

export interface Recommendation {
  item_id: number;
  title: string;
  kind: string;
  series_id: number | null;
  series_title: string | null;
  ordinal: number | null;
  duration_ms: number | null;
  thumb_url: string;
  coverage: number;
  unknown_lexemes: number;
  unknowns_per_minute?: number;
  dense_unknowns_30s?: number;
  subtitle_characters_per_minute?: number;
  subtitle_source?: string;
  source_warning?: boolean;
  goal?: string;
  reasons?: string[];
  uncertainty?: string;
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

export interface GuidedQuestion {
  id: number;
  revision: number;
  category: string;
  prompt: string;
  passage: string;
  choices: string[];
  provenance: string;
  externally_validated: boolean;
}
export interface MeaningFeedback {
  correct: boolean;
  answer: number;
  choice: number;
  explanations: string[];
  provenance?: string;
}
export interface GuidedScene {
  id: number;
  item_id: number;
  goal: "read" | "listen";
  stage: "watch" | "clarify" | "reduce" | "check" | "complete";
  revision: number;
  snapshot: { title: string; fingerprint: string | null; kind: string; t0: number; t1: number; lines: { id: number; zh: string; en: string | null; translation_source: string | null; t0: number; t1: number; revision: number; words: Word[] }[] };
  support: Record<string, unknown> & { checked?: boolean; reflection?: boolean; answer_feedback?: MeaningFeedback };
  revisits: number;
  due_at: string | null;
  completed_at: string | null;
  source_current: boolean;
  stream_url: string | null;
  question: GuidedQuestion | null;
}
export interface SceneSummary {
  id: number; item_id: number; title: string; goal: string; stage: string;
  revision: number; due_at: string | null; due: boolean; duration_ms: number;
}
export interface MiningBudget {
  daily_word_budget: number; used: number; remaining: number; timezone: string; soft_limit: boolean;
}
export interface Construction {
  id: string; title: string; note: string; suspended: boolean;
  examples: { zh: string; en: string }[];
  question: { category: string; prompt: string; passage: string; choices: string[] };
}
