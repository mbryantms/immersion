# Mandarin canonical forms and selected readings

Implemented after the initial study-flow delivery, 18 October 2026. This is the first approved follow-on phase, scoped to L01–L04/P02. The roadmap records remaining work separately.

## Learner-visible changes

- Traditional-source words such as 學習, 銀行, and 音樂 retain their original spelling and resolve through dictionary aliases to the appropriate simplified lexeme. Tokenization uses a simplified working copy only when codepoint lengths agree, then maps tokens back to the unchanged source.
- Every analyzed token records half-open source offsets in Unicode codepoints. Browser selection uses those positions, excludes ruby annotations, and distinguishes repeated occurrences. Supplementary Han characters count once.
- Automatic pronunciation uses sentence context rather than separately pronouncing every token. Lookup labels it as an estimate and displays dictionary alternatives separately.
- Lookup offers one radio choice per definition. Save selected meaning records that definition and reading. Different meanings/readings of the same lexeme become distinct learning items; repeat saves of the same selection add context to the same item. Saved cards show the selected reading and meaning.
- Selecting a reading updates the precise occurrence's ruby/pinyin and transcript revision. Review and Anki preview use the selected reading/meaning. Reanalysis replays the correction only when source text, ordinal, token surface, and offset still match. It never guesses the first matching substring.
- Graduating a selected sense does not promote the entire lexeme to Known. Manual whole-word overrides and existing Anki evidence remain separate.
- Dictation defaults to matching the source script. An explicit selector permits unambiguous simplified/traditional character pairs. Checked attempts retain their original policy after settings change/reload. Feedback retains source spelling. Ambiguous mappings such as 后/後 and 发/髮 are deliberately excluded. This is transcription accuracy, not comprehension.
- Search indexes canonical token/character forms when an item is analyzed again. Original Chinese and English remain intact.

## Data model and upgrade

Alembic revision `a2b4c6d8e0f1` adds nullable token occurrence offsets/canonical form/reading and saved-item selected reading/meaning/provenance. It does not delete or renumber any existing row. Source spelling and occurrence readings also live in sentence analysis JSON. Saved contexts snapshot analysis and the selected occurrence, retaining text practice and export feedback when a live sentence disappears.

Before migrating an existing database, startup/`immersion upgrade` creates an online SQLite backup under `data_dir/backups`. SQLite's backup API includes committed WAL content. The backup is restored into an in-memory database and checked for integrity and foreign-key consistency before Alembic runs. Failed verification stops the upgrade. Existing databases at the current revision do not create another backup on each launch. No personal production database was migrated during development; migration/restore verification uses temporary fixtures.

Run the normal API/worker startup or `immersion upgrade` to apply the additive schema change. Then run the existing background worker and enqueue in-place analysis:

```sh
immersion reanalyze --item-id 123  # try a representative item first
immersion reanalyze                # queue all items, one job per item
```

These jobs run at low priority and commit per item. They preserve sentence IDs, timing, translations, saved IDs, and existing events, rebuilding token occurrences and FTS and incrementing transcript revisions. They require the existing HanLP worker/model setup; the API never imports Torch. Existing transcript payloads synthesize safe offsets until backfill completes. Legacy unknown/orphaned words remain usable; ambiguous historical identity merging is intentionally deferred.

To roll back, stop API and worker, retain the current database for diagnosis, and restore a verified pre-upgrade backup with the prior application revision. Do not downgrade schema while the new application is running. Cache files are not part of this schema backup.

## Validation

- 121 backend tests pass, including both-script reconciliation, supplementary characters, repeated offsets, polyphone fixtures (还/长/行/重/地), code switching, conservative script scoring, separate saves, selected reading replay/export/review, online WAL backup, and migration from the previous schema with original IDs preserved.
- 26 frontend unit tests pass, including client script scoring and source feedback.
- 29 production-UI Chromium checks pass, including script-policy interaction, exact selected-definition payload, repeated-word DOM selection, existing study/review flows, mobile layouts, and WCAG-tagged automated scans.
- TypeScript/Vite build and changed Python core correctness checks pass.
- [Selected-meaning mobile screenshot](screenshots/selected-meaning-mobile.png) is from the production React UI with synthetic media/API fixtures. The dialog was visually inspected at 390px and its controls remained readable within the scrollable sheet.

## Remaining limitations

Automatic pypinyin output remains fallible: isolated 长, adverbial 地, names, and ambiguous syntax can be wrong. A selected dictionary reading is an explicit correction, not a validated pronunciation score. Source timing remains sentence-level. Standalone corrections, text/timing editing, sandhi teaching, and resegmented correction spans belong to L05–L07.

This migration preserves legacy lexeme IDs instead of collapsing historical traditional-only duplicates. New/reanalyzed occurrences use canonical dictionary identities; evidence reconciliation across old duplicate identities needs an explicit, reversible mapping in the learner-model phase. Reanalysis cannot restore original whitespace removed by an earlier ingest. Reordered repeated lines may require selecting the intended reading again; no correction is silently transferred when identity checks fail.

Anki field construction is verified locally. Live Anki export, exact media clipping on a real library, Safari/iPad, screen readers, and CPU/GPU profiling remain unverified. Selected-reading saves omit generic isolated-word TTS because text-only synthesis cannot guarantee the chosen pronunciation; source sentence audio remains available. Full configurable note schemas and Anki evidence reconciliation remain in M7.
