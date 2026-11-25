"""Rubato demo: upload a video, get it back at dynamic speed.

Runs the same rubato.py that ships with the skill. Meant for a Hugging Face
Space (CPU), and runs locally with:

    uv run --with gradio --with faster-whisper --with imageio-ffmpeg space/app.py
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import tempfile

import gradio as gr

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_MINUTES = float(os.environ.get("RUBATO_MAX_MINUTES", "15"))
MODEL = os.environ.get("RUBATO_MODEL", "base")
REPO = "https://github.com/andreolf/rubato"


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


def _die(msg: str) -> None:  # the CLI exits on errors; a web app must not
    raise RubatoError(msg)


rubato.die = _die


def options(base: float, slow: float, fast: float, silence: float) -> argparse.Namespace:
    return argparse.Namespace(
        base=base, slow=min(slow, base), fast=max(fast, base), silence=max(silence, fast, base),
        spread=0.30, min_segment=2.0, min_silence=0.6, pad=0.12, silence_db=None,
        busy_motion=0.03, marks=None, transcript=None, no_content=False, cues=None,
        max_key_share=0.5, crf=23, preset="veryfast", vcodec="libx264", audio_bitrate="160k")


LABEL = {"takeaway": "Takeaway", "list": "List", "number": "Key numbers", "filler": "Filler"}


def process(video, base, slow, fast, silence, language, progress=gr.Progress()):
    if not video:
        raise gr.Error("Upload a video or audio file first.")
    work = tempfile.mkdtemp(prefix="rubato-demo-")
    try:
        ff = rubato.find_ffmpeg(None)
        info = rubato.probe(ff, video)
        if info["duration"] > MAX_MINUTES * 60:
            raise gr.Error(f"This demo takes files up to {MAX_MINUTES:g} minutes. "
                           f"For longer recordings, install the skill or the CLI: {REPO}")
        o = options(base, slow, fast, silence)

        progress(0.05, desc="Listening for pauses")
        an = rubato.analyze(ff, video, use_video=True)

        highlights = words = None
        transcript = os.path.join(work, "transcript.json")
        if info["has_audio"]:
            progress(0.25, desc="Transcribing")
            if rubato.transcribe(ff, video, transcript, MODEL, (language or "").strip() or None):
                cues = rubato.parse_cues(transcript)
                words = rubato.word_times(cues)
                highlights = rubato.find_highlights(rubato.sentences(cues), an["duration"])

        progress(0.6, desc="Planning speeds")
        plan = rubato.build_plan(an, o, None, words, highlights)
        if highlights is None:
            plan["notes"].append("no transcript: speeds follow sound and picture only")

        progress(0.7, desc="Rendering")
        ext = ".mp4" if info["has_video"] else ".m4a"
        out = os.path.join(tempfile.gettempdir(), f"rubato-{os.path.basename(work)}{ext}")
        rubato.render(ff, video, plan, out, o)

        st = plan["stats"]
        saved = st["source_seconds"] - st["output_seconds"]
        head = (f"### {rubato.fmt_time(st['source_seconds'])} → {rubato.fmt_time(st['output_seconds'])}"
                f"  ·  {rubato.fmt_time(saved)} saved  ·  {st['effective_speed']}x on average\n\n"
                "```\n" + "\n".join(l for l in rubato.summary(plan, width=56).splitlines()
                                      if l.startswith(("speed", "share", "note"))) + "\n```")
        rows = [[rubato.fmt_time(h["start"]), LABEL.get(h["kind"], h["kind"]),
                 f"{(o.fast if h['kind'] == 'filler' else o.slow):g}x", h["text"]]
                for h in plan.get("highlights", [])]
        if not rows:
            head += ("\n\nNo takeaways, lists or filler were recognised by phrase, so only pauses and "
                     "flat stretches changed speed. Used as a skill, Claude reads the transcript and "
                     "marks them itself.")
        return (out if info["has_video"] else None), (None if info["has_video"] else out), head, rows
    except RubatoError as exc:
        raise gr.Error(str(exc))
    finally:
        shutil.rmtree(work, ignore_errors=True)


INTRO = f"""
# Rubato
**Dynamic speed for video. Not 1.5x everywhere: slow for the takeaways, fast through the filler.**

Upload a talk, lecture, meeting or screen recording. Rubato transcribes it, slows down for takeaways,
lists and key numbers, speeds through filler, and races through silence. Pitch is kept and nothing is cut.

This demo takes files up to {MAX_MINUTES:g} minutes and recognises English phrasing. For longer
recordings, other languages and smarter picks, [install the skill or the CLI]({REPO}).
"""

OUTRO = f"""
**Privacy:** your file is processed on this server and the working files are deleted when the run ends.
Do not upload anything confidential to a public demo.

**Like it?** [Star Rubato on GitHub]({REPO}) · Install as a skill: `npx skills add andreolf/rubato`
"""

with gr.Blocks(title="Rubato: dynamic speed for video") as demo:
    gr.Markdown(INTRO)
    with gr.Row():
        with gr.Column():
            video = gr.File(label="Video or audio file", type="filepath",
                            file_types=["video", "audio"])
            with gr.Accordion("Speeds", open=False):
                base = gr.Slider(1.0, 1.6, value=1.2, step=0.05, label="Baseline")
                slow = gr.Slider(0.8, 1.3, value=1.0, step=0.05, label="Takeaways, lists, key numbers")
                fast = gr.Slider(1.2, 2.0, value=1.5, step=0.05, label="Filler and flat stretches")
                silence = gr.Slider(1.5, 4.0, value=2.0, step=0.25, label="Dead air")
                language = gr.Textbox(label="Spoken language code (blank = detect)", placeholder="en")
            go = gr.Button("Make it Rubato", variant="primary")
        with gr.Column():
            out_video = gr.Video(label="Result")
            out_audio = gr.Audio(label="Result (audio)")
            stats = gr.Markdown()
    table = gr.Dataframe(headers=["At", "What", "Speed", "What was said"], label="What it picked up",
                         wrap=True, interactive=False)
    gr.Markdown(OUTRO)
    go.click(process, [video, base, slow, fast, silence, language],
             [out_video, out_audio, stats, table], concurrency_limit=1)

if __name__ == "__main__":
    demo.queue(max_size=8).launch()
