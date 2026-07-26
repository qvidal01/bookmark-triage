# bookmark-triage

See README.md — 4-stage pipeline in scripts/triage.py (parse/check/classify/build), buckets in rules.json.
Raw exports live in data/ (gitignored), results in out/ (gitignored). Inventory of record: out/inventory.json.
Re-runs are cheap and idempotent; `check` skips already-probed URLs unless --all.
