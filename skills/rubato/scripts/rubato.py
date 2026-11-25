#!/usr/bin/env python3
"""rubato - content-aware dynamic speed for video and audio.

Instead of one flat multiplier, rubato slows down for what matters (takeaways,
lists, key numbers, found by reading the transcript) and speeds through filler,
dull stretches and dead air, around a baseline you choose.

    rubato.py auto    talk.mp4 -o talk.rubato.mp4
    rubato.py transcribe talk.mp4 -o talk.transcript.json
    rubato.py analyze talk.mp4 -o analysis.json
    rubato.py plan    analysis.json -o plan.json [--marks marks.json] [--transcript talk.srt]
    rubato.py render  talk.mp4 plan.json -o out.mp4
    rubato.py remap-srt plan.json talk.srt -o out.srt

Python 3.8+ standard library only. Needs ffmpeg (on PATH, via --ffmpeg,
$RUBATO_FFMPEG, or the imageio-ffmpeg package).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

TICK = 0.1          # planning resolution, seconds
MOTION_FPS = 4      # frames per second sampled for visual activity
AUDIO_SR = 48000    # sample rate of the rendered audio
BLOCKS = " ▁▂▃▄▅▆▇█"


def die(msg: str) -> "None":
    print(f"rubato: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------
# ffmpeg plumbing
# --------------------------------------------------------------------------

def find_ffmpeg(explicit: str | None) -> str:
    for cand in (explicit, os.environ.get("RUBATO_FFMPEG"), shutil.which("ffmpeg")):
        if cand:
            return cand
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    die("ffmpeg not found. Install it (macOS: `brew install ffmpeg`, Debian/Ubuntu: "
        "`apt install ffmpeg`), or run this script with "
        "`uv run --with imageio-ffmpeg rubato.py ...`, or pass --ffmpeg /path/to/ffmpeg.")
    return ""


def probe(ffmpeg: str, path: str) -> dict:
    if not os.path.exists(path):
        die(f"input not found: {path}")
    p = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", path], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    err = p.stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not m:
        die(f"could not read duration of {path}:\n{err.strip()[-600:]}")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vlines = [l for l in err.splitlines()
              if re.search(r"Stream #.*Video:", l) and "attached pic" not in l]
    has_audio = bool(re.search(r"Stream #.*Audio:", err))
    fps = None
    if vlines:
        fm = re.search(r", (\d+(?:\.\d+)?) fps", vlines[0])
        if fm:
            fps = float(fm.group(1))
    return {"duration": duration, "has_video": bool(vlines), "has_audio": has_audio, "fps": fps}


def fps_arg(fps: float | None) -> str:
    if not fps:
        return "30"
    for near, exact in ((23.976, "24000/1001"), (29.97, "30000/1001"), (59.94, "60000/1001")):
        if abs(fps - near) < 0.02:
            return exact
    return f"{fps:g}"


def read_metadata_stream(cmd: list, key: str) -> list:
    """Run ffmpeg with a (a)metadata=print:file=- filter; return [(time, value)]."""
    out = []
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    t = None
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("frame:"):
            m = re.search(r"pts_time:(-?[\d.]+)", line)
            t = float(m.group(1)) if m else None
        elif line.startswith(key + "=") and t is not None:
            raw = line.split("=", 1)[1]
            try:
                v = float(raw)
            except ValueError:
                v = float("-inf")
            if math.isnan(v):
                v = float("-inf")
            out.append((t, v))
    _, err = proc.communicate()
    if proc.returncode != 0:
        die(f"ffmpeg analysis failed:\n{err.strip()[-800:]}")
    return out


# --------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------

def analyze(ffmpeg: str, path: str, use_video: bool = True) -> dict:
    info = probe(ffmpeg, path)
    n = max(1, int(math.ceil(info["duration"] / TICK)))
    rms = None
    motion = None

    if info["has_audio"]:
        print("rubato: analysing audio…", file=sys.stderr)
        key = "lavfi.astats.Overall.RMS_level"
        frame = int(16000 * TICK)
        rows = read_metadata_stream(
            [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", path, "-vn",
             "-map", "0:a:0", "-ac", "1", "-ar", "16000",
             "-af", f"asetnsamples=n={frame}:p=0,astats=metadata=1:reset=1,"
                    f"ametadata=mode=print:key={key}:file=-",
             "-f", "null", "-"], key)
        rms = [-120.0] * n
        for t, v in rows:
            i = int(t / TICK + 0.5)
            if 0 <= i < n:
                rms[i] = round(max(v, -120.0), 1)

    if info["has_video"] and use_video:
        print("rubato: analysing picture…", file=sys.stderr)
        key = "lavfi.scene_score"
        rows = read_metadata_stream(
            [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error", "-i", path, "-an",
             "-map", "0:v:0",
             "-vf", f"fps={MOTION_FPS},scale=160:-2,select='gte(scene,0)',"
                    f"metadata=mode=print:key={key}:file=-",
             "-f", "null", "-"], key)
        samples = [0.0] * max(1, int(math.ceil(info["duration"] * MOTION_FPS)) + 1)
        for t, v in rows:
            i = int(t * MOTION_FPS + 0.5)
            if 0 <= i < len(samples):
                samples[i] = max(0.0, v)
        motion = [round(samples[min(len(samples) - 1, int(i * TICK * MOTION_FPS))], 5)
                  for i in range(n)]

    if rms is None and motion is None:
        die("nothing to analyse: no audio stream and no usable video stream")
    return {"rubato": 1, "source": os.path.abspath(path), "duration": info["duration"],
            "fps": info["fps"], "has_audio": info["has_audio"], "has_video": info["has_video"],
            "tick": TICK, "rms_db": rms, "motion": motion}


# --------------------------------------------------------------------------
# small numeric helpers
# --------------------------------------------------------------------------

def percentile(values: list, q: float) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    k = (len(s) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def smooth(values: list, seconds: float) -> list:
    """Centred moving average."""
    half = max(0, int(seconds / TICK / 2))
    if half == 0:
        return list(values)
    pre = [0.0]
    for v in values:
        pre.append(pre[-1] + v)
    n = len(values)
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append((pre[b] - pre[a]) / (b - a))
    return out


def zscores(values: list, mask: list) -> list:
    sel = [v for v, m in zip(values, mask) if m]
    if len(sel) < 2:
        return [0.0] * len(values)
    mean = sum(sel) / len(sel)
    sd = math.sqrt(sum((v - mean) ** 2 for v in sel) / len(sel))
    if sd < 1e-9:
        return [0.0] * len(values)
    return [max(-2.5, min(2.5, (v - mean) / sd)) for v in values]


def parse_time(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).strip().replace(",", ".").split(":")
    try:
        secs = 0.0
        for p in parts:
            secs = secs * 60 + float(p)
        return secs
    except ValueError:
        die(f"cannot parse time: {v!r} (use seconds, MM:SS or HH:MM:SS)")
        return 0.0


def fmt_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# --------------------------------------------------------------------------
# transcripts and marks
# --------------------------------------------------------------------------

CUE_RE = re.compile(r"((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})")


def parse_cues(path: str) -> list:
    """Return [(start, end, text)] from SRT, VTT or Whisper-style JSON."""
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    cues = []
    if path.lower().endswith(".json"):
        data = json.loads(raw)
        segs = data.get("segments", data) if isinstance(data, dict) else data
        for s in segs:
            words = s.get("words") or []
            if words and all("start" in w and "end" in w for w in words):
                for w in words:
                    cues.append((float(w["start"]), float(w["end"]),
                                 str(w.get("word", w.get("text", ""))).strip()))
            else:
                cues.append((float(s["start"]), float(s["end"]), str(s.get("text", "")).strip()))
        return cues
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        m = CUE_RE.search(lines[i])
        if not m:
            i += 1
            continue
        text = []
        i += 1
        while i < len(lines) and lines[i].strip():
            text.append(re.sub(r"<[^>]+>", "", lines[i]).strip())
            i += 1
        cues.append((parse_time(m.group(1)), parse_time(m.group(2)), " ".join(text)))
    return cues


def sentences(cues: list, max_len: float = 20.0) -> list:
    """Regroup cues (words, or caption lines that break mid-sentence) into sentences."""
    out, cur = [], []

    def flush() -> None:
        if cur:
            out.append((cur[0][0], cur[-1][1], " ".join(c[2] for c in cur if c[2])))
            cur.clear()

    for s, e, text in cues:
        if cur and (s - cur[-1][1] > 1.2 or e - cur[0][0] > max_len):
            flush()
        cur.append((s, e, text.strip()))
        if text.rstrip().endswith((".", "?", "!", "…", "。", "？", "！")):
            flush()
    flush()
    return out


def word_times(cues: list) -> list:
    out = []
    for s, e, text in cues:
        words = text.split()
        for k in range(len(words)):
            out.append(s + (e - s) * (k + 0.5) / len(words))
    return out


def load_marks(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("marks", [])
    marks = []
    for m in data:
        s, e = parse_time(m["start"]), parse_time(m["end"])
        if e <= s:
            die(f"mark has end <= start: {m}")
        marks.append({"start": s, "end": e, "label": m.get("label"),
                      "speed": m.get("speed"), "note": m.get("note")})
    return marks


# --------------------------------------------------------------------------
# reading the transcript: takeaways, lists, numbers, filler
# --------------------------------------------------------------------------

NUM = r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten|a few|several|a couple of)"
ORD = r"(?:first|second|third|fourth|fifth|sixth|last|final)"
THING = (r"(?:things?|reasons?|ways?|steps?|tips?|rules?|points?|lessons?|mistakes?|types?|kinds?|"
         r"options?|parts?|principles?|questions?|factors?|categories|takeaways?|ideas?|problems?)")

KEY_CUES = [
    ("takeaway", 2, r"\btake[- ]?aways?\b"),
    ("takeaway", 2, r"\b(bottom line|long story short|tl;?dr|rule of thumb|pro tip|golden rule|lessons? learned)\b"),
    ("takeaway", 2, r"\b(in summary|to summari[sz]e|to sum (it )?up|in conclusion|to recap|to wrap up)\b"),
    ("takeaway", 2, r"\bthe (one |single )?(main|key|important|big|biggest|whole|real|core|critical|crucial|only) "
                    r"(point|thing|idea|lesson|insight|message|question|problem|difference|reason|trick)\b"),
    ("takeaway", 2, r"\b(most|really|very|super|extremely|incredibly) important\b"),
    ("takeaway", 2, r"\b(keep in mind|don'?t forget|never forget|pay attention|write (this|that) down)\b"),
    ("takeaway", 2, r"(^|[.!?] )remember\b|\bremember[,:]"),
    ("takeaway", 1, r"\bremember\b"),
    ("takeaway", 2, r"\b(here'?s|this is|that'?s) (the thing|the deal|what matters|the trick|the secret|the point|the catch)\b"),
    ("takeaway", 2, r"\bwhat (this|that|it) (really |actually )?means\b"),
    ("takeaway", 2, r"\b(let me|i'?ll|i will|i want to) (repeat|say (that|it|this) again|be (very )?clear|stress|emphasi[sz]e)\b"),
    ("takeaway", 1, r"\b(in other words|the point is|the trick is|the secret is|the answer is|the reason is|make sure|note that)\b"),
    ("takeaway", 1, r"\b(crucial|critical|essential|fundamental|important(ly)?|key)\b"),
    ("list", 2, r"\b" + NUM + r" (?:\w+ ){0,2}" + THING + r"\b"),
    # "number three", but not a slate such as "script number five" or "cam number eight"
    ("list", 2, r"(?<!script )(?<!cam )(?<!camera )(?<!take )(?<!scene )(?<!screen )(?<!slide )(?<!episode )"
                r"\b(number|step|rule|tip|point|reason|lesson|option|part|mistake) "
                r"(one|two|three|four|five|six|seven|eight|nine|ten|10|[1-9])\b(?! ?\d)"),
    ("list", 2, r"\b(firstly|secondly|thirdly|lastly)\b"),
    ("list", 2, r"\b(the )?" + ORD + r" (one|thing|point|reason|step|rule|tip|lesson|mistake|is|was)\b"),
    ("list", 1, r"\b(first|second|third|fourth|fifth|finally|next|then|last)[,:]"),
    ("list", 1, r"\b(first of all|to begin with|on top of that|and finally|last but not least)\b"),
    ("number", 1, r"\d[\d,.]* ?(%|percent\b|x\b|times\b)"),
    ("number", 1, r"[$€£] ?\d|\b\d[\d,.]* ?(dollars|euros|million|billion|thousand)\b"),
    ("number", 1, r"\b(doubled|tripled|halved|twice as|half as)\b"),
]
FILLER_CUES = [
    r"\bcan (you|everyone|everybody|you all|you guys) (hear|see)\b",
    r"\b(share|sharing) my screen\b|\bis this (thing )?on\b|\bam i (on mute|muted)\b|\byou'?re (on mute|muted)\b",
    r"\b(one sec(ond)?|hold on|hang on|bear with me|give me a (sec(ond)?|moment|minute)|just a (sec(ond)?|moment|minute))\b",
    r"\b(where was i|sorry about that|technical (difficulties|issues)|let me (just )?(find|pull up|open|check|see if))\b",
    r"\b(still loading|is loading|waiting for (it|this|that|the))\b",
    r"\b(like and subscribe|hit (the|that) (bell|like)|sponsor(ed)? (of|by)|use (the )?code)\b",
    r"\b(before we (start|begin|get started)|housekeeping|welcome (back|everyone|everybody)|thanks for (joining|watching|coming|tuning in))\b",
]
HESITATION = re.compile(r"\b(um+|uh+|erm+|hmm+|(?<!do )(?<!did )(?<!if )you know|i mean|sort of|kind of|so yeah|okay so)\b")


def find_highlights(cues: list, duration: float, extra: dict | None = None,
                    max_share: float = 0.5) -> list:
    """Spot what is worth slowing down for (takeaways, lists, numbers) and what
    is not (logistics, hesitation), from transcript text alone."""
    key_cues = [(k, w, re.compile(rx)) for k, w, rx in KEY_CUES]
    filler_cues = [re.compile(rx) for rx in FILLER_CUES]
    for rx in (extra or {}).get("key", []):
        key_cues.append(("takeaway", 2, re.compile(rx)))
    for rx in (extra or {}).get("filler", []):
        filler_cues.append(re.compile(rx))

    found = []
    n = len(cues)
    for i, (s, e, text) in enumerate(cues):
        low = text.lower()
        words = low.split()
        if not words or e <= s:
            continue
        score, kinds = 0, {}
        for kind, w, rx in key_cues:
            if rx.search(low):
                score += w
                kinds[kind] = kinds.get(kind, 0) + w
        if score >= 2:
            kind = max(kinds, key=lambda k: kinds[k])
            end, idx = e, {i}
            # "Here is the key takeaway." is a lead-in: the content is the next sentence.
            if len(words) < 12 and i + 1 < n and cues[i + 1][0] - e < 2.0:
                end, idx = cues[i + 1][1], {i, i + 1}
            found.append({"start": s, "end": end, "kind": kind, "idx": idx, "w": score})
        elif any(rx.search(low) for rx in filler_cues) or (
                len(words) >= 4 and len(HESITATION.findall(low)) / len(words) >= 0.2):
            found.append({"start": s, "end": e, "kind": "filler", "idx": {i}, "w": 0})

    keys = sorted((h for h in found if h["kind"] != "filler"), key=lambda h: h["start"])
    merged = []
    for h in keys:
        if merged and h["start"] - merged[-1]["end"] < 1.0:
            m = merged[-1]
            m["end"] = max(m["end"], h["end"])
            m["idx"] = m["idx"] | h["idx"]
            m["w"] = max(m["w"], h["w"])
        else:
            merged.append(dict(h))
    # If everything is a highlight, nothing is: keep the strongest up to a share of the runtime.
    budget, kept = duration * max_share, []
    for h in sorted(merged, key=lambda h: -h["w"]):
        if budget - (h["end"] - h["start"]) >= 0 or not kept:
            kept.append(h)
            budget -= h["end"] - h["start"]
    fillers = [h for h in found if h["kind"] == "filler"
               and not any(k["start"] < h["end"] and h["start"] < k["end"] for k in kept)]
    out = sorted(fillers + kept, key=lambda h: h["start"])
    for h in out:
        h["text"] = " ".join(cues[i][2].strip() for i in sorted(h.pop("idx")))
    return out


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def build_plan(an: dict, o: argparse.Namespace, marks: list | None = None,
               words: list | None = None, highlights: list | None = None) -> dict:
    if not (o.slow <= o.base <= o.fast):
        die("speeds must satisfy --slow <= --base <= --fast")
    dur = an["duration"]
    n = max(1, int(math.ceil(dur / TICK)))
    rms = an.get("rms_db")
    motion = an.get("motion")
    notes = []

    # ---- pauses -----------------------------------------------------------
    voiced = [True] * n
    pause = [False] * n
    thr = None
    if rms:
        audible = [v for v in rms if v > -100] or [-120.0]
        p10, p95 = percentile(rms, 0.10), percentile(audible, 0.95)
        rng = p95 - p10
        if o.silence_db is not None:
            thr = o.silence_db
        elif rng >= 12:
            thr = min(max(p10 + 0.35 * rng, p95 - 30), p95 - 10)
        else:
            notes.append("audio level is nearly constant (music or steady noise): no pauses detected")
        if thr is not None:
            voiced = [v >= thr for v in rms]
            pad = int(round(o.pad / TICK))
            need = int(round(o.min_silence / TICK))
            i = 0
            while i < n:
                if voiced[i]:
                    i += 1
                    continue
                j = i
                while j < n and not voiced[j]:
                    j += 1
                if j - i >= need:
                    a = i if i == 0 else i + pad
                    b = j if j == n else j - pad
                    for k in range(a, b):
                        pause[k] = True
                i = j

    # ---- interest score ---------------------------------------------------
    active = [not p for p in pause]
    parts = []
    if rms:
        floor = thr if thr is not None else percentile(rms, 0.05)
        level = smooth([max(v, floor) for v in rms], 2.0)
        parts.append((0.40, zscores(level, active)))
        if thr is not None:
            density = smooth([1.0 if v else 0.0 for v in voiced], 6.0)
            parts.append((0.25, zscores(density, active)))
    if motion:
        act = smooth([math.log10(v + 1e-4) for v in motion], 2.0)
        parts.append((0.30 if rms else 1.0, zscores(act, active)))
    if words:
        counts = [0.0] * n
        for t in words:
            i = int(t / TICK)
            if 0 <= i < n:
                counts[i] += 1
        parts.append((0.45, zscores(smooth(counts, 6.0), active)))
    wsum = sum(w for w, _ in parts) or 1.0
    score = smooth([sum(w * z[i] for w, z in parts) / wsum for i in range(n)], 3.0)

    ranked = sorted(score[i] for i in range(n) if active[i])

    def rank(v: float) -> float:
        if len(ranked) < 2:
            return 0.5
        lo, hi = 0, len(ranked)
        while lo < hi:
            mid = (lo + hi) // 2
            if ranked[mid] < v:
                lo = mid + 1
            else:
                hi = mid
        return lo / (len(ranked) - 1)

    # Once we can read what is said, sounding lively is no reason to slow down:
    # only detected content and explicit marks get the slow speed.
    content_led = highlights is not None
    spread = max(0.0, min(0.5, o.spread))
    core = spread / 2  # outermost share that gets the full fast / slow speed

    def speed_for(p: float) -> float:
        if spread <= 0:
            return o.base
        if p < spread:
            k = 1.0 if p <= core else (spread - p) / (spread - core)
            return o.base + (o.fast - o.base) * k
        if p > 1 - spread and not content_led:
            q = 1 - p
            k = 1.0 if q <= core else (spread - q) / (spread - core)
            return o.base + (o.slow - o.base) * k
        return o.base

    quant = lambda v: round(round(v / 0.05) * 0.05, 2)
    # Median, not mean: one hard cut inside a pause is not "action".
    motion_s = None
    if motion:
        half = int(1.0 / TICK)
        motion_s = [percentile(motion[max(0, i - half):i + half + 1], 0.5) for i in range(n)]
    speed = [0.0] * n
    reason = [""] * n
    for i in range(n):
        if pause[i]:
            busy = motion_s is not None and motion_s[i] >= o.busy_motion
            # A quiet stretch with a lot happening on screen is a demo, not dead air.
            speed[i] = quant(o.fast if busy else o.silence)
            reason[i] = "quiet-action" if busy else "pause"
        else:
            speed[i] = quant(speed_for(rank(score[i])))
            reason[i] = ("lively" if speed[i] < o.base - 1e-6
                         else "dull" if speed[i] > o.base + 1e-6 else "base")

    # ---- run-length encode, then drop flicker -------------------------------
    segs = []
    for i in range(n):
        if segs and segs[-1]["speed"] == speed[i] and segs[-1]["reason"] == reason[i]:
            segs[-1]["end"] = i + 1
        else:
            segs.append({"start": i, "end": i + 1, "speed": speed[i], "reason": reason[i]})

    def coalesce(items: list) -> list:
        out = []
        for s in items:
            if out and out[-1]["speed"] == s["speed"] and (
                    (out[-1]["reason"] == "pause") == (s["reason"] == "pause")):
                if s["end"] - s["start"] > out[-1]["end"] - out[-1]["start"]:
                    out[-1]["reason"] = s["reason"]
                out[-1]["end"] = s["end"]
            else:
                out.append(dict(s))
        return out

    segs = coalesce(segs)
    # Slivers of pause (left over when part of a pause counts as on-screen action)
    # are not worth a speed change of their own.
    for k, s in enumerate(segs):
        if s["reason"] == "pause" and s["end"] - s["start"] < 4:
            neigh = [segs[j] for j in (k - 1, k + 1)
                     if 0 <= j < len(segs) and segs[j]["reason"] != "pause"]
            if neigh:
                s["speed"], s["reason"] = neigh[0]["speed"], neigh[0]["reason"]
    segs = coalesce(segs)
    min_ticks = int(round(o.min_segment / TICK))
    while True:
        short = [(s["end"] - s["start"], k) for k, s in enumerate(segs)
                 if s["reason"] != "pause" and s["end"] - s["start"] < min_ticks]
        merged = False
        for _, k in sorted(short):
            s = segs[k]
            neigh = [segs[j] for j in (k - 1, k + 1)
                     if 0 <= j < len(segs) and segs[j]["reason"] != "pause"]
            if not neigh:
                continue  # speech squeezed between two pauses: leave it alone
            tgt = min(neigh, key=lambda x: abs(x["speed"] - s["speed"]))
            s["speed"], s["reason"] = tgt["speed"], tgt["reason"]
            segs = coalesce(segs)
            merged = True
            break
        if not merged:
            break

    out = [{"start": round(s["start"] * TICK, 3), "end": round(min(dur, s["end"] * TICK), 3),
            "speed": s["speed"], "reason": s["reason"]} for s in segs]
    out = [s for s in out if s["end"] > s["start"]]
    if out:
        out[-1]["end"] = round(dur, 3)

    # ---- what is being said beats how it sounds; explicit marks beat both ------
    label_speed = {"key": o.slow, "slow": o.slow, "normal": o.base, "base": o.base,
                   "filler": o.fast, "fast": o.fast, "skip": o.silence}
    overlays = [(h["start"], h["end"], o.fast if h["kind"] == "filler" else o.slow,
                 "content:" + h["kind"]) for h in (highlights or [])]
    for m in sorted(marks or [], key=lambda x: x["start"]):
        if m["speed"] is not None:
            v = float(m["speed"])
        elif m["label"] in label_speed:
            v = label_speed[m["label"]]
        else:
            die(f"mark needs a speed or a label in {sorted(label_speed)}: {m}")
        overlays.append((m["start"], m["end"], v, "mark:" + str(m["label"] or "speed")))
    for a, b, v, why in overlays:
        a, b = max(0.0, a), min(dur, b)
        if b <= a:
            continue
        cut = []
        for s in out:
            if s["end"] <= a or s["start"] >= b:
                cut.append(s)
                continue
            if s["start"] < a:
                cut.append({**s, "end": round(a, 3)})
            if s["end"] > b:
                cut.append({**s, "start": round(b, 3)})
        cut.append({"start": round(a, 3), "end": round(b, 3), "speed": round(v, 2), "reason": why})
        out = sorted(cut, key=lambda x: x["start"])
    if overlays:
        # An overlay can leave a sliver of the automatic map beside it; fold it into its neighbour.
        auto = lambda s: s["reason"] != "pause" and not s["reason"].startswith(("mark:", "content:"))
        for k, s in enumerate(out):
            if auto(s) and s["end"] - s["start"] < 1.0:
                neigh = [out[j] for j in (k - 1, k + 1) if 0 <= j < len(out) and auto(out[j])
                         and out[j]["end"] - out[j]["start"] >= 1.0]
                if not neigh and s["end"] - s["start"] < 0.5:
                    neigh = [out[j] for j in (k + 1, k - 1) if 0 <= j < len(out)
                             and out[j]["reason"].startswith(("mark:", "content:"))]
                if neigh:
                    s["speed"], s["reason"] = neigh[0]["speed"], neigh[0]["reason"]
        tidy = []
        for s in out:
            if tidy and tidy[-1]["speed"] == s["speed"] and tidy[-1]["reason"] == s["reason"]:
                tidy[-1]["end"] = s["end"]
            else:
                tidy.append(s)
        out = tidy

    plan = {"rubato": 1, "source": an.get("source"), "duration": round(dur, 3), "fps": an.get("fps"),
            "settings": {"slow": o.slow, "base": o.base, "fast": o.fast, "silence": o.silence,
                         "spread": spread, "silence_db": None if thr is None else round(thr, 1)},
            "notes": notes,
            "highlights": [{"start": round(h["start"], 2), "end": round(h["end"], 2),
                            "kind": h["kind"], "text": h["text"]} for h in (highlights or [])],
            "segments": out}
    plan["stats"] = plan_stats(plan)
    return plan


def normalise_segments(plan: dict) -> list:
    """Validate a (possibly hand-edited) plan; return gap-free, merged segments."""
    dur = float(plan["duration"])
    base = float(plan.get("settings", {}).get("base", 1.0))
    segs = sorted(({"start": parse_time(s["start"]), "end": parse_time(s["end"]),
                    "speed": float(s["speed"])} for s in plan["segments"]),
                  key=lambda x: x["start"])
    out = []
    pos = 0.0
    for s in segs:
        if not 0.25 <= s["speed"] <= 8:
            die(f"segment speed {s['speed']} outside 0.25–8x")
        a, b = max(pos, s["start"]), min(dur, s["end"])
        if a - pos > 1e-3:
            out.append({"start": pos, "end": a, "speed": base})
        if b - a > 1e-3:
            out.append({"start": a, "end": b, "speed": s["speed"]})
            pos = b
    if dur - pos > 1e-3:
        out.append({"start": pos, "end": dur, "speed": base})
    merged = []
    for s in out:
        if merged and abs(merged[-1]["speed"] - s["speed"]) < 1e-6:
            merged[-1]["end"] = s["end"]
        else:
            merged.append(s)
    if not merged:
        die("plan has no segments")
    return merged


def plan_stats(plan: dict) -> dict:
    segs = normalise_segments(plan)
    dur = float(plan["duration"])
    out_dur = sum((s["end"] - s["start"]) / s["speed"] for s in segs)
    by = {}
    for s in segs:
        key = f"{s['speed']:.2f}"
        by[key] = by.get(key, 0.0) + (s["end"] - s["start"])
    return {"segments": len(segs), "source_seconds": round(dur, 2),
            "output_seconds": round(out_dur, 2),
            "effective_speed": round(dur / out_dur, 3) if out_dur else None,
            "source_seconds_by_speed": {k: round(v, 1) for k, v in sorted(by.items())}}


def summary(plan: dict, width: int = 64) -> str:
    segs = normalise_segments(plan)
    st = plan_stats(plan)
    dur = float(plan["duration"])
    base = float(plan.get("settings", {}).get("base", 1.0))
    lo = min(s["speed"] for s in segs)
    hi = max(max(s["speed"] for s in segs), lo + 0.01)
    strip = ""
    for c in range(width):
        a, b = dur * c / width, dur * (c + 1) / width
        tot = sum((min(b, s["end"]) - max(a, s["start"])) * s["speed"]
                  for s in segs if s["end"] > a and s["start"] < b)
        mean = tot / (b - a) if b > a else lo
        strip += BLOCKS[1 + int(round((mean - lo) / (hi - lo) * 7))]
    lines = [
        f"source   {fmt_time(dur)}  ->  output {fmt_time(st['output_seconds'])}"
        f"   (effective {st['effective_speed']}x; flat {base:g}x would give {fmt_time(dur / base)})",
        f"speed    |{strip}|   low bar = {lo:g}x, tall bar = {hi:g}x",
        "share    " + "  ".join(f"{float(k):g}x {v / dur * 100:.0f}%"
                                for k, v in st["source_seconds_by_speed"].items()),
        f"segments {st['segments']}",
    ]
    hl = plan.get("highlights") or []
    if hl:
        kinds = {}
        for h in hl:
            kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
        lines.append("content  " + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items()))
                     + "   (from the transcript; listed in the plan under \"highlights\")")
    for note in plan.get("notes", []):
        lines.append(f"note     {note}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# transcribe
# --------------------------------------------------------------------------

def transcribe(ffmpeg: str, src: str, dst: str, model: str = "base",
               language: str | None = None) -> bool:
    """Write a Whisper-style JSON transcript. Returns False when no speech-to-text
    engine is available (the caller then falls back to signals only)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        WhisperModel = None
    cli = shutil.which("whisper")
    if WhisperModel is None and not cli:
        return False
    with tempfile.TemporaryDirectory(prefix="rubato-") as tmp:
        wav = os.path.join(tmp, "speech.wav")
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn",
             "-map", "0:a:0", "-ac", "1", "-ar", "16000", wav], "extracting audio")
        print(f"rubato: transcribing (model {model})…", file=sys.stderr)
        if WhisperModel is not None:
            import numpy as np  # ships with faster-whisper
            with wave.open(wav, "rb") as w:
                pcm = w.readframes(w.getnframes())
            # Hand over samples, not a path: avoids the engine's own decoder and its version quirks.
            audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            wm = WhisperModel(model, compute_type="int8")
            segs, info = wm.transcribe(audio, language=language, vad_filter=True,
                                       word_timestamps=True)
            data = {"language": info.language,
                    "segments": [{"start": round(x.start, 2), "end": round(x.end, 2),
                                  "text": x.text.strip(),
                                  "words": [{"start": round(w.start, 2), "end": round(w.end, 2),
                                             "word": w.word.strip()} for w in (x.words or [])]}
                                 for x in segs]}
        else:
            cmd = [cli, wav, "--model", model, "--output_format", "json", "--output_dir", tmp,
                   "--word_timestamps", "True"]
            if language:
                cmd += ["--language", language]
            run(cmd, "transcribing")
            raw = load_json(os.path.join(tmp, "speech.json"))
            data = {"language": raw.get("language"),
                    "segments": [{"start": round(x["start"], 2), "end": round(x["end"], 2),
                                  "text": x["text"].strip(), "words": x.get("words", [])}
                                 for x in raw.get("segments", [])]}
    save_json(data, dst)
    print(f"rubato: wrote {dst}", file=sys.stderr)
    return True


