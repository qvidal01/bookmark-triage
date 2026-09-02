ROLE: Senior Python tooling engineer continuing bookmark-triage (repo:
~/projects/bookmark-triage, GitHub qvidal01/bookmark-triage). Authorized to
operate autonomously (commit, push) with the safety rails below. Work evidence-first.

CONTEXT: Stdlib-only CLI (scripts/triage.py: parse/check/classify/build) that merges
Chrome bookmark exports from multiple profiles, dedupes, liveness-checks, buckets via
rules.json, and emits importable Netscape HTML per bucket. No deploy target — local
tool. Buckets are generic; the same pipeline is meant to be reused for other splits
(e.g. SBA vs Faron) and has productization potential.
Safety rails: data/ and out/ are gitignored ON PURPOSE (bookmark URLs can embed
tokens/session params) — never commit or push exports or inventory.json. Liveness
probes send no credentials. Raw data exists ONLY on qmac — on any other machine, ask
for fresh exports before doing data work.

WHERE THINGS STAND (as of 2026-07-26):
- Both profiles processed: 1,094 bookmarks -> 762 unique (332 cross-profile dupes),
  final statuses alive 638 / gated 90 / dead+stale 34.
- Buckets built in out/: business 197, homelab 195, personal 158, followup 119,
  review 59 (+ review.md, dead.md, report.md).
- Liveness has a curl second-opinion pass: public-host timeouts = bot-gated (kept),
  private-IP timeouts = stale old-network links (dead). Committed in 69b54de.
- rules.json encodes Q's verdicts so far: JW/Jobs/Banking->personal, CMMC/Education->
  business, Tech->homelab, old review/ folder->followup, mercury.com->business.
- Tree clean, master == origin/master. No Odoo project for this repo (none created).
- USER-SIDE PENDING: Q has NOT yet imported the out/import_*.html files into Chrome,
  and has NOT walked out/review.md (59 undecided links).

NEXT STEPS (in order):
1. Ask Q whether the imports landed; if yes, confirm the old duplicated folders were
   deleted in both profiles. Gate: Q confirms both profiles show the new folder sets.
2. Walk out/review.md with Q (59 items); encode every verdict into rules.json,
   re-run classify+build, commit rules. Gate: review bucket count == 0.
3. Distill the followup bucket (119 links; clusters: Odoo-headless Next.js/OWL,
   Canva<->Odoo integration, AI coding agents) into an Obsidian research note via
   pkb-vault MCP. Gate: note exists in the PKB vault and is linked from a session log.
4. Phase 2 — Bitwarden separation: two bw sessions (separate BITWARDENCLI_APPDATA_DIR
   per account: one business, one personal; use /bw-session),
   cross-reference vault item URIs against business/personal buckets, emit a
   wrong-vault migration checklist. Gate: checklist doc lists every login whose vault
   doesn't match its bucket, with zero fabricated entries.
5. Optional: Ollama pass (via ollama MCP) to auto-suggest buckets for future review
   piles; and decide whether to productize (web wrapper + agent review flow).

FIRST: read CLAUDE.md + README.md + memory project_bookmark_triage.md before acting.
