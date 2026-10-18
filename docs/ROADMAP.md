# Mandarin learning and interface roadmap

Immersion should help a learner understand authentic Mandarin, recognise it again in unfamiliar contexts, and retain useful vocabulary. This roadmap turns the application audit into a dependency-ordered delivery plan for a single local installation. Learning correctness, usable study flows, and recovery of personal learning data take precedence over adding more features.

Baseline: `bb338a3181e0f339ba797be963644800a701ec1d`. Updated 18 October 2026. Work on this branch includes trustworthy practice, Mandarin representations, source recovery/corrections, learner evidence, guided scenes/construction practice, local shadowing, controlled AI assistance, and a persistent configurable Anki handoff; this document is not a claim that every milestone is complete.

## Delivery decisions

- Retain React 19, TypeScript, Vite, Tailwind, Radix primitives, TanStack Query/Virtual, FastAPI, SQLite WAL, and Anki. These already support a modern, accessible local application. A Next.js/server-rendering migration adds little value to this use case.
- Establish explicit reading, listening, and dictation tasks. Preserve display preferences when switching tasks, hide all app-controlled answer surfaces during an unassisted attempt, and record deliberate hints. Burned-in subtitles inside the source video cannot be hidden by the application.
- Preserve original Chinese text. Canonical forms, displayed script, contextual reading, dictionary sense, and spoken realisation must be represented separately.
- Keep exposure and retrieval as different evidence. Vocabulary familiarity must never be presented as a measured comprehension score.
- Keep Anki as the long-term scheduler. The local review queue is a short contextual preparation stage with an explicit export handoff.
- Keep core playback, dictionary lookup, saving, and practice useful without remote AI or TTS. Explain optional remote dependencies in Settings.

## Status and ownership

`Delivered` means implemented in this branch and subject to the validation record in UI_REVIEW.md. `Partial` means a working first slice exists but named follow-up remains. `Planned` means no implementation claim. Each workstream should be owned by one delivery lead, even when one person fills every role. Effort is approximate engineering work, excluding model downloads, content curation, and user-study recruitment.

| Milestone | Objective | Suggested owner | Effort | Dependencies | Exit gate |
| --- | --- | --- | --- | --- | --- |
| M1 | Trustworthy practice and usable feedback | Full-stack | 1–2 weeks | None | Meaning-changing errors lose credit; retries cannot advance twice; task answers stay hidden |
| M2 | Reliable Mandarin representations and correction | NLP/data | 2–3 weeks | M1 interfaces | Both scripts resolve to intended lexemes; selected readings/senses survive rescans and exports |
| M3 | Media, cache, and data recovery | Backend | 1–2 weeks | M1 revision contract | Rescans, changed media, missing caches, and offline use recover without losing learning history |
| M4 | Evidence-based learner model and recommendations | Learning/data | 2–3 weeks | M2, durable events | Reading/listening evidence is distinct; recommendations calibrate against actual difficulty |
| M5 | Guided scene learning and Mandarin assessments | Learning/full-stack | 3–4 weeks | M2, M4 | Learners complete a scene cycle; assessments have validated answers and track hints |
| M6 | Accessible, performant daily use | Frontend/QA | 1–2 weeks | Runs throughout M1–M5 | Keyboard, screen reader, responsive, and performance gates pass on representative hardware |
| M7 | Retention and measurable learning outcomes | Anki/learning | 1–2 weeks | M2, M4, M5 | Correct export handoff; delayed and unseen-context performance can be measured |

These are planning ranges, not committed dates. Re-estimate after M1 and after testing the real media library. Accessibility and data recovery are continuous gates, not work deferred until the last milestone.