def sidecar_transcript(path: str) -> str | None:
    stem = os.path.splitext(path)[0]
    for ext in (".srt", ".vtt", ".transcript.json"):
        if os.path.exists(stem + ext):
            return stem + ext
    return None


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def atempo_chain(v: float) -> str:
    if abs(v - 1.0) < 1e-6:
        return ""
    parts = []
    while v > 2.0 + 1e-9:
        parts.append(2.0)
        v /= 2.0
    while v < 0.5 - 1e-9:
        parts.append(0.5)
        v /= 0.5
    parts.append(v)
    return "".join(f"atempo={p:.6f}," for p in parts)


def run(cmd: list, what: str) -> None:
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        die(f"ffmpeg failed while {what}:\n{p.stderr.strip()[-1200:]}")


def render_audio(ffmpeg: str, src: str, segs: list, tmp: str) -> str:
    """Time-stretch every segment (pitch preserved) into one sample-exact WAV."""
    out_edges = [0.0]
    for s in segs:
        out_edges.append(out_edges[-1] + (s["end"] - s["start"]) / s["speed"])
    sample_edges = [int(round(t * AUDIO_SR)) for t in out_edges]

    # Batches keep ffmpeg's buffering bounded on long files.
    batches, cur, cur_len = [], [], 0.0
    for idx, s in enumerate(segs):
        d = s["end"] - s["start"]
        if cur and (cur_len + d > 120 or len(cur) >= 40):
            batches.append(cur)
            cur, cur_len = [], 0.0
        cur.append(idx)
        cur_len += d
    if cur:
        batches.append(cur)

    wavs = []
    for bi, idxs in enumerate(batches):
        print(f"\rrubato: audio {bi + 1}/{len(batches)}", end="", file=sys.stderr)
        live = [i for i in idxs if sample_edges[i + 1] > sample_edges[i]]
        if not live:
            continue
        b0, b1 = segs[idxs[0]]["start"], segs[idxs[-1]]["end"]
        fc = [f"[0:a:0]aresample={AUDIO_SR},aformat=sample_fmts=fltp:channel_layouts=stereo,"
              f"asplit={len(live)}" + "".join(f"[a{k}]" for k in range(len(live)))]
        for k, i in enumerate(live):
            s = segs[i]
            nsamp = sample_edges[i + 1] - sample_edges[i]
            fc.append(f"[a{k}]atrim=start={s['start'] - b0:.6f}:end={s['end'] - b0:.6f},"
                      f"asetpts=PTS-STARTPTS,{atempo_chain(s['speed'])}"
                      f"apad,atrim=end_sample={nsamp},asetpts=PTS-STARTPTS[o{k}]")
        fc.append("".join(f"[o{k}]" for k in range(len(live)))
                  + f"concat=n={len(live)}:v=0:a=1[out]")
        wav = os.path.join(tmp, f"a{bi:05d}.wav")
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-ss", f"{b0:.6f}", "-t", f"{b1 - b0:.6f}", "-i", src, "-vn",
             "-filter_complex", ";".join(fc), "-map", "[out]",
             "-c:a", "pcm_s16le", wav], "stretching audio")
        wavs.append(wav)
    print("", file=sys.stderr)

    joined = os.path.join(tmp, "audio.wav")
    with wave.open(joined, "wb") as dst:
        dst.setnchannels(2)
        dst.setsampwidth(2)
        dst.setframerate(AUDIO_SR)
        for w in wavs:
            with wave.open(w, "rb") as srcw:
                while True:
                    chunk = srcw.readframes(1 << 16)
                    if not chunk:
                        break
                    dst.writeframes(chunk)
            os.remove(w)
    return joined


