# Persistent Anki handoff and configurable export

This phase implements A02/A04, advances A01/U06, and replaces the application's transient export dialog with a recoverable handoff. It retains React 19, TypeScript, Tailwind, Radix, TanStack Query, FastAPI and SQLite. It does not change Anki templates, create note types, or infer learning success from exporting.

## Configure an existing deck and note type

Settings → **Anki export setup** reads AnkiConnect's version, decks, note types and selected model fields. The user chooses an existing destination and maps canonical app fields to their actual Anki field names. The personal `Xiehanzi Mandarin` default is optional. Mappings support simplified/traditional text and source sentences, selected reading/meaning, sentence pinyin/translation, source audio and an optional still. Different source fields cannot overwrite one destination field. A Chinese text field and Meaning are required; the model's first field must receive an identifier or available Chinese text. Cards with a selected reading require a Pinyin mapping. Missing per-card Chinese text blocks that card rather than silently substituting another script.

Preflight identifies an unavailable AnkiConnect service, missing deck/model/fields, unmapped first field, and unreviewed templates. New-model choices retain compatible mappings and suggest Front/Back for a Basic model; they reset template confirmation. The user must review the actual card fronts and backs in Anki. Mapping fields cannot establish whether a note tests reading, listening, production or meaning. The app never modifies those templates. Configuration is validated again when saved, submitted and processed. Previously submitted work retains its reviewed configuration when Settings changes.

Online word TTS is off by default and its remote/synthetic nature is visible. Selected or locally corrected readings never receive generic substitute word audio. Source clips remain separate from synthetic audio. ffmpeg operations have a 90-second timeout; optional TTS has a 20-second timeout, and AnkiConnect has bounded connection/read waits. One worker still handles heavy work; an active transcription cannot yet be preempted. Export jobs receive higher waiting priority, not a guarantee of immediate execution.

## Completed reviews stay visible

`/exports`, linked from Home, Saved and review completion, lists completed local reviews awaiting handoff. **Ready / Deferred** and named Defer/Restore actions preserve card IDs, selected readings/meanings, contexts and review progress. Deferred, suspended and already linked cards are excluded from Home's awaiting-handoff count. Deferral is an inbox choice, not a new learning grade. Cards in pending/unconfirmed delivery cannot be deferred through this screen.

Both the inbox and export history use SQL cursor pagination; related attempts/jobs are fetched in batches. History retains reviewed fields, destination, source revision, exact export tag, warnings, errors and confirmed note IDs. The UI shows 20 submissions per page. A direct **View export** link includes an older unresolved attempt even when it falls outside the recent page and moves focus to that result. The server identifies superseded attempts so old history does not offer an inappropriate retry.

Saved still allows deliberate earlier export of up to 50 selected cards. This does not require or imply local review graduation. Review completion remains task-scoped self-report evidence; exporting never marks a whole lexeme Known or creates pronunciation evidence. Existing Anki evidence import/reconciliation is unchanged and remains A03 work.

## Review and submit

The scrollable Radix dialog keeps named footer actions reachable on a narrow screen, shows source Chinese/reading/translation, allows a meaning edit, and gives an explicit choice about available source media. Similar notes in the configured Chinese field are surfaced and initially excluded. Adding another note requires a deliberate override. Duplicate handling does not append random characters to a Chinese card front. Scalar text is HTML-escaped for Anki; media fields contain only the app-generated markup.

A submission freezes the reviewed text/reading/meaning, source revision, effective timing, source fingerprint/file signature and destination profile. Only Meaning is editable in this preview. Source/profile changes before acceptance return a refresh conflict. The worker rechecks the current source, including after media preparation, and refuses stale source/reading/timing. It never silently rebuilds submitted fields from a changed sentence. Missing source audio leaves an explicit text-only warning rather than fabricated audio. Source-language and automatic pinyin correctness still need their existing linguistic validation gates.

Before sending, the browser stores an independent reminder containing the exact UUID and payload. If storage is unavailable/full, nothing is sent and the editable preview remains. If the response is lost, **Retry same submission** works after close/reload and reuses the original request. A previously accepted UUID returns its original job, including when Anki is now offline. SQLite writer serialization and card-level active/link checks prevent concurrent requests from queuing the same card twice. A reused UUID with different content is rejected.

Closing discards unsubmitted preview edits. Accepted work continues in the worker and remains accessible in the inbox. Confirmed per-note outcomes live in structured rows, so a truncated `Job.progress` summary cannot lose results or break JSON parsing. Partial failure keeps successful links and individual errors visible. A dismissed browser reminder does not cancel an accepted server job.

## A lost add-note reply is not a confirmed failure

Every card's attempts share a random, persisted `immersion-id-…` tag. Immediately before the external add-note mutation the worker commits an **uncertain** state. The new note receives that tag. A crash after the external add, a lost network reply, or a failed local confirmation can therefore be reconciled by tag without adding another note. Confirmed links and the final attempt update commit together.