## M1 Trustworthy practice

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| P01 | Replace recall-only dictation scores with normalised edit distance, counting insertions, substitutions, numbers, and names | Delivered | 我爱你/我不爱你 and repeated answers score below 100%; wrong digits and missing Latin names lose credit; client/server share regression cases |
| P02 | Accept equivalent permitted script forms during dictation; distinguish transcription from comprehension | Delivered | 学习/學習 is accepted under an explicit policy; original forms remain visible; ambiguous conversions are not silently accepted |
| P03 | Enforce due eligibility, archive/graduation checks, atomic claim, and idempotent review requests | Delivered | Sequential/concurrent duplicate requests advance once; replaying the same request returns the stored outcome; future-due items return a recoverable conflict |
| P04 | Make the 1/3/7-day ladder accurate | Delivered | Initial practice schedules 1 day, subsequent consecutive successes schedule 3 and 7 days; graduation follows the delayed reviews; a lapse restarts spaced success evidence |
| P05 | Give reviews real answer feedback and saved-snapshot fallback | Delivered | Word answers show dictionary alternatives/pinyin when available; sentence translation is shown; missing feedback is explicit; orphaned live contexts retain text practice |
| P06 | Remove answer leakage from practice | Delivered | Word cloze audio is not auto-played before reveal; every repeated target is masked; listening and dictation hide app overlays, transcript, English, and pinyin until deliberately revealed |
| P07 | Make submissions understandable and recoverable | Delivered | Grading is disabled while saving; failed/uncertain results retain the card; retries reuse one request ID; completion separates recalled and missed items |
| P08 | Add explicit Read, Listen, Dictate modes for both video and audio | Delivered | Keyboard-operable selector explains the task; listening offers an explicit recorded transcript hint; dictation is available for video; returning to Read preserves display preferences |
| P09 | Choose better review contexts | Planned | Rank available, reliable contexts with mostly accessible surrounding language; avoid recently reviewed contexts; prefer a novel context after initial success; exclude ambiguous targets |
| P10 | Resume review after graduation/lapse and complete the Anki handoff | Partial, M7 | Existing graduates cannot be accidentally graded again; add explicit reopening with appropriate learner-state adjustment; unexported graduates remain discoverable |

## M2 Mandarin representation and correction

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| L01 | Introduce occurrence offsets and canonical lookup forms while preserving source text | Partial | Simplified/traditional subtitles share appropriate dictionary identity; text selection uses offsets rather than first substring; Unicode supplementary Han characters work |
| L02 | Stop traditional source words from shattering in simplified-keyed reconciliation | Delivered | 學習, 銀行, 音樂 resolve as intended words with correct contextual readings; reanalysis preserves original text and saved contexts |
| L03 | Store contextual pronunciation separately from first dictionary reading | Partial | Subtitle ruby, lookup, review, and exported pinyin agree; 还/长/行/重/地 fixtures cover multiple contexts; alternatives are labelled rather than silently substituted |
| L04 | Store selected meaning and reading on a saved learning item | Delivered | 会 as ability and 会 as meeting can be learned separately; one sense does not automatically establish all readings/meanings |
| L05 | Explain lexical tones versus connected speech | Planned | Optional notes cover third-tone sandhi, 一/不, neutral tone, and erhua; dictionary notation is labelled; no fabricated word-level timing is presented as exact |
| L06 | Let users correct text, reading, meaning, and timing locally | Delivered | Corrections have provenance/revision history, survive rescans, and propagate to search, review, cache, and export; reset original is reversible |
| L07 | Handle segmentation exceptions and multiword constructions | Planned | Separable verbs and constructions can span tokens; user corrections and per-series names do not corrupt dictionary vocabulary |
| L08 | Improve regional/script presentation and character practice | Planned | Traditional preferences apply consistently to word pages/examples; source region can be recorded; components, phonetic families, and confusing forms aid reading; handwriting is optional |
| L09 | Preserve code-switching text and meaningful spaces | Partial | 我是 Nathan and English passages remain readable after sentence splitting; numbers and names remain assessable |

Migration strategy: add nullable canonical/occurrence/sense fields; backfill in bounded jobs; compare against original text and token offsets before switching reads; preserve legacy IDs through an explicit mapping. Do not overwrite original sentence text with OpenCC output. Back up the database before migration and verify restore before rollout.

