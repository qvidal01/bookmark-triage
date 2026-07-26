#!/usr/bin/env python3
"""bookmark-triage: parse, dedupe, liveness-check, and classify browser bookmark exports.

Subcommands:
  parse    data/*.html  -> out/inventory.json (normalized records)
  check    out/inventory.json -> liveness status per unique URL
  classify apply bucket rules (rules.json) -> business / personal / homelab / followup / review
  build    emit importable Netscape HTML per bucket + report.md + review.md

Stdlib only. Re-runnable: each stage reads/writes out/inventory.json.
"""
import argparse
import concurrent.futures
import html
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INV = os.path.join(ROOT, "out", "inventory.json")
RULES = os.path.join(ROOT, "rules.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

TRACKING_PARAMS = re.compile(
    r"^(utm_|gclid|fbclid|igshid|mc_cid|mc_eid|ref_src|ref_url|_hs|vero_|yclid|msclkid)")


# ---------------------------------------------------------------- parse

class NetscapeParser(HTMLParser):
    """Chrome/Firefox 'Netscape bookmark file' parser. Tracks folder path via DL nesting."""

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.stack = []          # folder path
        self.records = []
        self._h3 = False
        self._a = None
        self._pending_folder = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "h3":
            self._h3 = True
            self._pending_folder = {"name": "", "add_date": a.get("add_date")}
        elif tag == "dl":
            if self._pending_folder is not None:
                self.stack.append(self._pending_folder["name"])
                self._pending_folder = None
            else:
                self.stack.append(None)  # root DL
        elif tag == "a":
            self._a = {"url": a.get("href", ""), "title": "",
                       "add_date": a.get("add_date"), "icon": None}

    def handle_endtag(self, tag):
        if tag == "h3":
            self._h3 = False
        elif tag == "dl":
            if self.stack:
                self.stack.pop()
        elif tag == "a" and self._a:
            folder = [f for f in self.stack if f]
            self._a["folder"] = "/".join(folder)
            self._a["source"] = self.source
            if self._a["url"].startswith(("http://", "https://")):
                self.records.append(self._a)
            self._a = None

    def handle_data(self, data):
        if self._h3 and self._pending_folder is not None:
            self._pending_folder["name"] += data.strip()
        elif self._a is not None:
            self._a["title"] += data


def norm_url(url):
    """Canonical form for dedupe: strip www/fragment/tracking params/trailing slash."""
    try:
        p = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = p.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
         if not TRACKING_PARAMS.match(k.lower())]
    path = p.path.rstrip("/")
    return urllib.parse.urlunsplit(
        ("https", host, path, urllib.parse.urlencode(q), ""))


def cmd_parse(args):
    records = []
    for f in sorted(args.files):
        src = os.path.splitext(os.path.basename(f))[0]
        p = NetscapeParser(src)
        with open(f, encoding="utf-8", errors="replace") as fh:
            p.feed(fh.read())
        print(f"{src}: {len(p.records)} bookmarks")
        records.extend(p.records)

    # dedupe: group by normalized URL, keep earliest add_date; remember all folder homes
    by_key = {}
    for r in records:
        r["key"] = norm_url(r["url"])
        r["title"] = " ".join(r["title"].split())
        if r["key"] not in by_key:
            by_key[r["key"]] = {**r, "dupes": []}
        else:
            keep = by_key[r["key"]]
            keep["dupes"].append({"folder": r["folder"], "source": r["source"],
                                  "title": r["title"]})
            if (r.get("add_date") or "9" * 12) < (keep.get("add_date") or "9" * 12):
                keep.update({k: r[k] for k in ("url", "title", "add_date", "folder", "source")})
    inv = sorted(by_key.values(), key=lambda r: (r["folder"], r["title"].lower()))
    os.makedirs(os.path.dirname(INV), exist_ok=True)
    json.dump(inv, open(INV, "w"), indent=1)
    ndupes = len(records) - len(inv)
    print(f"total {len(records)} -> {len(inv)} unique ({ndupes} duplicates folded)")