def render(ffmpeg: str, src: str, plan: dict, out: str, o: argparse.Namespace) -> None:
    info = probe(ffmpeg, src)
    if abs(info["duration"] - float(plan["duration"])) > 1.0:
        die(f"plan was made for a {plan['duration']}s file but {src} is {info['duration']:.1f}s")
    segs = normalise_segments(plan)
    total = sum((s["end"] - s["start"]) / s["speed"] for s in segs)
    ext = os.path.splitext(out)[1].lower()
    audio_only_out = ext in (".m4a", ".mp3", ".wav", ".aac", ".flac", ".opus", ".ogg")
    want_video = info["has_video"] and not audio_only_out
    if not want_video and not info["has_audio"]:
        die("nothing to render")
    if os.path.abspath(src) == os.path.abspath(out):
        die("output would overwrite the input")

    with tempfile.TemporaryDirectory(prefix="rubato-") as tmp:
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-stats", "-y"]
        maps, codec = [], []
        if want_video:
            cmd += ["-i", src]
        if info["has_audio"]:
            wav = render_audio(ffmpeg, src, segs, tmp)
            cmd += ["-i", wav]
            maps += ["-map", f"{1 if want_video else 0}:a:0"]
            if ext == ".wav":
                codec += ["-c:a", "pcm_s16le"]
            elif ext == ".mp3":
                codec += ["-c:a", "libmp3lame", "-b:a", o.audio_bitrate]
            elif ext == ".flac":
                codec += ["-c:a", "flac"]
            elif ext in (".opus", ".ogg", ".webm"):
                codec += ["-c:a", "libopus", "-b:a", o.audio_bitrate]
            else:
                codec += ["-c:a", "aac", "-b:a", o.audio_bitrate]
        if want_video:
            # One monotonic, piecewise-linear time map for the whole picture stream, written
            # as a balanced if() tree so that hundreds of segments stay shallow to parse.
            starts = [0.0]
            for s in segs:
                starts.append(starts[-1] + (s["end"] - s["start"]) / s["speed"])

            def tree(lo: int, hi: int) -> str:
                if hi - lo == 1:
                    s = segs[lo]
                    return f"{starts[lo]:.5f}+(T-{s['start']:.4f})/{s['speed']:.4f}"
                mid = (lo + hi) // 2
                return f"if(lt(T,{segs[mid]['start']:.4f}),{tree(lo, mid)},{tree(mid, hi)})"

            expr = tree(0, len(segs))
            vf = (f"[0:v:0]setpts=PTS-STARTPTS,setpts='({expr})/TB',"
                  f"fps={fps_arg(info['fps'])},"
                  f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',format=yuv420p[v]")
            cmd += ["-filter_complex", vf]
            maps = ["-map", "[v]"] + maps
            if ext == ".webm":
                codec += ["-c:v", "libvpx-vp9", "-crf", str(o.crf + 12), "-b:v", "0"]
            else:
                codec += ["-c:v", o.vcodec, "-preset", o.preset, "-crf", str(o.crf)]
                if ext in (".mp4", ".mov", ".m4v"):
                    codec += ["-movflags", "+faststart"]
        cmd += maps + codec + ["-t", f"{total:.3f}", out]
        print("rubato: encoding…", file=sys.stderr)
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=sys.stderr)
        if p.returncode != 0:
            die("ffmpeg failed while encoding (see message above)")
    print(f"rubato: wrote {out}", file=sys.stderr)