## M3 Media and data reliability

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| D01 | Revise transcript caches after translation, alignment, replacement, or analysis | Delivered | Translation/alignment increment revision; clients periodically revalidate. Complete revision handling for every edit path; browser tests show new timing/English without reload |
| D02 | Update English FTS in the translation transaction | Delivered | Newly translated sentences are searchable immediately; failed batches retain the already committed index and translations |
| D03 | Treat search input as literals; normalise tones and canonical script | Partial | Punctuation/FTS-looking input never causes a server error; spaced numbered/marked pinyin and traditional queries find simplified sources. Add concatenated pinyin, ü variants, and traditional-source backfill |
| D04 | Persist learner events until acknowledgement | Delivered | HTTP failure, offline reload, declined beacon, and uncertain beacon delivery retain UUIDs; acknowledged entries are removed; duplicate delivery does not double counters |
| D05 | Use effective track timing everywhere | Partial | Review/search/export use the shared timing helper; complete all snapshot and custom-clip consumers; positive/negative offsets tested near zero |
| D06 | Reset player session state between items | Delivered | Episode navigation remounts item-specific state; resume, speed, reveals, dialogs, and hints do not leak to another item |
| D07 | Repair subtitle discovery and selection | Delivered | Deleted/unreadable sidecars are deselected; all available tracks can be selected explicitly; selected source/script is visible; embedded cache includes media fingerprint |
| D08 | Repair missing/stale media caches | Partial | Missing remux/audio triggers repair; regenerated URLs include content revision; thumbnails update after source changes; writes are atomic |
| D09 | Handle codec/container/audio-track combinations | Partial | Actual browser capability and tested fallback determine direct play; audible Mandarin track selection is explicit; conversion failures have recovery actions |
| D10 | Make root configuration work through the local serving stack | Delivered | Adding a root makes it streamable in dev and production without a manual Caddy edit; reserved routes cannot collide; missing roots do not erase history |
| D11 | Improve podcast pairing and ingestion diagnostics | Partial | Dates and episode numbers do not silently pair wrong files; ambiguous pairs are reviewable; timed SRT input preserves useful timing rather than discarding it |
| D12 | Preserve sentence identity across reingest | Delivered | Repeated identical lines relink by source/time/identity; SQLite ID reuse cannot attach old events to new text; saved attempts and contexts retain revisions |
| D13 | Backup, export, and restore personal learning data | Partial | SQLite online backup includes WAL consistency; preferences/attempts/corrections can be exported; restoring to a clean install is tested; caches are regenerable |
| D14 | Separate CPU and GPU setup and expose capability status | Planned | CPU install does not require CUDA packages; GPU fallback is explained; missing ffmpeg/models/Anki are actionable; optional network features fail gracefully |

## M4 Learner evidence and recommendations

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| K01 | Separate reading, listening, pronunciation, meaning, and production evidence | Partial | Scoped reading/listening/meaning review and sentence-transcription evidence retain timestamp, method, assistance and reading/meaning; Word/Home explain evidence. Pronunciation/production remain explicitly unassessed; calibrated confidence and finer assistance remain open |
| K02 | Treat exposure as familiarity rather than mastery | Delivered | Source/day-deduplicated exposure can only infer Familiar; lookups do not demote; review graduation does not mark whole lexemes Known; exposure reset and audit preserve the distinction |
| K03 | Use honest coverage language | Delivered | Player/library/home use vocabulary familiarity; recommendation explanations state uncertainty and ignored-word denominator; source pace and activity remain labelled estimates; retrieval has task-specific labels |
| K04 | Recommend content using more than a fixed token threshold | Partial | Ranking includes unfamiliar occurrences/minute, dense cue-start windows, subtitle pace, source warnings, title interests, goal/level, and skill-specific episode ratings; fixed band no longer gates selection. Validated source quality and cross-content sample calibration remain open |
| K05 | Remove beginner-hostile common-word assumptions | Delivered | Optional Home/Settings preferences establish goal/script/level/title interests without marking vocabulary known; common HSK/function words remain eligible gaps |
| K06 | Distinguish indexed corpus from actual encounters | Delivered | Home has indexed/encountered filters and honest library counts; Word shows independent exposure and legacy-counter limits; loops are raw activity, not independent mastery evidence |

