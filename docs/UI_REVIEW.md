# Interface inspection and validation

The first interface changes make study intent explicit and feedback recoverable while keeping the existing React, Tailwind, and Radix design system. This review covers the application's route components, player surfaces, shared styles, keyboard handling, data-query states, and answer visibility.

## Inspection scope

The source inspection covers Home, Library/Series, Watch, Review, Saved/Export, Search, Word, Settings, Admin, and shared navigation/dialog/player controls. Runtime inspection used the actual production-built React application in Chromium with synthetic local video/audio and intercepted API fixtures. It covered desktop and mobile layouts, keyboard behaviour, retry flows, and automated contrast/accessibility checks. Personal media, Safari/iPad, manual screen-reader behaviour, and real-library GPU performance remain separate validation tasks.

## Route findings and changes

| Surface | Finding | First implementation | Remaining inspection |
| --- | --- | --- | --- |
| Navigation | No skip link; utility actions are small; route errors can retain focus unpredictably | Skip-to-content target and shared focus outlines | Keyboard route focus announcements and error-boundary reset across routes |
| Home | Activity presented as comprehensible input; coverage used as comprehension guidance | More precise familiarity/activity copy | Real content density, onboarding, chart accessible alternative, query failure combinations |
| Library/Series | Coverage obscures evidence source; readiness and availability can be confusing | Named sorting controls, semantic filter groups, accessible readiness/playback progress, and clearer vocabulary-familiarity labels | Large libraries, filters/search, missing media, clear processing versus playable state |
| Watch | Learning actions mix task choice and display preferences; subtitles-off leaves transcript visible | Labelled Read/Listen/Dictate selector, task explanation, explicit transcript hint; preserve preferences | Real video/audio, desktop/mobile/zoom/fullscreen, caption contrast over changing frames |
| Watch controls | Toggle state absent from assistive technology; dense short targets | aria-pressed for loop/pause/pinyin/script; focus outlines; 44px coarse-pointer learning actions | Volume/progress keyboard operation, short landscape layout, PiP subtitle limitations |
| Dictation | Audio-only entry; overlay leaks answers; inputs lack explicit labels; repeated work on render | Video support, overlay suppression, input labels, bounded input, cached scoring and debounced persistence | Long-transcript virtualisation, scroll/focus during playback, storage-unavailable behaviour |
| Review | Missing definitions; auto-spoken cloze; repeated target leaks; no save pending/error state | Full dictionary feedback, all-target masking, no pre-answer word audio, frozen session queue, guarded grades, retry/reload, honest summary | Network interruption during submission, autoplay denial, screen-reader feedback and focus between cards |
| Gloss | Custom modal has initial focus but no complete trap/restore contract | Radix Dialog provides focus trapping, Escape dismissal, and focus restoration while preserving the fullscreen portal and Space-to-resume workflow | Manual screen-reader and fullscreen device checks |
| Saved/Export | Personal note schema; graduates can disappear from daily practice | Correct dashboard waiting count; effective timing for clips | Configurable schema, interrupted export and duplicates, persistent export inbox |
| Search | Search failure can look like an empty initial screen; unsupported query punctuation | Named query input, explicit retry/error state, literal query parsing | Marked/numbered pinyin, traditional-source backfill, long results and focus order |
| Word | First dictionary reading may be wrong in context; traditional preference incomplete | Preserve alternatives; roadmap identifies contextual reading work | Both scripts, component examples, meaningful stroke interaction and missing-data fallback |
| Settings/Admin | Mixed capability assumptions; core versus remote features not sufficiently clear | Keep existing configuration; roadmap specifies capability/preflight and CPU/GPU work | Missing models/ffmpeg/Anki, offline explanations, safe backup and recovery |

## UI standards

Use semantic native controls or established Radix primitives with explicit names, state, focus behaviour, and keyboard support. Retain the user's Pleco tone palette; use labels and structure rather than colour alone for learning state. Preserve legible Chinese text with generous line height and controlled measure. Prefer a single clear primary action per task, accurate progress, recoverable errors, and no destructive reset without an appropriate recovery path.

Target WCAG 2.2 AA. A 44px touch target is the preferred ergonomic target for main controls, rather than a blanket assertion about every inline dictionary token. Verify custom word hit areas do not overlap into ambiguous adjacent targets. Reduced motion must include transitions as well as animations. Source-video burned-in text cannot be hidden by the app and must not be mistaken for an application answer-visibility defect.

## Validation record