# --------------------------------------------------------------------------
# subtitle remap
# --------------------------------------------------------------------------

def remap_srt(plan: dict, src: str, dst: str) -> None:
    segs = normalise_segments(plan)

    def warp(t: float) -> float:
        return sum(max(0.0, min(t - s["start"], s["end"] - s["start"])) / s["speed"] for s in segs)

    vtt = src.lower().endswith(".vtt")

    def stamp(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d}{'.' if vtt else ','}{ms:03d}"

    with open(src, encoding="utf-8-sig") as f:
        text = f.read()
    text = CUE_RE.sub(lambda m: f"{stamp(warp(parse_time(m.group(1))))} --> "
                                f"{stamp(warp(parse_time(m.group(2))))}", text)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"rubato: wrote {dst}", file=sys.stderr)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def add_plan_opts(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("speed map")
    g.add_argument("--base", type=float, default=1.2, help="baseline speed (default 1.2)")
    g.add_argument("--fast", type=float, default=1.5, help="speed for dull stretches (default 1.5)")
    g.add_argument("--slow", type=float, default=1.0, help="speed for lively stretches (default 1.0)")
    g.add_argument("--silence", type=float, default=2.0,
                   help="speed for dead air: pauses with nothing happening on screen (default 2.0; "
                        "set equal to --fast to treat pauses like any dull stretch)")
    g.add_argument("--spread", type=float, default=0.30,
                   help="share of non-pause time pushed towards each extreme, 0-0.5 (default 0.30; "
                        "0 = only pauses deviate from base)")
    g.add_argument("--min-segment", type=float, default=2.0,
                   help="shortest stretch allowed at its own speed, seconds (default 2.0)")
    g.add_argument("--min-silence", type=float, default=0.6,
                   help="shortest gap treated as a pause, seconds (default 0.6)")
    g.add_argument("--pad", type=float, default=0.12,
                   help="margin kept at speech speed around each pause, seconds (default 0.12)")
    g.add_argument("--silence-db", type=float, default=None,
                   help="pause threshold in dBFS (default: adaptive)")
    g.add_argument("--busy-motion", type=float, default=0.03,
                   help="scene-change score above which a quiet stretch counts as on-screen action")
    g.add_argument("--marks", help="JSON list of {start, end, label|speed} overrides")
    g.add_argument("--transcript",
                   help="SRT / VTT / Whisper JSON. Read for takeaways, lists, numbers and filler, "
                        "and used as a speech-density signal")
    g.add_argument("--no-content", action="store_true",
                   help="do not read the transcript for takeaways and filler (density signal only)")
    g.add_argument("--cues", help='JSON {"key": [regex...], "filler": [regex...]} adding your own '
                                  "phrases (other languages, house jargon)")
    g.add_argument("--max-key-share", type=float, default=0.5,
                   help="most of the runtime that detected highlights may slow down (default 0.5)")


def add_render_opts(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("encoding")
    g.add_argument("--crf", type=int, default=18, help="video quality, lower is better (default 18)")
    g.add_argument("--preset", default="medium", help="x264 preset (default medium)")
    g.add_argument("--vcodec", default="libx264", help="video encoder (default libx264)")
    g.add_argument("--audio-bitrate", default="192k")


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def plan_from_args(an: dict, a: argparse.Namespace) -> dict:
    marks = load_marks(a.marks) if a.marks else None
    words = highlights = None
    if a.transcript:
        cues = parse_cues(a.transcript)
        words = word_times(cues)
        if not a.no_content:
            extra = load_json(a.cues) if a.cues else None
            highlights = find_highlights(sentences(cues), an["duration"], extra, a.max_key_share)
    plan = build_plan(an, a, marks, words, highlights)
    if not a.transcript:
        plan["notes"].append("no transcript: speeds follow sound and picture only, not what is said")
    return plan


def main() -> None:
    ap = argparse.ArgumentParser(prog="rubato", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ffmpeg", help="path to the ffmpeg binary")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("auto", help="analyse, plan and render in one go")
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--plan-only", action="store_true", help="stop after writing the plan")
    p.add_argument("--no-video-analysis", action="store_true")
    p.add_argument("--no-transcribe", action="store_true",
                   help="do not run speech-to-text when no transcript is found next to the input")
    p.add_argument("--model", default="base", help="Whisper model size (default base)")
    p.add_argument("--language", help="spoken language code, e.g. en, it (default: detect)")
    add_plan_opts(p)
    add_render_opts(p)

    p = sub.add_parser("analyze", help="measure loudness and on-screen activity")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--no-video-analysis", action="store_true")

    p = sub.add_parser("transcribe", help="speech to text (needs faster-whisper or the whisper CLI)")
    p.add_argument("input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--model", default="base", help="Whisper model size (default base)")
    p.add_argument("--language", help="spoken language code, e.g. en, it (default: detect)")

    p = sub.add_parser("plan", help="turn an analysis into a speed map")
    p.add_argument("analysis")
    p.add_argument("-o", "--output", required=True)
    add_plan_opts(p)

    p = sub.add_parser("show", help="print the summary of a plan (after hand edits)")
    p.add_argument("plan")

    p = sub.add_parser("render", help="render a video (or audio file) from a plan")
    p.add_argument("input")
    p.add_argument("plan")
    p.add_argument("-o", "--output", required=True)
    add_render_opts(p)

    p = sub.add_parser("remap-srt", help="retime subtitles to match a plan")
    p.add_argument("plan")
    p.add_argument("subtitles")
    p.add_argument("-o", "--output", required=True)

    a = ap.parse_args()

    if a.cmd == "analyze":
        save_json(analyze(find_ffmpeg(a.ffmpeg), a.input, not a.no_video_analysis), a.output)
        print(f"rubato: wrote {a.output}", file=sys.stderr)
    elif a.cmd == "transcribe":
        if not transcribe(find_ffmpeg(a.ffmpeg), a.input, a.output, a.model, a.language):
            die("no speech-to-text engine found. Run with `uv run --with faster-whisper "
                "--with imageio-ffmpeg rubato.py transcribe ...`, or install the whisper CLI.")
    elif a.cmd == "plan":
        plan = plan_from_args(load_json(a.analysis), a)
        save_json(plan, a.output)
        print(summary(plan))
    elif a.cmd == "show":
        print(summary(load_json(a.plan)))
    elif a.cmd == "render":
        render(find_ffmpeg(a.ffmpeg), a.input, load_json(a.plan), a.output, a)
    elif a.cmd == "remap-srt":
        remap_srt(load_json(a.plan), a.subtitles, a.output)
    elif a.cmd == "auto":
        ff = find_ffmpeg(a.ffmpeg)
        stem, ext = os.path.splitext(a.input)
        out = a.output or f"{stem}.rubato{ext or '.mp4'}"
        an = analyze(ff, a.input, not a.no_video_analysis)
        if not a.transcript:
            a.transcript = sidecar_transcript(a.input)
            if a.transcript:
                print(f"rubato: using transcript {a.transcript}", file=sys.stderr)
            elif an["has_audio"] and not a.no_transcribe:
                made = os.path.splitext(a.input)[0] + ".transcript.json"
                if transcribe(ff, a.input, made, a.model, a.language):
                    a.transcript = made
        plan = plan_from_args(an, a)
        plan_path = os.path.splitext(out)[0] + ".plan.json"
        save_json(plan, plan_path)
        print(summary(plan))
        print(f"rubato: wrote {plan_path}", file=sys.stderr)
        if not a.plan_only:
            render(ff, a.input, plan, out, a)


def cli() -> None:
    try:
        main()
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        die(f"{type(exc).__name__}: {exc}")
    except KeyboardInterrupt:
        die("interrupted")


if __name__ == "__main__":
    cli()