# ---------------------------------------------------------------- check

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # liveness only; we never send credentials


def probe(url, timeout=15):
    """Return (status, detail). status: alive | auth | dead | timeout | error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            return "alive", f"{resp.status} {resp.url[:120]}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 405, 429, 999):
            return "auth", str(e.code)      # reachable but gated/bot-blocked
        if e.code in (404, 410):
            return "dead", str(e.code)
        return "dead" if e.code >= 500 else "auth", str(e.code)
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))
        if "timed out" in reason.lower():
            return "timeout", reason[:120]
        return "dead", reason[:120]
    except Exception as e:  # noqa: BLE001
        return "error", f"{type(e).__name__}: {e}"[:120]


def is_private_host(url):
    """Private/LAN targets: RFC1918 IP literals, localhost, .local/.lan, bare names."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    try:
        import ipaddress
        return ipaddress.ip_address(host).is_private
    except ValueError:
        pass
    return (host in ("localhost",) or host.endswith((".local", ".lan", ".home"))
            or "." not in host)


def curl_fallback(url, timeout=25):
    """Second opinion via curl (different TLS/client fingerprint than urllib)."""
    import subprocess
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", str(timeout),
             "-L", "-A", UA, url], capture_output=True, text=True, timeout=timeout + 5)
        code = out.stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    if code.startswith(("2", "3")):
        return "alive", f"curl:{code}"
    if code in ("401", "403", "405", "429", "999"):
        return "auth", f"curl:{code}"
    if code == "000":
        # curl couldn't connect either; public host stalling both clients = bot wall
        return ("auth", "curl:000 bot-gated") if not is_private_host(url) else None
    return None