The implementation branch contains meaningful regression coverage for scoring, task visibility, repeated cloze targets, event acknowledgement/retries, spaced review, cache/index updates, and timing. The final run on 18 October 2026 passed 105 backend tests, 25 frontend unit tests, 26 Chromium browser checks, and the TypeScript/Vite production build. Changed Python files pass Ruff core correctness checks (E4/E7/E9/F); repository-wide broader lint has pre-existing diagnostics outside this change. Backend tests emit an existing Starlette/httpx deprecation warning.

Browser checks include all nine main page accessibility scans plus an open dictionary-dialog scan with no violations under the selected WCAG A/AA tags, repeated-target masking, safe grade retries, audio/video task modes, keyboard focus restoration, four Watch viewport widths, and mobile layouts on eight other routes. These automated results do not certify complete WCAG conformance.

Optional Chinese font stylesheets now load only when selected. The initial CSS build output fell from approximately 350.8 kB to 110.3 kB, about 69% smaller. This measures stylesheet output, not total page load time. Real media playback/transcription, Anki Desktop export, Safari, 200% zoom, and manual assistive-technology testing still need their release gates.

## Browser acceptance matrix

- Viewports: 320px, 390px, 768px, 1440px; 200% zoom; short landscape; fullscreen.
- Routes: empty and populated Home/Library; Watch video/audio in each mode; Review with/without source/definition; Search results/error; Saved export preflight; Settings/Admin missing dependencies.
- Input: keyboard-only navigation, Chinese IME Enter, pointer/touch, reduced motion; focus visible and restored after dialogs.
- Failures: offline event flush, HTTP 503, refused beacon, failed playback, missing transcript, concurrent review, ambiguous network response, quota-limited local storage.
- Learning: no app-controlled text in an unassisted attempt; deliberate hints labelled; dictionary alternatives not asserted as a selected contextual meaning; activity not asserted as comprehension.

## Reviewed screenshots

These are real application screenshots using synthetic test media and fixture learning data, not a separate design mock-up.

![Desktop listening mode with text hidden](screenshots/listening-desktop.png)

![Mobile review with dictionary feedback and clear grading actions](screenshots/review-mobile.png)

![Mobile library with semantic filters and vocabulary familiarity labels](screenshots/library-mobile.png)

## Reproduce the checks

```sh
cd web
npm ci
npx playwright install chromium
npm test
npm run build
npm run test:ui
```

From `server/`, run `uv run pytest` with Python 3.12 and the development dependencies installed. The browser tests intercept API calls, so they exercise production UI behaviour deterministically; the backend suite separately exercises the actual SQLite/API logic. The included tiny MP4 is a generated colour-and-tone fixture with no personal or third-party media.

The initial UI delivery introduced no database schema migration. Later additive migrations are documented below. Existing graduated items are preserved; the revised due/spacing policy applies to subsequent submissions. Full script-equivalent dictation, contextual pronunciation, and sense-specific knowledge remain explicitly scheduled in the roadmap.

## Canonical forms / selected readings follow-up

The next delivery adds a radio choice per dictionary definition, separate automatic-context reading copy, selected reading/meaning on saved cards, and an explicit dictation script policy selector. The existing React/Radix dialog retains focus trapping and a scrollable body. A 390px production-UI inspection confirmed readable choices and reachable footer actions; see [selected meaning](screenshots/selected-meaning-mobile.png).

The current combined validation is 121 backend tests, 26 frontend unit tests, and 29 Chromium checks. The added interaction checks verify permitted script entry, exact meaning/reading/occurrence save payload, and selecting the second repeated source word while excluding ruby. The existing dictionary-dialog accessibility scan also covers the new radio choices. See [migration and language limitations](MANDARIN_REPRESENTATION.md).

## Source corrections and recovery follow-up

The Watch transcript now offers “Correct line” and a Radix dialog for Chinese text, English meaning, source-clock timing, per-word reading/meaning, original source, and revision history. Reset and restore create new history entries. A conflict preserves the draft until the learner reloads. Save/restore/reset actions have 44px minimum height; the dialog uses a scrollable body, retains reachable footer actions, and restores focus to the line action.

A collapsible source panel shows available Chinese/English subtitle tracks, preserves explicit choices, reports queued work, and offers playback repair. Transcript provenance distinguishes corrected/source/estimated timing; interpolated timings are identified. Checked dictation reports when its source changed and retains its original target/score. [Mobile editor screenshot](screenshots/correction-editor-mobile.png) was inspected at 390px. The screenshot is from the production React app with synthetic API/media fixtures, with history expanded and the form scrolled.