## M5 Guided learning and content quality

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| G01 | Build an optional short-scene learning cycle | Delivered | Source-snapshotted Read/Listen scenes resume across reloads; supported study → reduced support → local keyed check or labelled reflection → due revisit; revisions/retries/source changes are guarded and free viewing remains available |
| G02 | Add meaning-focused Mandarin comprehension tasks | Partial | Versioned bundled contrasts cover roles, negation, aspect, result, comparison and paraphrase; local scene questions require explicit review and explain distractors. Reports suspend grading and exclude prior questionable results while retaining audit. Independent linguistic validation and automatic grounded scene questions remain open |
| G03 | Teach reusable constructions | Partial | Twelve offline construction lessons provide explanations, contrasting examples and candidate simplified/traditional library links. Candidate markers are not validated grammar parses; richer paired patterns and validated contrasting library examples remain open |
| G04 | Make vocabulary mining selective | Delivered | Optional daily intake suggestion, scene repetition candidates, deliberate definition saves and over-budget choices, no bulk preselection, confirmed/failed-save recovery, and reversible Active/Suspended views preserve progress without treating saved counts as success |
| G05 | Add recording/shadowing and careful pronunciation feedback | Partial | Browser-only source/learner comparison, source-bound IndexedDB, download/delete and permission/cancellation/quota recovery are implemented. No pronunciation grade is inferred; validated tone/phonetic feedback and learner/hardware validation remain open |
| G06 | Expose source and timing provenance | Partial | Official/sidecar/ASR/corrected text, source/generated translation, engine, and timing reliability are distinguishable; low-quality material is excluded from high-stakes grading |
| G07 | Repair alignment confidence semantics | Partial | Timestamp overlap is labelled temporal coverage; overlapping intervals use union coverage; mismatches and interpolated timings are flagged; semantic correctness is assessed separately |
| G08 | Ground and validate AI explanations | Partial | Prompt-v4 strict nested schemas and complete adjacent-token coverage reject malformed output; source/model/analysis context, source-edit discard, persistent rejection and explicit idempotent retry are implemented. Linguistic accuracy, particle completeness and generated-example level remain unvalidated |
| G09 | Control speculative AI work and offline behaviour | Partial | Prefetch defaults off; extras are explicit; API requests have bounded queues, cancellation and interactive priority; API/worker share a provider lock; cache works without the CLI and remote use is visible. Active-worker preemption, cross-process cancellation/priority and full job budgets remain open |

## M6 Interface and performance

See [UI inspection and validation](UI_REVIEW.md) for the route-by-route review and the first implementation slice.

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| U01 | Consistent semantic controls and keyboard access | Partial | Study selector uses Radix roving focus; player toggles expose state; shared focus styles and skip link exist. Gloss uses Radix focus trapping/restoration and has a passing keyboard test; finish the remaining icon names, language tags, and route focus announcements |
| U02 | Responsive readable learning surfaces | Partial | Study choices remain labelled on narrow screens; coarse-pointer learning actions target 44px; Chinese text keeps readable line height. Verify at 320/390/768/1440px and 200% zoom with no clipped actions |
| U03 | Review feedback, loading, error, and recovery states | Delivered | Pending grades cannot double-submit; transcript/media/search failures have retry; missing dictionary/audio has explicit fallback; session progress exposes its value accessibly |
| U04 | Dictation accessibility and efficiency | Partial | Labelled input, IME-safe submit, longer touch targets, stored attempts, and bounded input. Finish full virtualisation, measured row heights, memoised feedback, and interruption-safe persistence |
| U05 | Profile real local workloads | Planned | Measure small/large libraries, long transcripts, CPU transcription, playback while importing, and memory/VRAM; publish baseline hardware and p50/p95 measurements |
| U06 | Optimise queue, library, and alignment queries | Partial | Export inbox/history use SQL limits/cursors and batched relations; supporting indexes reduce a synthetic 10,000-card inbox median from 340.49 to 2.97 ms. Due queue, library aggregates, random context selection and alignment sweeps remain open |
| U07 | Prioritise interactive work without resource contention | Partial | Long transcription/transcode cannot starve quick dictionary/review/export work; bounded workers or cooperative stages respect CPU/GPU budgets; ffmpeg has timeouts/cancellation |
| U08 | Automate interaction and accessibility regression checks | Partial | 62 Chromium checks passed at the preceding handoff build; the final 63-check rerun is blocked by sandbox Chromium/socket permissions. Checks cover production React routes with synthetic media, including guided scenes, local recording/native-codec playback, AI feedback/cancellation/policy, question/contrast feedback, selective mining, reversible suspension, nine baseline page axe scans, export setup/recovery, and expanded-surface scans; current build/unit/backend checks pass. See RETENTION_HANDOFF.md for the exact verification boundary. Add CI and manual screen-reader/Safari checks |

