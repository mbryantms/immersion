# Guided Mandarin scenes and construction practice

This delivery adds an optional short-scene learning cycle, versioned offline construction exercises, selective vocabulary intake, and reversible local-card suspension. It uses the existing React/TypeScript/Tailwind/TanStack and FastAPI/SQLite stack. Core guided practice does not call an AI provider or download models.

## Study a short scene

Choose **Study a short scene** in Watch. The current sentence, or the first sentence when playback has not started, anchors a scene of up to 60 seconds and 20 cues. The API supports 15–120-second windows. A cue is never cut in half; invalid timing, cues beyond known media duration, and a first cue longer than the requested window produce an actionable failure. Only the starting Chinese track is included.

The scene takes the active Read/Listen goal and preserves source text, translations/provenance, word analysis, sentence IDs/revisions, source fingerprint, effective timing, title, and media kind. A source correction, timing change, missing sentence, or fingerprint change disables old audio and keyed grading while retaining the original snapshot. It does not silently attach the old question to new text. Missing audio leaves reading/reflection available.

| Step | Behavior |
| --- | --- |
| Watch or listen | Get the situation with Chinese and available translation. Advancing is self-paced, not proof that playback completed or meaning was understood. |
| Clarify | Inspect dictionary candidates ordered by scene repetition, choose the reading/meaning that fits, and save only useful expressions. Saving is optional. |
| Less support | Listening hides the app-controlled transcript; reading keeps Chinese and hides English. Deliberate Chinese/translation hints and explicit Replay actions are recorded. |
| Check meaning | Use a reviewed local question when available, or an explicitly labelled self-reflection. Feedback explains each interpretation. Neither is an unseen-context benchmark. |
| Revisit later | Complete the scene after a check/reflection. Initial completion schedules one day; successive eligible revisits schedule three then seven days. Revisits begin with less support and reset the current attempt's hints. |

Progress is stored in SQLite, so reloads and browser changes resume the cycle. UUID retries and revision checks prevent duplicate advancement; concurrent stale changes return a recoverable conflict. Due scenes sort ahead of unfinished/future scenes, including when the inbox reaches its 30-item display limit. Home exposes resume/due scenes; `/practice` lists guided work and the construction library.

Playback is bounded to the snapshot interval. The Replay button restarts the interval; seeking is clamped without repeatedly setting the same playback position. Burned-in video subtitles cannot be hidden. Browser-native controls can replay material without using the explicit Replay button; the recorded explicit count is not a complete replay measurement. Guided playback emits activity events, while the existing media-minute estimate continues to use free-player sentence-completion events; advancing a scene does not fabricate minutes or independent exposures.

## Local scene questions and honest evidence

Before the hidden attempt, a teacher, study partner, or learner can add a local multiple-choice question. The form requires an exact source sentence, a meaning contrast, distinct choices, explanations for both choices, a selected key, and an explicit review of ambiguity. The API accepts two to four choices, rejects unknown question fields, blank content, invalid keys and non-source passages. Authoring is limited to the supported study steps, so opening an editor cannot reveal answers during a hidden attempt.

Questions retain their authoring/source revision. The public question payload omits the key/explanations until submission; the server scores the selected choice. Replacing a question preserves its previous record. Its provenance remains **learner-authored and reviewed, not externally validated**. The author has seen the answer, and that fact stays with the evidence.

A report suspends a questionable key, preserves the original attempt and explanations, excludes earlier keyed results from dashboard averages, and offers reflection in its place. Restoring a bundled exercise allows future practice without retroactively reinstating excluded results. Original scores remain in the event audit; `learning_evidence.valid_for_summary` is an explicit projection of assessment eligibility, not a rewrite of the original answer.

`scene_meaning_choice`, `scene_meaning_reflection`, and `construction_meaning_choice` remain distinct from ordinary reviews and transcription. Evidence records method, assistance, source/scene or construction version, prior study of the same context, and delayed revisit. Bundled exercises identify first attempts separately from repeated practice. No scene result changes whole-word Known status. Confidence calibration, pronunciation, spontaneous production, active-time/rate measurement, and transfer to unfamiliar material remain unassessed/open.

## Mandarin constructions