Combined validation now passes 151 backend tests, 26 frontend unit tests, and 33 Chromium checks. The new editor has a passing WCAG-tagged axe scan, focus restoration, correction/reset/restore, conflict recovery, live transcript refresh, source-selection/repair, and historical dictation checks. Automated scans do not establish full WCAG compliance. Manual screen-reader, Safari/iPad, 200% zoom, real-library profiling, live Anki, and the running Caddy stack remain unverified. See [source reliability delivery](SOURCE_RELIABILITY.md).


## Learner evidence and recommendation follow-up

Home now separates indexed library words from recorded encounters, labels indexed counts, includes common beginner words, and shows task-specific practice evidence. Optional goal/level/script/title-interest preferences use labelled native selects and explicit save/error states. Recommendations show vocabulary familiarity, unfamiliar occurrences per minute, expandable reasons, subtitle pace/source warnings, and the ignored-word denominator. The Word page separates independent encounters from legacy counters and shows dated self-graded retrieval scoped to selected reading/meaning. Pronunciation/production remain unassessed. Watch adds optional task-specific difficulty feedback with save/retry and pressed-state feedback. Shared keyboard outlines now cover selects and textareas.

The existing React 19/Tailwind/Radix/TanStack stack was retained. Browser inspection covered the actual production build at 390px with synthetic fixtures, including preference saves, library/encountered empty states, expanded explanations, evidence limits, and failed difficulty submission/retry. WCAG-tagged axe checks on the expanded new surfaces, labels, touch targets, and horizontal-overflow checks pass. Screenshot capture resets scroll/focus after axe to avoid recording fixed navigation at an intermediate scroll position.

- [Learning preferences on mobile](screenshots/learner-profile-mobile.png)
- [Recommendations and practice evidence on mobile](screenshots/recommendations-mobile.png)
- [Selected reading/meaning evidence on mobile](screenshots/word-evidence-mobile.png)

Combined validation: **165 backend tests, 26 frontend unit tests, and 37 Chromium checks pass**, with TypeScript/Vite build and core Python correctness/whitespace checks. A synthetic local service benchmark over 250 items / 40,000 sentences / 320,000 token occurrences returned recommendations in median 164 ms and dashboard aggregation in 74 ms. This is not end-to-end latency or representative-hardware certification. [Migration, evidence policy, recommendation formulas, and remaining learning/validation gates](LEARNER_EVIDENCE.md) are documented separately. Manual screen-reader, Safari/iPad, zoom, real-library CPU/GPU work, live Anki and Caddy runtime checks remain open.


## Guided scenes, constructions and selective mining follow-up

Watch can start a short Read/Listen scene. The new lazy-loaded scene route has a semantic step list/progress, source-bound media controls, keyboard-focus heading updates, named hint/replay actions, explicit reflection versus local-key feedback, stale-source handling, and revision-safe retry/reload. The source/answer editor appears only in supported study steps. `/practice` offers resumable/due scenes, labelled construction navigation, contrast examples, candidate-library links, interpretation feedback, report/suspend/restore, and version conflicts. Home exposes the scene inbox.

Mining starts with a few candidates and an explicit reading/meaning choice; over-budget saves require a deliberate local UI choice. The session summary no longer preselects all unknowns or closes before requests succeed. Failed choices remain retryable and confirmed saves are retained. Settings distinguishes display-default reset from learner/intake preferences. Saved has Active/Suspended views with named, reversible actions and focus moved to the destination filter. Context and review rung remain visible after resume.

The existing dictionary popup had a transient contrast failure during its opacity fade. The fade was removed while retaining movement and reduced-motion support; its accessibility test waits for animation completion before scanning. An actual video replay/seek check verifies that scene bounds do not create a same-position seek loop.

- [Guided listening with the transcript hidden](screenshots/guided-listening-mobile.png)
- [Scene meaning check and suspension recovery](screenshots/scene-meaning-mobile.png)
- [Mandarin construction practice and explanations](screenshots/construction-practice-mobile.png)

Validation passes **188 backend tests, 26 frontend unit tests and 45 Chromium checks**, with production build and changed application Python/new-test correctness/whitespace checks. The expanded scenes/meaning/construction and populated Saved views have passing WCAG-tagged axe scans and mobile overflow checks at 320/390px. Screenshots were visually inspected. Browser APIs/media are synthetic fixtures; separate backend tests exercise real SQLite/API behavior. Independent teacher/learner review of exercise language, manual screen-reader/zoom/Safari/iPad, real media/hardware/large-library work, live Anki and Caddy runtime checks remain open. See [guided learning details and limits](GUIDED_LEARNING.md).