def cmd_check(args):
    inv = json.load(open(INV))
    todo = [r for r in inv if args.all or not r.get("status")]
    print(f"probing {len(todo)} urls ({args.workers} workers)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(probe, r["url"]): r for r in todo}
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            r = futs[fut]
            r["status"], r["status_detail"] = fut.result()
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}")
    # second pass: timeouts/errors on PUBLIC hosts get a curl second opinion —
    # big-brand sites stall non-browser clients; private IPs that time out are stale
    retry = [r for r in todo if r["status"] in ("timeout", "error")
             and not is_private_host(r["url"])]
    if retry:
        print(f"curl second-opinion on {len(retry)} public timeouts...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(curl_fallback, r["url"]): r for r in retry}
            for fut in concurrent.futures.as_completed(futs):
                res = fut.result()
                if res:
                    futs[fut]["status"], futs[fut]["status_detail"] = res
    json.dump(inv, open(INV, "w"), indent=1)
    counts = {}
    for r in inv:
        counts[r.get("status", "unchecked")] = counts.get(r.get("status", "unchecked"), 0) + 1
    print(json.dumps(counts, indent=1))


# ---------------------------------------------------------------- classify

def load_rules():
    return json.load(open(RULES))


def classify_one(r, rules):
    folder = r["folder"].lower()
    host = (urllib.parse.urlsplit(r["url"]).hostname or "").lower()
    text = folder + " " + r["title"].lower()
    for bucket, spec in rules["buckets"].items():
        for kw in spec.get("folders", []):
            # match whole folder-path segments so 'ai' doesn't hit 'maintenance'
            if kw.lower() in [seg.lower() for seg in r["folder"].split("/")]:
                return bucket, f"folder:{kw}"
        for dom in spec.get("domains", []):
            if host == dom or host.endswith("." + dom):
                return bucket, f"domain:{dom}"
        for kw in spec.get("keywords", []):
            if kw.lower() in text:
                return bucket, f"keyword:{kw}"
    return rules.get("default", "review"), "no-rule"


def cmd_classify(args):
    inv = json.load(open(INV))
    rules = load_rules()
    counts = {}
    for r in inv:
        r["bucket"], r["bucket_reason"] = classify_one(r, rules)
        if r.get("status") in ("dead", "timeout", "error"):
            pass  # keep bucket; build stage separates dead links out
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    json.dump(inv, open(INV, "w"), indent=1)
    print(json.dumps(counts, indent=1))


# ---------------------------------------------------------------- build

def netscape(records, title):
    """Emit an importable Netscape bookmark file preserving folder paths."""
    lines = ['<!DOCTYPE NETSCAPE-Bookmark-file-1>',
             '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
             f'<TITLE>{html.escape(title)}</TITLE>',
             f'<H1>{html.escape(title)}</H1>', '<DL><p>']
    cur = []

    def close_to(target):
        while cur and cur != target[:len(cur)]:
            cur.pop()
            lines.append("    " * (len(cur) + 1) + "</DL><p>")

    for r in sorted(records, key=lambda x: (x["folder"], x["title"].lower())):
        path = [p for p in r["folder"].split("/") if p]
        close_to(path)
        while len(cur) < len(path):
            seg = path[len(cur)]
            ind = "    " * (len(cur) + 1)
            lines.append(f'{ind}<DT><H3>{html.escape(seg)}</H3>')
            lines.append(f'{ind}<DL><p>')
            cur.append(seg)
        ind = "    " * (len(cur) + 1)
        ad = f' ADD_DATE="{r["add_date"]}"' if r.get("add_date") else ""
        lines.append(f'{ind}<DT><A HREF="{html.escape(r["url"], quote=True)}"{ad}>'
                     f'{html.escape(r["title"] or r["url"])}</A>')
    close_to([])
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def cmd_build(args):
    inv = json.load(open(INV))
    out = os.path.join(ROOT, "out")
    live = [r for r in inv if r.get("status") in ("alive", "auth", None, "")]
    dead = [r for r in inv if r.get("status") in ("dead", "timeout", "error")]

    buckets = {}
    for r in live:
        buckets.setdefault(r.get("bucket", "review"), []).append(r)

    for bucket, recs in sorted(buckets.items()):
        fn = os.path.join(out, f"import_{bucket}.html")
        open(fn, "w").write(netscape(recs, f"bookmark-triage: {bucket}"))
        print(f"{fn}: {len(recs)}")

    # review.md — clickable checklist for the user
    with open(os.path.join(out, "review.md"), "w") as f:
        f.write("# Needs your call\n\n"
                "Click through; annotate each line with keep-as: business/personal/"
                "homelab, or drop.\n\n")
        for r in sorted(buckets.get("review", []), key=lambda x: x["folder"]):
            f.write(f"- [ ] [{r['title'] or r['url']}]({r['url']}) — "
                    f"folder `{r['folder'] or '(bar)'}`\n")

    with open(os.path.join(out, "dead.md"), "w") as f:
        f.write("# Dead / unreachable (excluded from imports)\n\n")
        for r in sorted(dead, key=lambda x: x["folder"]):
            f.write(f"- [{r['title'] or r['url']}]({r['url']}) — "
                    f"`{r.get('status')}` {r.get('status_detail','')} — "
                    f"folder `{r['folder'] or '(bar)'}`\n")

    # summary
    counts = {b: len(v) for b, v in buckets.items()}
    with open(os.path.join(out, "report.md"), "w") as f:
        f.write("# bookmark-triage report\n\n")
        f.write(f"Unique bookmarks: {len(inv)}  |  live: {len(live)}  |  "
                f"dead/unreachable: {len(dead)}\n\n## Buckets (live only)\n\n")
        for b, c in sorted(counts.items()):
            f.write(f"- **{b}**: {c}\n")
        gated = [r for r in inv if r.get("status") == "auth"]
        f.write(f"\nLogin/bot-gated (kept, worth a manual glance): {len(gated)}\n")
    print(f"dead: {len(dead)}  review: {len(buckets.get('review', []))}")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="triage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse"); p.add_argument("files", nargs="+"); p.set_defaults(fn=cmd_parse)
    p = sub.add_parser("check"); p.add_argument("--workers", type=int, default=24)
    p.add_argument("--all", action="store_true", help="re-probe already-checked urls")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("classify"); p.set_defaults(fn=cmd_classify)
    p = sub.add_parser("build"); p.set_defaults(fn=cmd_build)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
