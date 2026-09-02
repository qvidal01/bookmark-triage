---
runbook: true
repo: bookmark-triage
status: active
type: tool
updated: 2026-07-29
health: unknown
deploy: not deployed
next: import the generated bookmark sets, then review and classify the 59 undecided links
---

# bookmark-triage — Runbook

## Purpose

Merge Chrome or Firefox HTML bookmark exports, normalize and deduplicate URLs, check
link liveness, classify bookmarks with repository rules, and build clean HTML imports
plus review and dead-link reports.

## Stack

- Python 3 standard library only; no external dependencies.
- `scripts/triage.py` provides the `parse`, `check`, `classify`, and `build` stages.
- `rules.json` defines ordered folder, domain, and keyword bucketing rules.
- `data/` holds raw exports and `out/` holds generated results; both are gitignored.
- `out/inventory.json` is the inventory of record.

## Where it runs

This is a local macOS/Linux tool with no deploy target. Raw bookmark data currently
exists only on qmac; another machine needs fresh HTML exports before data work.

## Run / deploy

Export bookmarks as HTML into `data/`, then run:

```bash
python3 scripts/triage.py parse data/*.html
python3 scripts/triage.py check
python3 scripts/triage.py classify
python3 scripts/triage.py build
```

To force all URLs to be checked again:

```bash
python3 scripts/triage.py check --all
```

After editing `rules.json`, rebuilding is cheap and idempotent:

```bash
python3 scripts/triage.py classify
python3 scripts/triage.py build
```

Import `out/import_<bucket>.html` through the browser's bookmark manager. Never commit
`data/`, `out/`, exports, or `inventory.json`; bookmark URLs may contain sensitive
parameters.

## Health & recovery

Health is unknown because the repository defines no deployed service or health check.
Re-run the pipeline to regenerate outputs. The liveness probe sends no credentials;
authentication and bot-gated responses are retained, while dead links are excluded
from imports and listed in `out/dead.md`. Verify dead links before removing them.

## Current status

The latest commits on 2026-07-26 created the four-stage pipeline, added initial
classification rules, and added a curl second opinion so public-host timeouts are
kept as bot-gated while private-IP timeouts are treated as stale. The latest recorded
run processed 1,094 bookmarks into 762 unique URLs and built business, homelab,
personal, followup, and review outputs. Importing the generated HTML and resolving
the 59-item review queue remain user-side work.

## Links

- Repository: `qvidal01/bookmark-triage` (GitHub).
- Operational handoff: `docs/NEXT_SESSION.md`.
- No Odoo project exists for this repository.
