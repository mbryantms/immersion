# Learner evidence and content recommendations

This delivery separates activity, exposure, and task performance. It runs entirely on the local FastAPI/SQLite and React stack; no remote model is needed. It does not establish that the app improves learning outcomes; that requires delayed and unseen-context assessment.

## What changes for the learner

- Playback records activity, but only one word/source/UTC-day encounter contributes to the new exposure model. Loops, different tabs, and retries do not create independent evidence on the same day. The threshold for estimated Familiar is 12 independent encounters, three sources, and a 14-day span. These are product heuristics, not validated learning thresholds.
- Exposure never marks a word Known. Looking up a word no longer erases inferred familiarity. A lookup may concern curiosity, pronunciation, or a different sense.
- Completing the contextual review ladder still offers the Anki handoff. It records a self-graded result for the practiced task and selected reading/meaning, without marking the whole lexeme Known.
- Reading recall, listening recall, meaning recall, and sentence transcription stay separate. Legacy clients produce unspecified recall and unknown assistance rather than fabricated specificity. Pronunciation and spontaneous production remain explicitly unassessed.
- Home shows task-specific practice evidence over eight weeks. The Word page explains independent exposure and the latest 20 retrieval results, including task, date, assistance, selected reading/meaning, and initial/delayed practice. Self-reports are labelled; there is no combined mastery score or invented confidence probability.
- Optional preferences on Home and Settings establish goal, starting level, character preference, and title-based interests. Level does not mark any vocabulary Known. Character display continues to preserve source text; the existing optional traditional display preference can be changed explicitly.
- Common HSK 1–2/function words remain eligible learning gaps. Home separates words indexed in the library from words with a recorded encounter under the new policy. Counts on those lists are explicitly indexed library occurrences, not actual exposures.

## Evidence and source integrity

`learning_evidence` retains event identity, task, timestamp, method, assistance, score, and scope. Review scope includes selected reading/meaning, saved item, source sentence/revision, shown text, and whether the result follows initial practice. Dictation records its expected sentence and script policy; character matching does not prove meaning recall, listening comprehension, pronunciation, or whole-word knowledge.

`lexeme_exposure` has a unique `(lexeme_id, item_id, day)` key and retains its originating event and task. Full playback events remain in the append-only event stream. Browser events carry their original time through the durable outbox, normalized to UTC for counting. Future-clock events are acknowledged and preserved with their reported timestamp but excluded from evidence, so a bad clock cannot permanently block the outbox. A delayed event preceding an explicit exposure reset does not refill cleared counters. Source revisions are checked before attributing words; an offline event whose source changed is retained without assigning current words to its old playback.

Exposure reset removes the new exposure projection and derived Familiar status while retaining retrieval results, saved cards, and audit events. Manual status and exposure reset remain separate operations. Manual marks and imported Anki intervals retain precedence; neither is presented as measured listening comprehension.

New playback events snapshot word IDs and duration rather than relying only on a later join against mutable text. Dashboard activity uses duration snapshots when available. Legacy events lacking snapshots/revisions cannot recover their original source or task, and legacy counters are labelled separately from new independent encounters.

## Recommendation estimates

Ready, available, unfinished items are ranked by local, inspectable signals:

| Signal | Interpretation and limit |
| --- | --- |
| Unfamiliar token occurrences/minute | New/Learning token occurrences divided by item duration, falling back to transcript extent. This is not a count of distinct new words. |
| Dense unfamiliar stretches | Maximum unfamiliar tokens among cue starts in a forward 30-second window. Long/overlapping cues can distort the estimate. |
| Subtitle pace | Subtitle characters, including punctuation, per minute of summed cue duration; a proxy rather than measured speech rate. Overlap and inaccurate timing affect it. |
| Subtitle source | Automatic/unknown sources receive a warning and ranking penalty. Sidecar/embedded sources are not asserted to be accurate. Semantic and alignment reliability remain to be validated. |
| Goal and starting level | Reading does not apply the listening pace penalty; level changes relative unfamiliar-word weights. No vocabulary is presumed learned. |
| Interests | Literal case-insensitive matching against item/series titles, not semantic topic classification. |
| Learner rating | Too easy / Manageable / Too hard after an optional sample changes the ranking for that episode and skill. Reading feedback does not change listening feedback. |

The former fixed familiarity band is no longer a selection gate. A legacy `band`/`fallback` API response is retained for compatibility; the UI shows estimated vocabulary familiarity and an expandable explanation instead of implying an optimal comprehension threshold. Ignored tokens are excluded from the familiarity denominator and unfamiliar-word counts. All-ignored content has zero eligible tokens, so its percentage alone is uninformative; the API exposes the denominator.

Ratings are optional self-reports, not assessments. They currently adjust the rated episode rather than learning a validated cross-content difficulty model. The profile goal determines which skill's ratings recommendations use. The sample UI records the actual active task. It does not claim the learner completed a sample merely because they submitted a rating.

## Migration and recovery

Migration `d4e6f8a0b2c4` follows `c3d5e7f9a1b2`, adds the evidence/exposure tables and a type/skill/time event index, and passes through the existing verified online SQLite backup gate.

Existing automatically derived Known states become Familiar. Each change appends a `knowledge_policy_migrated` event recording the previous state/source and new policy. Original events, saved IDs, original text, manual choices, and Anki intervals are preserved. Legacy playback counters do not seed the new independent-exposure model because their source revisions, tasks, and repetition cannot be reconstructed reliably. Existing graduated cards remain graduated; migration does not replay review progress. Downgrade removes the new tables/index without recreating unsupported mastery claims or deleting the migration audit.

No personal database or running local deployment was changed during implementation. Apply the branch through the normal local update procedure to run the backed-up migration.

## Verification and remaining gates

The combined branch passes 165 backend tests, 26 frontend unit tests, 37 Chromium browser checks, TypeScript/Vite build, and core correctness lint on the changed application Python files and new evidence tests. New tests cover loop/retry deduplication, original offline dates/UTC normalization, future-clock recovery, delayed pre-reset delivery, source revision changes, beginner gaps, population filters, scoped/idempotent review evidence, transcription limits, profile validation, ignored-word denominators, skill-specific difficulty ratings, and migration preservation.

Browser tests use the production UI with intercepted synthetic API/media fixtures. New mobile flows cover preference saving, indexed/encountered empty states, recommendation explanations, self-report labels, difficulty save failure/retry, selected reading/meaning evidence, horizontal overflow, and WCAG-tagged axe scans. Screenshots were visually inspected at 390px; this is not full WCAG certification or a manual screen-reader test.

A local synthetic SQLite benchmark with 250 items, 40,000 sentences and 320,000 token occurrences returned six recommendations in 182/164/164 ms (median 164 ms); dashboard aggregation took 74 ms. This measures direct warm local service calls in this environment, without HTTP/rendering/model work. Real-library and representative-hardware profiling remain open.

Remaining M4 work: calibrated confidence, finer assistance tracking across all practice surfaces, validated pronunciation/production assessment, alignment/semantic source reliability, and sample-driven generalization to unseen content. Meaning-focused guided scenes and delayed/unseen-context outcome measures remain in M5/M7. See the [roadmap](ROADMAP.md) and [UI record](UI_REVIEW.md).
