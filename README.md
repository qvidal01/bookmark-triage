# bookmark-triage

Sort years of browser bookmarks from multiple profiles into clean, importable sets —
dedupe, dead-link check, rule-based bucketing, and a follow-up queue for the ones
only a human can decide.

Built for the "I have two Chrome profiles and hundreds of bookmarks I never got back to"
problem, but the buckets are just rules — the same pipeline separates any two concerns
(business vs personal, project A vs project B).

## Pipeline

```
Chrome/Firefox HTML export(s) in data/
        │ parse      normalize + fold duplicates (URL canonicalization: strip www,
        │            tracking params, fragments, trailing slash)
        │ check      probe every unique URL: alive / auth-gated / dead / timeout
        │ classify   rules.json buckets by folder segment, domain, keyword
        │ build      importable Netscape HTML per bucket + report.md, review.md, dead.md
        ▼
out/import_<bucket>.html  ← import back into the right Chrome profile
```

## Usage

```bash
# 1. Chrome → Bookmark Manager → ⋮ → Export bookmarks → save into data/
python3 scripts/triage.py parse data/*.html
python3 scripts/triage.py check            # ~2 min for ~500 urls; re-runs skip checked
python3 scripts/triage.py classify         # edit rules.json, re-run freely
python3 scripts/triage.py build
```

Outputs (all in `out/`, gitignored):

- `import_business.html`, `import_personal.html`, `import_homelab.html`, … — import each
  into the matching profile (Bookmark Manager → ⋮ → Import). Folder structure preserved.
- `review.md` — checklist of bookmarks no rule could place; click, decide, annotate.
- `dead.md` — unreachable links, excluded from imports (verify before mourning:
  `auth`-gated sites like LinkedIn/Cloudflare-fronted pages are *kept*, not here).
- `report.md` — counts summary.

## Re-bucketing for a different split

Copy `rules.json`, change the bucket names and folder/domain/keyword lists, re-run
`classify` + `build`. First matching bucket wins; unmatched → `review` (or set
`default`). Matching is: exact folder-path segment → domain suffix → keyword in
folder+title.

## Notes

- Stdlib only, no dependencies. macOS/Linux.
- `data/` and `out/` are gitignored: bookmark URLs can embed tokens/session params —
  keep them off remotes.
- Liveness probe sends no credentials and disables cert verification (dead-or-alive
  only, not a security check). 401/403/405/429 count as `auth` (reachable, bot-gated),
  not dead.
- Chrome profiles that sync from Google keep empty local bookmark files until synced on
  this machine — always work from HTML exports, not `~/Library/.../Chrome/*/Bookmarks`.

## Roadmap / ideas

- Phase 2 — account separation: cross-reference Bitwarden vaults (two `bw` sessions via
  separate `BITWARDENCLI_APPDATA_DIR`s) to flag sites whose login lives in the personal
  vault but belong to the business bucket → migration checklist.
- Optional LLM pass (Ollama) to auto-suggest buckets for the `review` pile from page
  titles/content instead of leaving all of it to the human.
- Productization: "multiple profiles, thousands of bookmarks" is a common pain —
  the pipeline is already generic; a web wrapper + agent-driven review is the SKU.
