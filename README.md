# Immersion (沉浸)

Self-hosted Mandarin immersion app: local video (and, in Phase 2, podcasts) with
interactive multi-track subtitles wired to a persistent learner model and an
Anki bridge. Successor to the static-site podcast reader; plan and rationale in
`~/.claude/plans/review-the-doc-in-splendid-steele.md`.

## Layout

- `server/` — FastAPI + SQLite (WAL) + Alembic. `src/app/lingua/` is the ported
  podreader NLP core (HanLP segmentation + CC-CEDICT reconcile, pypinyin,
  OpenCC traditional). `src/app/ingest/` scans media roots, parses subtitles
  (pysubs2, GB18030/Big5 sniffing), merges cues into sentence segments, aligns
  zh↔en by timestamp overlap, and links every token to a canonical lexeme.
  A single worker process (`immersion worker`) runs all jobs — which also
  serializes heavy model work.
- `web/` — React 19 + TypeScript + Vite + Tailwind SPA. Custom `<video>`
  player: tone-colored tappable subtitles (Pleco palette), virtualized
  transcript panel, sentence stepping/loop/pause-after, per-sentence EN and
  pinyin reveal, traditional toggle, gloss sheet with save/known/ignore.
- `data/` — CC-CEDICT and HSK 3.0 word list, imported into the DB at first boot.
- `deploy/` — Caddyfile (SPA + `/media/*` file_server + `/api` proxy on :8736)
  and systemd user units.

## Run (dev)

```sh
cd server && uv run immersion api      # http://127.0.0.1:8770
cd server && uv run immersion worker   # job queue (scans, analysis, Anki)
cd web && npm run dev                  # http://localhost:5173 (proxies /api, /media)
```

## Run (prod)

```sh
cd web && npm run build
cp deploy/immersion-*.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now immersion-api immersion-worker immersion-web
# optional hourly rescan: systemctl --user enable --now immersion-scan.timer
```

App at `http://<host>:8736` (Tailscale is the auth boundary — no app auth).

## Admin

- Add a media root: Admin page (or `uv run immersion add-root lfc /mnt/lfc --include 'Level */*'`).
  Include globs use fnmatch against root-relative paths.
- Anki known-word import: Admin → "Import known words from Anki" (Anki desktop
  must be open with AnkiConnect). Card interval ≥21d ⇒ known, 1–20d ⇒ learning;
  manual marks always win over sync.
- Jobs/errors: Admin page (the `job` table is the dashboard).

## Tests

```sh
cd server && uv run pytest
```

## Keyboard (player)

Space play/pause · ←/→ ±5s · ↑/↓ prev/next sentence · R replay · L loop ·
S subtitle mode (off/中/中+EN) · T reveal EN · P pinyin · D define ·
A save sentence · M pause-after-sentence · [ ] speed · Esc close
