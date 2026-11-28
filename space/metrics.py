"""Anonymous usage counts for the hosted Rubato demo.

What is written: one line per event (a page view, a job, a download) in a
dated JSONL file. What is never written: file names, links, transcripts, IP
addresses or user agents. Visitors are counted with a hash of address and
browser salted by a random value that lives only in memory and changes every
day, so a hash cannot be traced to anyone or followed across days.

Where it is kept, first match wins:
  RUBATO_DATA_DIR              a folder you choose
  /data                        a Hugging Face Space with persistent storage
  the temp folder              lost on every restart
With HF_TOKEN and RUBATO_METRICS_REPO set, the folder is also restored from
and pushed to a private Hugging Face dataset, which survives restarts.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.parse


def _pick_dir() -> tuple[str, str]:
    custom = os.environ.get("RUBATO_DATA_DIR")
    if custom:
        return custom, "folder"
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "/data/rubato-metrics", "disk"
    return os.path.join(tempfile.gettempdir(), "rubato-metrics"), "temporary"


DATA, MODE = _pick_dir()
os.makedirs(DATA, exist_ok=True)
STARTED = time.time()
_lock = threading.Lock()
_scheduler = None
_sync_error = None


def start_sync() -> None:
    """Keep the event files in a private Hugging Face dataset, if configured."""
    global MODE, _scheduler, _sync_error
    repo, token = os.environ.get("RUBATO_METRICS_REPO"), os.environ.get("HF_TOKEN")
    if not (repo and token):
        return
    try:
        from huggingface_hub import CommitScheduler, snapshot_download
        _scheduler = CommitScheduler(repo_id=repo, repo_type="dataset", folder_path=DATA,
                                     every=10, private=True, token=token,
                                     allow_patterns=["*.jsonl"])
        snapshot_download(repo, repo_type="dataset", local_dir=DATA, token=token,
                          allow_patterns=["*.jsonl"])
        MODE = "dataset"
    except Exception as exc:  # metrics must never stop the app from starting
        _sync_error = type(exc).__name__


def flush() -> None:
    if _scheduler is not None:
        try:
            _scheduler.push_to_hub()
        except Exception:
            pass


def storage() -> dict:
    return {"mode": MODE, "repo": os.environ.get("RUBATO_METRICS_REPO") if MODE == "dataset" else None,
            "sync_error": _sync_error}


# ---------------------------------------------------------------------------
# Writing events
# ---------------------------------------------------------------------------
def _day(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


def track(event: str, **fields) -> None:
    now = time.time()
    row = {"t": int(now), "e": event}
    row.update({k: v for k, v in fields.items() if v is not None})
    try:
        with _lock:
            with open(os.path.join(DATA, f"events-{_day(now)}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
            _cache.clear()
    except OSError:
        pass


_salt = {"day": "", "value": b""}


def visitor(request) -> str | None:
    """A per-day anonymous id for whoever sent this request."""
    try:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if not ip and request.client:
            ip = request.client.host
        ua = request.headers.get("user-agent") or ""
        today = _day(time.time())
        with _lock:
            if _salt["day"] != today:
                _salt["day"], _salt["value"] = today, secrets.token_bytes(16)
            salt = _salt["value"]
        return hashlib.sha256(salt + ip.encode() + b"|" + ua.encode()).hexdigest()[:12]
    except Exception:
        return None


NAMED_BOTS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
              "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User",
              "Google-Extended", "Googlebot", "bingbot", "Applebot", "DuckDuckBot", "YandexBot",
              "Amazonbot", "Bytespider", "CCBot", "meta-externalagent", "facebookexternalhit",
              "Twitterbot", "Slackbot", "LinkedInBot", "Discordbot", "WhatsApp", "TelegramBot")
_GENERIC_BOT = re.compile(r"bot|crawl|spider|slurp|preview|monitor|uptime|curl|wget|python|httpx|"
                          r"go-http|okhttp|headless|lighthouse|scrapy|axios|node-fetch", re.I)


def bot_name(ua: str) -> str | None:
    low = (ua or "").lower()
    for name in NAMED_BOTS:
        if name.lower() in low:
            return name
    if not low or _GENERIC_BOT.search(low):
        return "Other bot"
    return None


_OWN_HOSTS = {"tryrubato.com", "andreolf-rubato.hf.space", "localhost", "127.0.0.1"}
_TAG = re.compile(r"[^a-z0-9._-]")


def referrer(request) -> str:
    """Where a visit came from: a ?ref= or ?utm_source= tag, else the referring site's host."""
    for key in ("ref", "utm_source"):
        tag = _TAG.sub("", (request.query_params.get(key) or "").lower())[:40]
        if tag:
            return tag
    host = (urllib.parse.urlsplit(request.headers.get("referer") or "").hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    own = host in _OWN_HOSTS or host == (request.headers.get("host") or "").split(":")[0].lower()
    return "direct" if not host or own else host[:60]


def page_view(request, path: str) -> None:
    bot = bot_name(request.headers.get("user-agent") or "")
    if bot:
        track("bot", bot=bot, path=path)
    else:
        track("view", path=path, v=visitor(request), ref=referrer(request))


ACTIONS = ("seen", "engaged", "deep", "pick", "file", "sample", "err", "agents", "guide",
           "github", "claude", "feedback", "copy", "leave")
_sent = {"day": "", "n": collections.Counter()}


def device(ua: str) -> str:
    low = (ua or "").lower()
    if "mobi" in low or "iphone" in low:
        return "Phone"
    if "ipad" in low or "android" in low or "tablet" in low:
        return "Tablet"
    return "Computer"


def action(request, name: str, seconds=None) -> None:
    """Something the page's own script reported: it ran, or a button was used."""
    ua = request.headers.get("user-agent") or ""
    if name not in ACTIONS or bot_name(ua):
        return
    v = visitor(request)
    today = _day(time.time())
    with _lock:                       # a page sends each action once; cap what one sender can write
        if _sent["day"] != today:
            _sent["day"], _sent["n"] = today, collections.Counter()
        _sent["n"][v] += 1
        if _sent["n"][v] > 60:
            return
    fields = {"a": name, "v": v}
    if name == "seen":
        fields["dev"] = device(ua)
    if name == "leave":
        try:
            fields["s"] = max(0, min(int(seconds or 0), 3600))
        except (TypeError, ValueError):
            fields["s"] = 0
    track("act", **fields)


STAY = (("Under 10 seconds", 10), ("10 to 30 seconds", 30), ("30 seconds to 2 minutes", 120),
        ("Over 2 minutes", 10 ** 9))


def failure_reason(message: str, exc: Exception | None = None) -> str:
    low = (message or "").lower()
    if "up to" in low and "minutes" in low:
        return "Too long"
    if "larger than" in low:
        return "Too large"
    if "could not be read" in low or "no video or audio" in low:
        return "Unreadable file"
    if "link" in low or "redirect" in low:
        return "Bad link"
    return f"Crash: {type(exc).__name__}" if exc is not None else "Other"


# ---------------------------------------------------------------------------
# Reading them back
# ---------------------------------------------------------------------------
_cache: dict = {}


def _events():
    for name in sorted(os.listdir(DATA)):
        if not (name.startswith("events-") and name.endswith(".jsonl")):
            continue
        day = name[7:-6]
        try:
            with open(os.path.join(DATA, name), encoding="utf-8") as f:
                for line in f:
                    try:
                        yield day, json.loads(line)
                    except ValueError:
                        continue
        except OSError:
            continue


def _blank() -> dict:
    return {"visitors": 0, "views": 0, "started": 0, "done": 0, "failed": 0, "downloads": 0,
            "source_seconds": 0.0, "saved_seconds": 0.0, "took_seconds": 0.0}


def _top(counter, n: int = 12) -> list:
    return [[k, v] for k, v in counter.most_common(n)]


def stats(days: int = 30) -> dict:
    days = min(max(int(days), 1), 365)
    with _lock:
        hit = _cache.get(days)
        if hit and time.time() - hit[0] < 10:
            return hit[1]

    today = datetime.datetime.now(datetime.timezone.utc).date()
    dates = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    in_range = set(dates)
    before = {(today - datetime.timedelta(days=i)).isoformat() for i in range(days, days * 2)}

    totals, previous, all_time = _blank(), _blank(), _blank()
    per_day = {d: {"date": d, "visitors": 0, "views": 0, "upload": 0, "sample": 0,
                   "connector": 0, "failed": 0} for d in dates}
    seen = collections.defaultdict(set)            # day -> visitor ids, for daily uniques
    funnel = {k: set() for k in ("visited", "started", "finished", "downloaded")}
    refs, bots, errors, langs, kinds = (collections.Counter() for _ in range(5))
    recent = collections.deque(maxlen=40)
    first_day = None
    steps = {k: set() for k in ("seen", "engaged", "tried")}
    actions, devices, stay, pages = (collections.Counter() for _ in range(4))
    steps_since = None

    for day, ev in _events():
        first_day = first_day or day
        kind, v = ev.get("e"), ev.get("v")
        buckets = [all_time] + ([totals] if day in in_range else []) + ([previous] if day in before else [])
        here = day in in_range
        site = ev.get("src") in ("upload", "sample")
        if kind == "view":
            for b in buckets:
                b["views"] += 1
            if v and v not in seen[day]:
                seen[day].add(v)
                for b in buckets:
                    b["visitors"] += 1
                if here:
                    per_day[day]["visitors"] += 1
            if here:
                per_day[day]["views"] += 1
                refs[ev.get("ref") or "direct"] += 1
                pages[ev.get("path") or "/"] += 1
                if v:
                    funnel["visited"].add((day, v))
        elif kind == "act":
            steps_since = steps_since or day
            a = ev.get("a")
            if not here:
                continue
            if a == "seen":
                devices[ev.get("dev") or "Computer"] += 1
            elif a == "leave":
                secs = ev.get("s") or 0
                stay[next(label for label, top in STAY if secs < top)] += 1
            elif a != "engaged":
                actions[a] += 1
            if v:
                key = "tried" if a in ("pick", "file", "sample") else a
                if key in steps:
                    steps[key].add((day, v))
        elif kind == "bot" and here:
            bots[ev.get("bot") or "Other bot"] += 1
        elif kind == "start":
            for b in buckets:
                b["started"] += 1
            if here and site and v:
                funnel["started"].add((day, v))
        elif kind == "job":
            ok = bool(ev.get("ok"))
            for b in buckets:
                b["done" if ok else "failed"] += 1
                if ok:
                    b["source_seconds"] += ev.get("dur") or 0
                    b["saved_seconds"] += max(0.0, (ev.get("dur") or 0) - (ev.get("out") or 0))
                    b["took_seconds"] += ev.get("took") or 0
            if here:
                src = ev.get("src") if ev.get("src") in ("upload", "sample", "connector") else "upload"
                if ok:
                    per_day[day][src] += 1
                    kinds[ev.get("kind") or "video"] += 1
                    langs[ev.get("lang") or "auto"] += 1
                    if site and v:
                        funnel["finished"].add((day, v))
                else:
                    per_day[day]["failed"] += 1
                    errors[ev.get("reason") or "Other"] += 1
                recent.append({k: ev.get(k) for k in
                               ("t", "src", "ok", "reason", "kind", "dur", "out", "took", "lang")})
        elif kind == "reject":
            for b in buckets:
                b["failed"] += 1
            if here:
                per_day[day]["failed"] += 1
                errors[ev.get("reason") or "Other"] += 1
        elif kind == "download":
            for b in buckets:
                b["downloads"] += 1
            if here and site and v:
                funnel["downloaded"].add((day, v))

    # the page-script steps only exist from the day they were first recorded, so once they
    # do, the whole funnel counts from that day and every step describes the same visits
    if steps_since:
        funnel = {k: {x for x in s if x[0] >= steps_since} for k, s in funnel.items()}
    # only count funnel steps for visitors seen at the step before
    started = funnel["started"] & funnel["visited"]
    finished = funnel["finished"] & started
    real = steps["seen"] & funnel["visited"]
    engaged = steps["engaged"] & real
    out = {
        "range_days": days, "generated": int(time.time()), "first_day": first_day,
        "totals": totals, "previous": previous, "all_time": all_time,
        "days": [per_day[d] for d in dates],
        "funnel": {"visited": len(funnel["visited"]), "started": len(started),
                   "finished": len(finished), "downloaded": len(funnel["downloaded"] & finished),
                   "real": len(real), "engaged": len(engaged),
                   "tried": len(steps["tried"] & real)},
        "pages": _top(pages, 15), "steps_since": steps_since, "actions": _top(actions, 20), "devices": _top(devices),
        "stay": [[label, stay[label]] for label, _ in STAY if stay[label]],
        "referrers": _top(refs), "bots": _top(bots), "errors": _top(errors),
        "languages": _top(langs, 8), "kinds": _top(kinds),
        "recent": list(recent)[::-1],
        "storage": storage(), "uptime_seconds": int(time.time() - STARTED),
    }
    with _lock:
        _cache[days] = (time.time(), out)
    return out