A restarted worker first checks the tag. If it finds one note, it records the confirmation; if multiple notes carry the tag it asks the user to resolve the copies. When an uncertain result has no visible tagged note, it remains unconfirmed and does not automatically add again. **Check Anki** only reconciles. An additional add requires an explicit checked statement that the user inspected Anki and found no tagged note. The worker checks once more before adding. Retry UUIDs are idempotent, and superseded attempts cannot be restarted through the new endpoint.

This protects the ambiguous-response window; it is not an unconditional exactly-once guarantee across user-modified collections. Removing/copying export tags, an outstanding remote operation, or explicitly authorizing another add can affect reconciliation. Duplicate warnings examine the mapped Chinese field; they do not certify equivalence across every external model, field, script or sense. Exported-note deletion, lapses, suspension and changed templates still need A03 reconciliation and live collection checks.

Deleting a local saved card preserves its export snapshot and original ID, and clears the live foreign key. Reused SQLite IDs cannot inherit the old export key/link. Confirmed Anki notes are not deleted by local removal. Anki's remote collection is modified only by explicit submitted exports; tests use doubles and never contact a personal collection.

## Migration and compatibility

Additive migration `f6a8b0c2d4e6` follows `e5f7a9b1c3d5`. It adds `saved_item.export_deferred`, structured `export_attempt` records and lookup indexes. The existing online SQLite backup-and-restore verification gate runs before upgrade. Migration tests preserve original saved cards, completed review state, pass counts and events. Existing links/import evidence remain intact. New history describes new durable submissions; it does not invent detailed snapshots for legacy exports.

The worker now accepts durable export IDs. Legacy queued payloads fail with a fresh-preview instruction rather than using the older ambiguous export path. The generic job endpoint cannot inject a legacy export payload. Review old failed jobs in Admin and re-preview those cards after checking Anki. Old helper functions remain for regression coverage, but current API routes and workers do not submit through them.

## Performance evidence

A correlated exported-link exclusion lacked a supporting index. The migration adds saved-card inbox, graduated-review and Anki-link lookup indexes. On the same synthetic managed-Linux fixture with 10,000 completed cards, 2,000 linked notes and 20 measured runs after a warmup, local handler timings were:

| Handler | Before p50 / p95 | After p50 / p95 |
| --- | --- | --- |
| 30-card inbox, including counts | 340.49 / 342.88 ms | 2.97 / 3.15 ms |
| 20-submission history | 0.78 / 0.90 ms | 0.77 / 0.88 ms |

These measure SQLite and handler execution, not HTTP, browser route usability, ffmpeg, real Anki Desktop or the user's hardware. [Raw environment/results](benchmarks/handoff-10000-cards.json) and `server/scripts/benchmark_handoff.py` make the fixture reproducible. From an installed server environment, run `uv run python scripts/benchmark_handoff.py --cards 10000 --runs 20`. It creates/deletes a temporary synthetic database and does not open personal data or Anki. Queue/library/alignment optimization and representative local CPU/GPU workloads remain open.

## Verification record and limits

**245 backend tests and 30 frontend unit tests pass**, along with the TypeScript/Vite production build, changed Python core correctness lint and whitespace checks. Coverage includes configuration/schema/first-field validation, both-script mappings, selected-reading preservation, duplicate permission without corrupting fronts, markup escaping, source/file edits before and during processing, concurrent/idempotent submissions, lost add replies, crash-after-add recovery, explicit uncertain retry, removed/reused IDs, inbox deferral/pagination/old-attempt reachability, complete results beyond truncated job progress, additive migration and verified backups. Browser reminder tests preserve exact independent requests, ignore damaged entries and surface quota failures before sending.

An earlier production-build Chromium pass completed **62 checks**, including settings/custom mapping, defer/reload/restore, lost-submission replay, unconfirmed reconciliation and deliberate retry, missing note type, duplicate override, storage failure, 320px dialog footer reachability, mobile overflow and WCAG-tagged axe scans. Inspection identified and removed shared-dialog text opacity fades that could transiently lower contrast. Existing correction, learning, media and recording checks continued to pass.

The final pass adds one long-sentence/mobile recovery-focus check (63 checks total), plus small action-label/layout/storage-message refinements. That rerun could not start: the current sandbox denies both a local listening socket and Chromium startup (`EPERM`). A temporary no-server test mode encountered the same Chromium restriction and was removed. Consequently the last UI refinements and the added layout check have build/unit verification, not a completed final browser pass. New screenshots were not retained for this phase, and no new visual screenshot inspection is claimed. Rerun `npm run build && npm run test:ui` in an environment that permits Chromium and the local preview server. The previous 62-check pass does not establish full WCAG conformance.

Live Anki templates/collection/audio, manual screen-reader and zoom checks, Safari/iPad, real media/hardware, Anki evidence reconciliation and delayed learning transfer remain unverified. No personal production database or running local deployment was changed.