## M7 Retention and outcomes

| ID | Issue and implementation | Status | Acceptance criteria |
| --- | --- | --- | --- |
| A01 | Export selected contextual pronunciation and meaning | Partial | Edited sense/reading and corrected sentence survive preview/export; exact source audio has effective timing; card front/back correspond to the intended skill |
| A02 | Make Anki schema/deck/field mappings configurable | Delivered | Existing deck/model/field mappings, both-script text, live preflight, selected-reading protection, explicit template review, saved configuration and duplicate choices replace the required personal schema. Live collection/template checks remain a release gate |
| A03 | Reconcile Anki evidence over time | Planned | Deleted/lapsed/suspended/nonmatching cards update derived evidence appropriately; reading-card maturity is not treated as listening mastery; manual precedence remains explainable |
| A04 | Keep graduates awaiting export visible | Delivered | Persistent paginated Ready/Deferred inbox and history, complete per-card outcomes, source-bound submissions, exact-request retries, tag reconciliation and explicit unconfirmed-add recovery preserve cards/progress through close/reload/failure |
| O01 | Separate activity from learning outcomes | Partial | Home labels media-duration activity honestly. Guided checks retain explicit hints/replays, skill and delayed status; bundled practice distinguishes first/repeat attempts and reported-question grades are excluded from averages. Actual active time/rate and unseen-context transfer remain open |
| O02 | Add periodic unfamiliar-material benchmarks | Planned | Short comparable reading/listening samples provide interpretable trends; avoid coaching on benchmark material; report difficulty and uncertainty |
| O03 | Validate usefulness with learners | Planned | Beginner/intermediate and both-script learners complete key tasks; observe lookup disruption, support dependence, review load, and delayed transfer; revise based on failures |

## Release and test gates

1. **Correctness:** shared adversarial dictation cases; explicit script policy; server review eligibility/idempotency/concurrency; missing context/audio; full-text input escaping; cache revisions; effective timing and Anki clipping.
2. **Interaction:** real app routes with synthetic local video/audio, repeated-target cloze, rapid click, network failure/retry, item navigation, processing completion, and no accidental answer surfaces. Verify burned-in video subtitles are documented as a source limitation.
3. **Accessibility:** WCAG 2.2 AA target; named controls, visible focus, logical order, dialog focus/escape/restoration, IME composition, reduced motion, contrast checks, 200% zoom, adequate target size, accessible progress and errors. Automated tests supplement manual checks.
4. **Performance:** provisional targets on documented reference hardware: cached route usable within 1s, dictionary placeholder immediate and full response p95 <200ms, no >50ms input tasks in normal dictation, stable playback during background work. Establish baselines before claiming these targets are met.
5. **Data safety:** restore backup before destructive migrations; no model-triggered deletion of originals; migrations preserve saved contexts/events/corrections; cache regeneration cannot reset learner evidence.
6. **Learning quality:** no grade implies comprehension beyond the tested task; distinguish assisted/unassisted and exposure/retrieval; validate generated question answers; test delayed transfer rather than collection size.

## First delivery checklist

