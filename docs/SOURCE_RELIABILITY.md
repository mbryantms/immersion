# Source reliability and reversible local corrections

This delivery advances L06, D01, D07–D13, and G06–G08. The roadmap distinguishes delivered functionality from remaining acceptance gates.

## Correct a learning source

Choose **Correct line** in the Watch transcript. Edit Chinese text, English meaning, source-clock start/end times, or a word’s numbered pinyin and contextual meaning. Chinese text changes use immediate dictionary segmentation and contextual pinyin without importing HanLP/Torch into the API or requesting remote AI. Save changed Chinese before editing its new word positions. Changing Chinese clears the prior English translation unless its meaning is also edited; this avoids presenting an unrelated old answer.

The editor shows the captured source and up to 50 recent history entries. **Reset to source** and **Restore revision** append history; neither deletes prior edits. Stale saves return a conflict and keep the draft until the learner explicitly reloads. Dictionary-selected readings also enter correction history. Corrected words keep their local meaning separate from the dictionary’s general definitions.

The application projects corrections into playback, lookup, FTS, review, and Anki field construction. Corrections revise transcript ETags and invalidate affected client queries. AI explanations now key on text, analysis, translation, and configured model, in addition to their existing prompt/type keys. A translation generated while a local edit is made is discarded; explicitly cleared user meanings are not refilled automatically. Existing chosen meanings on saved learning items remain the intended retrieval target; editing a source does not silently redefine a saved sense.

Corrections never write to original subtitle or media files. Source identity includes the item, track, source text, media fingerprint, timing, and ordinal. Reingestion reapplies an override only to a matched identity. A different track/source version cannot inherit a correction merely because one line has the same text. Ambiguous or removed contexts keep their snapshots/history rather than being guessed onto another source. Correction history for removed identities remains in the database; a dedicated orphan-history UI is still future work.

## Stable learning history

Migration `c3d5e7f9a1b2` adds permanent `sentence_identity` and append-only `sentence_correction` tables. Existing live sentence IDs and original source projections are captured. IDs present only in historical events are reserved. The permanent identity table uses SQLite AUTOINCREMENT, and identities are never deleted when a live source line disappears.

An unchanged, matched line retains its sentence ID across ingestion. Repeated lines use unambiguous timing anchors; untimed repetitions additionally require matching cardinality/position. Removed IDs cannot be assigned to unrelated text, so old events and browser attempts cannot attach to a newly inserted sentence. Saved-context relinking requires source fingerprint, track, text, timing, and ordinal instead of the last matching substring.

New checked dictation attempts retain expected text, script policy/pairs, and source revision. If the current line changes, its historical score still uses the original target and the UI explains that the learner should edit/reset to practice the new line. Saved context snapshots also carry revision and fingerprint. Older attempts/events cannot retroactively recover source versions they never recorded; full multidimensional evidence migration remains M4.

Normal startup/`immersion upgrade` runs the additive migration using the existing online SQLite backup and restore-verification gate. Temporary-database tests verify source preservation, retained IDs, historical-ID reservation, and the backup. No personal production database was migrated here. Stop services before restoring a verified pre-upgrade database with its matching application revision.

## Choose subtitle sources and repair playback

Expand **Subtitle sources and playback repair** on Watch. Chinese and optional English choices are saved explicitly and reingestion is queued. Sidecar/embedded/transcript sources are labelled; missing or unreadable sidecars are unavailable and deselected. Text embedded tracks are discovered even when a sidecar is present. Bitmap subtitles still require OCR and are not offered as parseable text. Failed or removed embedded streams are unavailable; cache filenames include media fingerprints and extraction uses a temporary file with a timeout.

Source selections survive scans. Missing selected sources retain history and prompt for an available source. A disconnected root fails scanning without erasing its indexed history. English sync offsets are applied when aligning tracks, and changing them queues reingestion. Source/timing/translation provenance and correction revisions ship with the transcript. These labels describe origin, not linguistic correctness.

**Repair playback** queues a media-only job. Video can be converted to H.264/AAC; podcasts rebuild their seekable AAC cache. This does not reanalyze sentences or reset learning history. Repair progress/failures are visible in Admin; reload the player when complete. Cache validity checks include the current fingerprint, file existence, and nonzero size. Audio/remux writes use temporary files and bounded ffmpeg execution. Regenerated URLs include a revision, and superseded cache revisions are rejected. Explicit repair can regenerate an existing cache when the browser cannot play it.

The codec policy now checks container/codec combinations. Normal compatible H.264 remuxes can still use stream copy. This does not constitute a complete browser-capability matrix, and explicit Mandarin audio-stream selection remains outstanding.

The Caddy template now proxies `/media/*` through the same dynamic-root resolver used in development, including HTTP Range support. Adding a root no longer requires another per-root Caddy stanza. API and CLI both reject reserved cache slugs and malformed names. Apply the updated Caddy configuration through the normal local deployment procedure; it was not deployed here. Application Range serving is tested, but Caddy itself is unavailable in this execution environment.

## Podcast and timing quality

Pairing prefers explicit episode markers or a single unambiguous number. Dates and multiple unrelated numbers no longer silently pair by the first year. Ambiguous pairs are skipped; a reviewable pairing/diagnostic UI remains planned. SRT podcasts preserve their real cue timing and can skip forced ASR alignment.

English temporal coverage now measures the union of overlapping cue intervals. Two overlapping translations cannot manufacture 100% coverage by double-counting the same time. Forced alignment records matched-character fraction and interpolation flags; the transcript identifies interpolated timing. These measures describe timing anchors, not semantic translation accuracy or learner comprehension.

## Validation and remaining work

- 151 backend tests pass, including source correction/reset/restore, stale revision conflicts, API-only local analysis, correction persistence, repeated-source identity, changed-track isolation, migration/restore, historical-ID reservation, automatic-translation races, stale media revisions, Range serving, atomic conversion failure, timed SRT ingestion, and temporal union/interpolation.
- 26 frontend unit tests pass.
- 33 Chromium production-UI checks pass with synthetic media/API fixtures. New cases cover the correction/history flow, conflict recovery, focus restoration, live transcript refresh, an axe scan of the editor, source selection/repair, and historical dictation targets.
- TypeScript/Vite build, changed Python core correctness checks, and whitespace checks pass. [Mobile editor](screenshots/correction-editor-mobile.png) was visually inspected.

Remaining work includes artwork/ASR-cache repair, audio-stream selection, ambiguity diagnostics, comprehensive personal-data export/restore including browser preferences/attempts, source-quality filtering for graded tasks, validated alignment quality, strict AI response schemas, and worker isolation/cancellation/resource budgets. Manual screen-reader/Safari/iPad/zoom checks, real CPU/GPU/library profiling, live Anki export, and Caddy runtime validation remain outstanding. This delivery does not claim that all M3 or Mandarin-learning roadmap items are complete.
