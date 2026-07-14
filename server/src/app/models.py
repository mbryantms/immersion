"""Domain model. Single-household deployment: no users table — adding one later
is a single boring migration. Original media and subtitle text are immutable;
derived analysis lives in sentence.analysis (render payload) plus
token_occurrence rows (coverage/concordance queries)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MediaRoot(Base):
    __tablename__ = "media_root"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)  # ASCII, used in URLs
    kind: Mapped[str] = mapped_column(String)  # 'video' | 'podcast'
    path: Mapped[str] = mapped_column(String)  # absolute path on the host
    include_glob: Mapped[str | None] = mapped_column(String)  # e.g. "Level */**"
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Series(Base):
    __tablename__ = "series"
    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey("media_root.id"))
    title: Mapped[str] = mapped_column(String)
    level_hint: Mapped[int | None] = mapped_column(Integer)  # LFC "Level N"
    cover_item_id: Mapped[int | None] = mapped_column(Integer)  # item whose thumb is the cover
    tags: Mapped[list | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("root_id", "title"),)


class MediaItem(Base):
    __tablename__ = "media_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    root_id: Mapped[int] = mapped_column(ForeignKey("media_root.id"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id"))
    relpath: Mapped[str] = mapped_column(String)  # root-relative; absolute paths never leave the server
    title: Mapped[str] = mapped_column(String)
    ordinal: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)  # 'video' | 'audio'
    fingerprint: Mapped[str | None] = mapped_column(String)  # xxhash of head+tail; size:mtime fast path in meta
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    vcodec: Mapped[str | None] = mapped_column(String)
    acodec: Mapped[str | None] = mapped_column(String)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)  # zh track ingested
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[dict | None] = mapped_column(JSON)
    tracks: Mapped[list[TextTrack]] = relationship(back_populates="item")
    __table_args__ = (UniqueConstraint("root_id", "relpath"),)


class TextTrack(Base):
    __tablename__ = "text_track"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("media_item.id"))
    lang: Mapped[str] = mapped_column(String)  # 'zh' | 'en'
    source: Mapped[str] = mapped_column(String)  # sidecar|embedded|whisper|transcript|manual
    relpath: Mapped[str | None] = mapped_column(String)  # root-relative subtitle file
    format: Mapped[str | None] = mapped_column(String)  # srt|vtt|ass
    encoding: Mapped[str | None] = mapped_column(String)
    content_hash: Mapped[str | None] = mapped_column(String)
    offset_ms: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    item: Mapped[MediaItem] = relationship(back_populates="tracks")


class Sentence(Base):
    __tablename__ = "sentence"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("media_item.id"))
    track_id: Mapped[int] = mapped_column(ForeignKey("text_track.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    zh: Mapped[str] = mapped_column(Text)  # original text, never mutated
    trad: Mapped[str | None] = mapped_column(Text)  # OpenCC/CEDICT conversion
    t0_ms: Mapped[int] = mapped_column(Integer)
    t1_ms: Mapped[int] = mapped_column(Integer)
    en: Mapped[str | None] = mapped_column(Text)
    en_source: Mapped[str | None] = mapped_column(String)  # 'track' | 'ai'
    align_conf: Mapped[float | None] = mapped_column(Float)  # zh↔en overlap ratio
    analysis: Mapped[dict | None] = mapped_column(JSON)  # {words:[{t,type,py,tones,gloss,lex,tr}]}
    __table_args__ = (Index("ix_sentence_item_ord", "item_id", "ordinal"),)


class TokenOccurrence(Base):
    __tablename__ = "token_occurrence"
    sentence_id: Mapped[int] = mapped_column(ForeignKey("sentence.id"), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)  # word index within sentence
    item_id: Mapped[int] = mapped_column(ForeignKey("media_item.id"))  # denormalized for coverage
    surface: Mapped[str] = mapped_column(String)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexeme.id"))
    __table_args__ = (
        Index("ix_tokocc_lexeme", "lexeme_id"),
        Index("ix_tokocc_item", "item_id"),
    )


class Lexeme(Base):
    __tablename__ = "lexeme"
    id: Mapped[int] = mapped_column(primary_key=True)
    simplified: Mapped[str] = mapped_column(String, unique=True)
    traditional: Mapped[str | None] = mapped_column(String)
    pinyin: Mapped[str | None] = mapped_column(String)  # numbered, first CEDICT reading
    hsk_level: Mapped[int | None] = mapped_column(Integer)  # 1-7 (7 = HSK 7-9)
    is_dict: Mapped[bool] = mapped_column(Boolean, default=False)  # False: OOV/name token
    pos: Mapped[str | None] = mapped_column(String)  # dominant ICTCLAS tag (jieba lexicon)
    freq_rank: Mapped[int | None] = mapped_column(Integer)  # 1 = most frequent (jieba counts)


class Sense(Base):
    __tablename__ = "sense"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexeme.id"))
    ord: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String, default="cedict")  # cedict|user|ai
    traditional: Mapped[str | None] = mapped_column(String)
    pinyin: Mapped[str | None] = mapped_column(String)  # numbered
    glosses: Mapped[list] = mapped_column(JSON)
    __table_args__ = (Index("ix_sense_lexeme", "lexeme_id"),)


class ExampleSentence(Base):
    """Curated zh-en example pairs (Tatoeba). zh_simp is the OpenCC-normalized
    match key — the corpus mixes simplified and traditional."""

    __tablename__ = "example_sentence"
    id: Mapped[int] = mapped_column(primary_key=True)
    zh: Mapped[str] = mapped_column(Text)
    zh_simp: Mapped[str] = mapped_column(Text)
    en: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="tatoeba")


class KnowledgeState(Base):
    __tablename__ = "knowledge_state"
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexeme.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String)  # new|learning|known|ignored
    source: Mapped[str] = mapped_column(String)  # manual|anki|derived — manual > anki > derived
    anki_interval_days: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LexemeStats(Base):
    """Working-set counters; the event table is the audit trail."""

    __tablename__ = "lexeme_stats"
    lexeme_id: Mapped[int] = mapped_column(ForeignKey("lexeme.id"), primary_key=True)
    encounters: Mapped[int] = mapped_column(Integer, default=0)
    lookups: Mapped[int] = mapped_column(Integer, default=0)
    distinct_items: Mapped[int] = mapped_column(Integer, default=0)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavedItem(Base):
    __tablename__ = "saved_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # 'word' | 'sentence'
    lexeme_id: Mapped[int | None] = mapped_column(ForeignKey("lexeme.id"))
    surface: Mapped[str | None] = mapped_column(String)  # as saved (custom spans differ from lexeme)
    note: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    contexts: Mapped[list[SavedContext]] = relationship(back_populates="saved_item")
    __table_args__ = (Index("ix_saved_lexeme", "lexeme_id"),)


class SavedContext(Base):
    """Where an item was saved. `snapshot` denormalizes the sentence (zh, en,
    item, timing) so the context survives re-ingestion; the FK is re-linked by
    matching zh text afterwards when possible."""

    __tablename__ = "saved_context"
    id: Mapped[int] = mapped_column(primary_key=True)
    saved_item_id: Mapped[int] = mapped_column(ForeignKey("saved_item.id"))
    sentence_id: Mapped[int | None] = mapped_column(ForeignKey("sentence.id"))
    snapshot: Mapped[dict | None] = mapped_column(JSON)  # {item_id, zh, en, t0_ms, t1_ms}
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    saved_item: Mapped[SavedItem] = relationship(back_populates="contexts")
    __table_args__ = (UniqueConstraint("saved_item_id", "sentence_id"),)


class ReviewState(Base):
    """Contextual review ladder per saved item: fixed 1d -> 3d -> 7d spacing,
    fail drops a rung. Clearing the top (or two straight passes there) offers
    graduation to the Anki export tray — the queue is a funnel, not an SRS."""

    __tablename__ = "review_state"
    saved_item_id: Mapped[int] = mapped_column(ForeignKey("saved_item.id"), primary_key=True)
    rung: Mapped[int] = mapped_column(Integer, default=0)  # index into [1d, 3d, 7d]
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    passes: Mapped[int] = mapped_column(Integer, default=0)
    fails: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)  # consecutive passes
    graduated: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_review_due", "due_at"),)


class Event(Base):
    """Append-only learner event stream. Coarse, semantic events only."""

    __tablename__ = "event"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    session_id: Mapped[str | None] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    item_id: Mapped[int | None] = mapped_column(Integer)
    sentence_id: Mapped[int | None] = mapped_column(Integer)
    lexeme_id: Mapped[int | None] = mapped_column(Integer)
    position_ms: Mapped[int | None] = mapped_column(Integer)
    subtitle_mode: Mapped[str | None] = mapped_column(String)
    study_mode: Mapped[str | None] = mapped_column(String)
    data: Mapped[dict | None] = mapped_column(JSON)
    client_uuid: Mapped[str | None] = mapped_column(String, unique=True)  # idempotent batch replay
    __table_args__ = (Index("ix_event_ts", "ts"), Index("ix_event_lexeme", "lexeme_id"))


class PlaybackProgress(Base):
    __tablename__ = "playback_progress"
    item_id: Mapped[int] = mapped_column(ForeignKey("media_item.id"), primary_key=True)
    position_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    subtitle_mode: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnkiLink(Base):
    __tablename__ = "anki_link"
    id: Mapped[int] = mapped_column(primary_key=True)
    lexeme_id: Mapped[int | None] = mapped_column(ForeignKey("lexeme.id"))
    saved_item_id: Mapped[int | None] = mapped_column(ForeignKey("saved_item.id"))
    note_id: Mapped[int] = mapped_column(Integer)
    deck: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    fields_hash: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="exported")
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiArtifact(Base):
    __tablename__ = "ai_artifact"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_kind: Mapped[str] = mapped_column(String)  # 'sentence' | 'item' | ...
    target_id: Mapped[int] = mapped_column(Integer)
    artifact_type: Mapped[str] = mapped_column(String)  # 'translation' | 'explanation' | ...
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String, default="1")
    input_hash: Mapped[str] = mapped_column(String)
    output: Mapped[dict] = mapped_column(JSON)
    accepted: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("target_kind", "target_id", "artifact_type", "input_hash", "prompt_version"),
    )


class Job(Base):
    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="queued")  # queued|running|done|failed
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[str | None] = mapped_column(String)  # human-readable stage note
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_job_status", "status"),)


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