- [x] Add explicit study modes and make video dictation available.
- [x] Hide app-controlled text before listening/dictation responses.
- [x] Penalise extra negation, repetition, wrong numbers, and missing names.
- [x] Add safe spaced-review submission, full answer feedback, repeated-target masking, and snapshot fallback.
- [x] Preserve learner events through submission failures and reloads.
- [x] Repair translation indexing and begin revision-aware refresh.
- [x] Add effective timing to review/search/export and reset per-item player state.
- [x] Improve keyboard focus, touch controls, progress semantics, and error feedback.
- [x] Complete production build and browser/accessibility verification with synthetic local media.
- [ ] Deliver contextual pronunciation/canonical-script migration before claiming comprehensive traditional-input support.

## Recommended next pull requests

1. **Canonical forms and selected readings follow-up:** reconcile legacy duplicate lexeme IDs without conflating learning evidence; improve automatic polyphone/particle disambiguation and correct spans that change segmentation. The first implementation of L01–L04 and P02 is delivered; see [Mandarin phase delivery](MANDARIN_REPRESENTATION.md).
2. **Media recovery follow-up:** complete D08–D09 and D11/D13, including artwork/ASR caches, explicit Mandarin audio-track selection, ambiguous-pair diagnostics, and full personal-data export/restore. The correction/identity/source-selection delivery is described in [source reliability](SOURCE_RELIABILITY.md).
3. **Learner evidence follow-up:** complete K01/K04 calibration, finer hint tracking, and source-quality validation. The first K01–K06 delivery preserves original events, manual choices and Anki intervals; see [learner evidence](LEARNER_EVIDENCE.md).
4. **Guided learning follow-up:** validate bundled language/difficulty, strengthen grounded scene questions and grammar matches, validate G05 pronunciation feedback, and complete G08 linguistic checks/G09 worker scheduling. The local recording and structural AI/control slice is documented in [shadowing and AI](SHADOWING_AI.md). The first G01–G04 delivery is described in [guided learning](GUIDED_LEARNING.md).
5. **Daily-use polish and retention:** remaining U items, A01–A04, O01–O03, and measured performance improvements.

## Canonical forms and selected readings delivery

See [implementation, migration, verification, and limitations](MANDARIN_REPRESENTATION.md). This phase adds source offsets in Unicode codepoints, dictionary-backed traditional aliases, normalized tokenizer input mapped back to original text, context-level pinyin estimates, explicit per-definition saves, occurrence-specific reading replay, and conservative opt-in dictation script pairs. A sense-specific graduation never marks the whole lexeme known. Existing source text, sentence IDs, events, and saved IDs are preserved by the additive migration and in-place backfill.

L01 remains partial because historical duplicate lexeme IDs are retained rather than automatically combining their knowledge/events. L03 remains partial because automatic pronunciation is not a validated linguistic analysis; fixtures improve known cases but particles and ambiguous contexts still require a selected reading. L09 covers the analysis/sentence-splitting path; subtitle ingestion paths still need a full spacing audit. A01 now exports selected reading/meaning and contextual sentence pinyin; live Anki/media validation remains pending. Full M2 also includes L05–L08, which remain planned.

## Source reliability and local corrections delivery

[Implementation, migration, and validation](SOURCE_RELIABILITY.md) describes the next completed delivery. Local text/meaning/reading/timing corrections now have history, conflict protection, reset/restore, and an editor. Permanent sentence identities preserve matched contexts across reingestion and prevent SQLite ID reuse from reassigning old events. New checked dictation attempts retain their expected text and revision. Subtitle choices persist, unavailable tracks are deselected, and embedded caches include source fingerprints. Playback repair, cache revision URLs, conservative codec/container checks, dynamic-root serving, safer podcast pairing, timed SRT ingestion, union temporal coverage, and interpolation flags are implemented.

D08 remains partial for artwork and ASR-cache recovery; D09 for explicit audio-track selection/browser capability testing; D11 for reviewable ambiguity diagnostics; D13 for a full export/restore flow including browser data. G06–G08 remain partial for provenance-aware task filtering, fuller alignment-quality presentation/validation, and linguistic AI validation; the structural schema/rejection work is now covered by the shadowing/AI delivery below. U07 has ffmpeg timeouts, but worker isolation, budgets, and cancellation remain outstanding. Legacy records cannot recover source revisions that were never recorded. No production database or local deployment was changed during this work.