Twelve versioned offline lessons provide concise explanations and contrasting examples:

- 把 / 被 and who acts versus who is affected;
- 不 / 没 and occurrence/experience negation;
- 了 and event/change readings;
- experiential 过 versus ongoing activity;
- 着 and maintained states;
- result complements such as 看完 / 看懂;
- 比 / 没有 comparisons;
- 虽然…还是 concession and paraphrase;
- 的 / 地 / 得;
- measure words;
- topic/comment versus agent;
- separable verb–object forms.

Exercises target narrow meaning contrasts, with explanations for each distractor. Answer positions vary across exercises. The key is server-held and version-checked; stale clients cannot grade a new version using old choices. Failed submissions retry the same choice/UUID. Reports suspend exercises locally; a reviewed restore resumes future practice. The bundled linguistic examples have not undergone independent teacher/learner validation, so the UI labels them as practice, not certified assessment material.

Library links use marker matching against original simplified/traditional text. They are explicitly **candidate examples**, not validated grammar parses or guaranteed contrasts. Polysemy, lexicalized expressions, omitted markers, and broader discourse can defeat marker matching. This first library supports noticing and source exploration; it does not automatically certify arbitrary video questions or language analysis.

## Selective vocabulary intake

Settings offers a 0–30-word daily suggestion, default five, counted by newly created word cards in UTC. Archiving/suspending a card does not erase that day's intake. The budget is a soft guide; direct saves remain available. Guided mining requires a deliberate contextual definition and an explicit override beyond the suggestion. Suggestions start with at most three candidates and can be expanded; common beginner words remain eligible.

The session summary starts with no preselected words. It waits for confirmed saves, records save activity only after acknowledgment, retains failed choices, and skips already confirmed cards on retry. It no longer reports success before requests finish. Dictionary candidates, saved-card counts, and absence of lookups are not presented as learning success.

Saved now has **Active cards / Suspended cards** views and named Suspend/Resume actions. Suspension preserves source contexts, selected reading/meaning, original ID, due date, review rung and evidence, and appends an audit event. It removes the card from local due/export-waiting counts. Resume retains its previous due date, so an overdue card can be due immediately. Suspension does not change a linked Anki card's status; manage that separately in Anki. Permanent Remove remains a separate action.

## Migration, verification and limits

Migration `e5f7a9b1c3d5` follows `d4e6f8a0b2c4`. It adds guided scenes, local questions and their indexes, and a default-true summary-eligibility column for existing learning evidence. The verified online SQLite backup gate runs before upgrade. Tests seed the previous schema and verify original event/evidence preservation. Original media/subtitles, existing cards, Anki state and prior scores are not replaced. Scene snapshots are stored once; idempotent event replies retain small mutable response fields and reconstruct the immutable snapshot on replay.

Combined validation: **188 backend tests, 26 frontend unit tests, 45 Chromium checks**, TypeScript/Vite production build, core correctness lint for changed application Python/new guided tests, and whitespace checks. Tests cover source/timing boundaries, idempotent and concurrent steps, hint/reflection scope, due eligibility, reviewed key/schema rules, hidden keys, source/version conflicts, suspension and summary exclusion, intake accounting, first/repeat attempts, migration preservation, production UI retries, failed mining saves, reversible card suspension, seek/replay bounds, mobile overflow, and WCAG-tagged scans. New pages are lazy loaded.

The production UI was inspected with synthetic local media and intercepted APIs at 320/390px. Browser tests and API/SQLite tests are separate; they do not certify the user's media library or microphone/audio hardware. Automated accessibility checks are supplemented by visible layout inspection, not full WCAG certification. The dictionary popup's opacity fade was removed after a contrast failure during animation; its motion remains and reduced-motion settings still apply.

Still open: microphone recording/shadowing and validated pronunciation feedback; teacher/learner validation of exercise language and difficulty; automatic grounded question generation with review; stronger semantic/alignment reliability gates; validated contrasting library examples; fine-grained assistance across all player surfaces; strict AI explanation schemas and speculative-work control; cross-content calibration, long-transcript/performance work, full backup/export UX, and live Anki/Caddy/device/manual screen-reader checks. No personal production database or running local deployment was changed.
