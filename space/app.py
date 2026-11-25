"""Rubato web demo: a landing page plus a small job API.

Runs the same rubato.py that ships with the skill.

Local:
    uv run --with fastapi --with uvicorn --with python-multipart \
           --with faster-whisper --with imageio-ffmpeg space/app.py
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import ipaddress
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import shutil
import tempfile
import threading
import time
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
MAX_MINUTES = float(os.environ.get("RUBATO_MAX_MINUTES", "15"))
MAX_MB = float(os.environ.get("RUBATO_MAX_MB", "500"))
MODEL = os.environ.get("RUBATO_MODEL", "base")
KEEP_SECONDS = 30 * 60
SITE_URL = (os.environ.get("RUBATO_SITE_URL")
            or ("https://" + os.environ["SPACE_HOST"].split(",")[0].strip() if os.environ.get("SPACE_HOST") else "")).rstrip("/")
REPO = "https://github.com/andreolf/rubato"
WORK = os.path.join(tempfile.gettempdir(), "rubato-web")
os.makedirs(WORK, exist_ok=True)


def load_rubato():
    for cand in (os.path.join(HERE, "rubato.py"),
                 os.path.join(HERE, "..", "skills", "rubato", "scripts", "rubato.py")):
        if os.path.exists(cand):
            spec = importlib.util.spec_from_file_location("rubato", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("rubato.py not found next to app.py")


rubato = load_rubato()


class RubatoError(Exception):
    pass


def _die(msg: str) -> None:  # the CLI exits on errors; a server must not
    raise RubatoError(msg)


rubato.die = _die

# ---------------------------------------------------------------------------
# Hosted MCP endpoint (/mcp): lets chat apps use Rubato as a connector.
# It works on a link to a video, since a chat app cannot hand over a local file.
# ---------------------------------------------------------------------------
try:
    try:  # mcp 2.x
        from mcp.server.mcpserver import MCPServer as _MCP
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as _MCP
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.types import ToolAnnotations
    mcp_server = _MCP(
        "rubato",
        instructions=(
            "Rubato speeds up a video or audio recording dynamically: slow for takeaways, lists "
            "and key numbers, fast through filler, fastest through dead air. Nothing is cut and "
            "pitch is preserved. Call speed_up_video with a direct link to the file, then call "
            "get_result with the returned job_id every few seconds until its stage is 'done'. "
            f"Limits: {MAX_MINUTES:g} minutes and {MAX_MB:g} MB. If the user only has a local file, "
            "send them to the upload page instead."))
except Exception:  # the page and upload API still work without the mcp package
    mcp_server = None


@contextlib.asynccontextmanager
async def lifespan(_app):
    if mcp_server is None:
        yield
        return
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="Rubato", docs_url=None, redoc_url=None, lifespan=lifespan)
JOBS: dict = {}
LOCK = threading.Lock()
ONE_AT_A_TIME = threading.Semaphore(1)


def options(base: float, slow: float, fast: float, silence: float) -> argparse.Namespace:
    base = min(max(base, 1.0), 2.0)
    slow = min(max(slow, 0.5), base)
    fast = min(max(fast, base), 3.0)
    silence = min(max(silence, fast), 6.0)
    return argparse.Namespace(
        base=base, slow=slow, fast=fast, silence=silence,
        spread=0.30, min_segment=2.0, min_silence=0.6, pad=0.12, silence_db=None,
        busy_motion=0.03, marks=None, transcript=None, no_content=False, cues=None,
        max_key_share=0.5, crf=23, preset="veryfast", vcodec="libx264", audio_bitrate="160k")


def set_stage(job: dict, stage: str) -> None:
    job["stage"] = stage


def run_job(job_id: str) -> None:
    job = JOBS[job_id]
    src, folder = job["src"], job["dir"]
    with ONE_AT_A_TIME:
        try:
            if job.get("url"):
                set_stage(job, "fetching")
                fetch(job["url"], src)
            ff = rubato.find_ffmpeg(None)
            try:
                info = rubato.probe(ff, src)
            except RubatoError:
                raise RubatoError("That file could not be read as video or audio. "
                                  "Try MP4, MOV, WebM, MKV, MP3, M4A or WAV.")
            if not (info["has_audio"] or info["has_video"]):
                raise RubatoError("That file has no video or audio in it.")
            if info["duration"] > MAX_MINUTES * 60:
                raise RubatoError(
                    f"This demo takes recordings up to {MAX_MINUTES:g} minutes; yours is "
                    f"{rubato.fmt_time(info['duration'])}. Install the skill or the CLI for longer ones.")
            o = options(**job["speeds"])

            set_stage(job, "listening")
            an = rubato.analyze(ff, src, use_video=True)

            highlights = words = None
            if info["has_audio"]:
                set_stage(job, "transcribing")
                transcript = os.path.join(folder, "transcript.json")
                if rubato.transcribe(ff, src, transcript, MODEL, job["language"]):
                    cues = rubato.parse_cues(transcript)
                    words = rubato.word_times(cues)
                    highlights = rubato.find_highlights(rubato.sentences(cues), an["duration"])

            set_stage(job, "planning")
            plan = rubato.build_plan(an, o, None, words, highlights)
            segs = rubato.normalise_segments(plan)

            def warp(t: float) -> float:
                return sum(max(0.0, min(t - s["start"], s["end"] - s["start"])) / s["speed"]
                           for s in segs)

            set_stage(job, "rendering")
            kind = "video" if info["has_video"] else "audio"
            out = os.path.join(folder, "rubato.mp4" if kind == "video" else "rubato.m4a")
            rubato.render(ff, src, plan, out, o)

            st = plan["stats"]
            job["result"] = {
                "kind": kind,
                "source_seconds": st["source_seconds"],
                "output_seconds": st["output_seconds"],
                "saved_seconds": round(st["source_seconds"] - st["output_seconds"], 1),
                "effective_speed": st["effective_speed"],
                "flat_seconds": round(st["source_seconds"] / o.base, 1),
                "speeds": {"slow": o.slow, "base": o.base, "fast": o.fast, "silence": o.silence},
                "transcribed": highlights is not None,
                "music": any("constant" in n for n in plan.get("notes", [])),
                "segments": [{"start": round(warp(s["start"]), 2), "end": round(warp(s["end"]), 2),
                              "speed": s["speed"]} for s in segs],
                "highlights": [{"at": round(warp(h["start"]), 2), "kind": h["kind"],
                                "text": h["text"],
                                "speed": o.fast if h["kind"] == "filler" else o.slow}
                               for h in plan.get("highlights", [])],
                "file": f"/api/jobs/{job_id}/file",
                "name": os.path.splitext(job["name"])[0] + ".rubato" + os.path.splitext(out)[1],
            }
            set_stage(job, "done")
        except RubatoError as exc:
            job["error"] = str(exc)
            set_stage(job, "error")
        except Exception as exc:  # never leave a job hanging
            job["error"] = f"Something went wrong while processing ({type(exc).__name__})."
            set_stage(job, "error")
        finally:
            try:
                os.remove(src)  # the upload is not kept once processing ends
            except OSError:
                pass
            job["finished"] = time.time()


def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return bool(infos)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url: str, dst: str) -> None:
    """Download a public http(s) file, refusing private addresses and oversized bodies."""
    limit = int(MAX_MB * 1024 * 1024)
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(6):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise RubatoError("The link must be a public http or https address.")
        if not _public_host(parts.hostname):
            raise RubatoError("That link does not point to a public address.")
        req = urllib.request.Request(url, headers={"User-Agent": "rubato-demo"})
        try:
            resp = opener.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise RubatoError(f"The link could not be downloaded (HTTP {exc.code}).")
        except (urllib.error.URLError, OSError):
            raise RubatoError("The link could not be reached.")
        with resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype.startswith("text/html"):
                raise RubatoError("That link is a web page, not a video file. Use a direct link "
                                  "to the file, or upload it on the site.")
            if int(resp.headers.get("Content-Length") or 0) > limit:
                raise RubatoError(f"The file is larger than {MAX_MB:g} MB.")
            size = 0
            with open(dst, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        return
                    size += len(chunk)
                    if size > limit:
                        raise RubatoError(f"The file is larger than {MAX_MB:g} MB.")
                    f.write(chunk)
    raise RubatoError("Too many redirects.")


def sweep() -> None:
    while True:
        time.sleep(60)
        now = time.time()
        with LOCK:
            old = [k for k, j in JOBS.items() if j.get("finished") and now - j["finished"] > KEEP_SECONDS]
            for k in old:
                shutil.rmtree(JOBS.pop(k)["dir"], ignore_errors=True)


threading.Thread(target=sweep, daemon=True).start()


def start_job(src: str, folder: str, name: str, speeds: dict, language: str | None,
              url: str | None = None) -> str:
    job_id = os.path.basename(folder)
    with LOCK:
        waiting = sum(1 for j in JOBS.values() if j["stage"] not in ("done", "error"))
        JOBS[job_id] = {"stage": "queued", "src": src, "dir": folder, "name": name,
                        "speeds": speeds, "language": language, "ahead": waiting, "url": url}
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job_id


def clean_language(language: str) -> str | None:
    language = (language or "").strip().lower()
    return language if language.isalpha() and 2 <= len(language) <= 3 else None


@app.post("/api/jobs")
async def create_job(request: Request, file: UploadFile = File(...),
                     base: float = Form(1.2), slow: float = Form(1.0), fast: float = Form(1.5),
                     silence: float = Form(2.0), language: str = Form("")):
    limit = int(MAX_MB * 1024 * 1024)
    if int(request.headers.get("content-length") or 0) > limit + 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_MB:g} MB.")
    folder = os.path.join(WORK, uuid.uuid4().hex)
    os.makedirs(folder)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if not ext.replace(".", "").isalnum() or len(ext) > 6:
        ext = ".bin"
    src = os.path.join(folder, "source" + ext)
    size = 0
    with open(src, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                f.close()
                shutil.rmtree(folder, ignore_errors=True)
                raise HTTPException(413, f"File is larger than {MAX_MB:g} MB.")
            f.write(chunk)
    name = os.path.basename(file.filename or "video")[:120]
    job_id = start_job(src, folder, name, {"base": base, "slow": slow, "fast": fast,
                                           "silence": silence}, clean_language(language))
    return {"id": job_id}


@app.post("/api/sample")
async def sample_job():
    sample = os.path.join(STATIC, "sample.m4a")
    if not os.path.exists(sample):
        raise HTTPException(404, "No sample on this server.")
    folder = os.path.join(WORK, uuid.uuid4().hex)
    os.makedirs(folder)
    src = os.path.join(folder, "source.m4a")
    shutil.copy(sample, src)
    return {"id": start_job(src, folder, "pricing-talk-sample.m4a",
                            {"base": 1.2, "slow": 1.0, "fast": 1.5, "silence": 2.0}, "en")}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "This job has expired. Results are kept for 30 minutes.")
    return JSONResponse({"stage": job["stage"], "error": job.get("error"),
                         "result": job.get("result"), "ahead": job.get("ahead", 0)})


@app.get("/api/jobs/{job_id}/file")
async def job_file(job_id: str, download: int = 0):
    job = JOBS.get(job_id)
    if not job or not job.get("result"):
        raise HTTPException(404, "This result has expired.")
    kind = job["result"]["kind"]
    path = os.path.join(job["dir"], "rubato.mp4" if kind == "video" else "rubato.m4a")
    return FileResponse(path, media_type="video/mp4" if kind == "video" else "audio/mp4",
                        filename=job["result"]["name"] if download else None)


def page(name: str) -> str:
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return (f.read().replace("{{MAX_MINUTES}}", f"{MAX_MINUTES:g}")
                .replace("{{MAX_MB}}", f"{MAX_MB:g}").replace("{{SITE_URL}}", SITE_URL)
                .replace("{{REPO}}", REPO))


@app.get("/", response_class=HTMLResponse)
async def index():
    return page("index.html")


@app.get("/connector", response_class=HTMLResponse)
async def connector_docs():
    return page("connector.html")


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return page("privacy.html")


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms():
    return page("llms.txt")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    sitemap = f"\nSitemap: {SITE_URL}/sitemap.xml" if SITE_URL else ""
    return "User-agent: *\nAllow: /\nDisallow: /api/" + sitemap + "\n"


@app.get("/sitemap.xml")
async def sitemap():
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{SITE_URL}/</loc></url><url><loc>{SITE_URL}/connector</loc></url><url><loc>{SITE_URL}/privacy</loc></url></urlset>\n")
    return PlainTextResponse(body, media_type="application/xml")


@app.get("/icon.png")
async def icon():
    return FileResponse(os.path.join(STATIC, "icon.png"), media_type="image/png")


@app.get("/og.svg")
async def og():
    return FileResponse(os.path.join(STATIC, "og.svg"), media_type="image/svg+xml")


def _base_url() -> str:
    return SITE_URL or "http://localhost:" + os.environ.get("PORT", "7860")


if mcp_server is not None:
    @mcp_server.tool(title="Speed up a video dynamically",
                     annotations=ToolAnnotations(title="Speed up a video dynamically",
                                                 readOnlyHint=False, destructiveHint=False,
                                                 idempotentHint=False, openWorldHint=True))
    def speed_up_video(video_url: str, base: float = 1.2, slow: float = 1.0, fast: float = 1.5,
                       silence: float = 2.0, language: str = "") -> dict:
        """Start speeding up a video or audio recording dynamically.

        video_url must be a direct, publicly reachable link to the media file (MP4, MOV,
        WebM, MKV, MP3, M4A, WAV), not a page that embeds a player. Speeds: slow is used
        for takeaways, lists and key numbers; base for ordinary passages; fast for filler;
        silence for dead air. language is the spoken language code (blank detects it).

        Returns a job_id. Processing takes from seconds to a few minutes; get_result
        reports progress and, once finished, the result.
        """
        parts = urllib.parse.urlsplit(video_url.strip())
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return {"stage": "error",
                    "message": "video_url must be a public http or https link that points directly "
                               "to a video or audio file, for example https://example.com/talk.mp4"}
        for label, value, lo, hi in (("base", base, 1.0, 2.0), ("slow", slow, 0.5, 2.0),
                                     ("fast", fast, 1.0, 3.0), ("silence", silence, 1.0, 6.0)):
            if not lo <= value <= hi:
                return {"stage": "error",
                        "message": f"{label} must be between {lo:g} and {hi:g}; got {value:g}"}
        folder = os.path.join(WORK, uuid.uuid4().hex)
        os.makedirs(folder)
        ext = os.path.splitext(parts.path)[1].lower()
        if not ext.replace(".", "").isalnum() or len(ext) > 6:
            ext = ".bin"
        name = os.path.basename(parts.path)[:120] or "video"
        job_id = start_job(os.path.join(folder, "source" + ext), folder, name,
                           {"base": base, "slow": slow, "fast": fast, "silence": silence},
                           clean_language(language), url=video_url.strip())
        return {"job_id": job_id, "stage": "queued",
                "next": "Call get_result with this job_id every few seconds until stage is 'done'."}

    @mcp_server.tool(title="Get the result of a speed-up job",
                     annotations=ToolAnnotations(title="Get the result of a speed-up job",
                                                 readOnlyHint=True, openWorldHint=False))
    def get_result(job_id: str) -> dict:
        """Check a job started with speed_up_video.

        stage is one of queued, fetching, listening, transcribing, planning, rendering,
        done, error. When done, returns the before and after length, the time saved, the
        passages that were slowed down or sped up, and a download link valid for 30 minutes.
        """
        job = JOBS.get(job_id)
        if not job:
            return {"stage": "expired", "message": "No such job. Results are kept for 30 minutes."}
        if job["stage"] == "error":
            return {"stage": "error", "message": job.get("error")}
        if job["stage"] != "done":
            return {"stage": job["stage"], "next": "Not ready yet. Call get_result again in a few seconds."}
        r = job["result"]
        return {
            "stage": "done",
            "download_url": _base_url() + r["file"] + "?download=1",
            "original_length": rubato.fmt_time(r["source_seconds"]),
            "new_length": rubato.fmt_time(r["output_seconds"]),
            "time_saved": rubato.fmt_time(r["saved_seconds"]),
            "average_speed": r["effective_speed"],
            "passages": [{"at_in_new_video": rubato.fmt_time(h["at"]), "kind": h["kind"],
                          "speed": h["speed"], "text": h["text"]} for h in r["highlights"]],
            "note": None if r["transcribed"] else "No speech was transcribed; only pauses changed speed.",
        }

    app.mount("/", mcp_server.streamable_http_app(
        streamable_http_path="/mcp", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "7860")))