## Learner evidence and recommendation delivery

[Implementation, migration, UI and performance evidence](LEARNER_EVIDENCE.md) describes this delivery. Passive encounters are deduplicated per word/source/UTC day, never create Known, and survive offline/retry delivery without inflating evidence. Lookups no longer erase familiarity. Review graduation retains scoped self-report evidence rather than promoting whole-word knowledge; transcription remains separate. The migration audits legacy derived Known → Familiar while preserving original events, manual marks, Anki intervals, and graduated queues.

Optional learning preferences, beginner-safe word eligibility, indexed/encountered filters, Word/Home evidence summaries, visible recommendation reasons, subtitle pace/source warnings, and per-skill sample ratings are implemented. K01/K04 remain partial for calibrated confidence, finer assistance, validated source quality, and cross-content sample calibration. Pronunciation/production are explicitly unassessed. Combined checks: 165 backend, 26 frontend unit, 37 Chromium; synthetic local recommendation median 164 ms over 320,000 token occurrences. No production database or deployment was changed.


## Guided learning and selective mining delivery

[Implementation, migration, learning limits and verification](GUIDED_LEARNING.md) describes optional source-snapshotted scenes with supported study, selective clarification, reduced support, reviewed local checks/self-reflection, and due revisits. Twelve versioned offline construction lessons cover core Mandarin meaning contrasts and link to candidate library examples. Question reports preserve audit while excluding earlier keyed results from averages. Intake suggestions, explicit contextual saves, partial-failure recovery and reversible card suspension reduce collection pressure without claiming saved cards are learned.

G01/G04 are delivered. G02/G03 remain partial for independently validated language/difficulty, automatic grounded scene questions and validated grammar/contrast matching. This first guided delivery preceded the recording/AI slice below; G05/G08/G09 now have working partial implementations. Combined verification is 188 backend, 26 frontend unit and 45 Chromium checks plus build/lint/whitespace checks. New screenshots were inspected; production data/deployment were not changed.


## Local shadowing and controlled AI delivery

[Implementation, recovery boundaries, learning limits and verification](SHADOWING_AI.md) documents browser-only recording, source/learner comparison, source-bound persistence, downloads, removal and permission/quota/cancellation recovery. Recording is explicitly unassessed and absent from reduced-support/check steps. Strict AI schemas and complete token grounding reject malformed output; source changes discard stale results; rejection persists and regeneration is explicit and idempotent. Settings makes prefetch opt-in, extras require a separate request, close/abort cancels exact requests, and API/worker share bounded provider execution. Existing caches work without a CLI.

Combined validation is 216 backend, 27 frontend unit and 53 Chromium checks plus build/lint/whitespace checks. Native Chromium encoder/storage/reloaded-playback verification uses an oscillator stream; actual microphones, Safari/iPad and pronunciation assessment are not certified. G05 remains partial for validated feedback; G08 for linguistic accuracy; G09 for cross-process priority/cancellation and worker budgets. Next daily-use work should address the remaining U items and retention/export handoff, while keeping independent language/content validation explicit.


## Configurable Anki handoff and export inbox delivery

[Implementation, migration, recovery semantics, benchmark and verification limits](RETENTION_HANDOFF.md) describes existing-model/deck mappings and preflight, explicit card-template review, browser reminders for ambiguous submissions, source-bound immutable attempts, persistent graduate deferral/history, and per-note tag reconciliation. Unknown remote outcomes never silently trigger another add. Source changes, selected readings, local removal/ID reuse, duplicate choices and partial results remain explicit. Anki export does not create mastery evidence.

A02/A04 are implemented; A01 retains live source-audio/template validation and A03 evidence reconciliation remains planned. U06 now includes measured export-query/index work, while queue/library/alignment and real-hardware profiling remain open. Current backend/unit/build/lint checks pass (245 backend, 30 unit). An earlier browser pass completed 62 checks; the final 63-check rerun was blocked before Chromium launch. Final small layout/message refinements and the added long-sentence test need a permitted-environment browser rerun. No production database or deployment was changed.
