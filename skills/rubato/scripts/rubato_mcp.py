#!/usr/bin/env python3
"""Rubato MCP server: dynamic video speed as tools for Claude and other MCP clients.

Run (no install needed):

    uvx --from git+https://github.com/andreolf/rubato rubato-mcp

Tools work on files on the machine the server runs on. The intended flow is
rubato_plan -> (read the transcript, decide marks) -> rubato_plan again with
marks -> rubato_render.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP

try:
    import rubato
except ImportError:  # run straight from the repo
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import rubato


class RubatoError(Exception):
    pass


def _die(msg: str) -> None:  # the CLI exits on errors; a server must report them
    raise RubatoError(msg)


rubato.die = _die

mcp = FastMCP(
    "rubato",
    instructions=(
        "Rubato changes the speed of a video or audio file passage by passage: slow for "
        "takeaways, lists and key numbers, fast through filler, fastest through dead air. "
        "Nothing is cut and pitch is preserved. Call rubato_plan first; it transcribes and "
        "returns the speed map plus the passages it recognised. Then read the transcript with "
        "rubato_transcript and, where its automatic picks are wrong or incomplete, call "
        "rubato_plan again with marks (key = slow, filler = fast, normal = baseline). Show the "
        "user the before/after length and what will be slowed down, then call rubato_render."))


def _paths(input_path: str) -> tuple:
    src = os.path.abspath(os.path.expanduser(input_path))
    if not os.path.isfile(src):
        raise RubatoError(f"file not found: {src}")
    stem, ext = os.path.splitext(src)
    return src, stem, ext


def _options(base, slow, fast, silence) -> argparse.Namespace:
    return argparse.Namespace(
        base=base, slow=slow, fast=fast, silence=silence, spread=0.30, min_segment=2.0,
        min_silence=0.6, pad=0.12, silence_db=None, busy_motion=0.03, max_key_share=0.5,
        crf=18, preset="medium", vcodec="libx264", audio_bitrate="192k")


def _transcript_for(ff: str, src: str, stem: str, language: str | None) -> str | None:
    found = rubato.sidecar_transcript(src)
    if found:
        return found
    made = stem + ".transcript.json"
    return made if rubato.transcribe(ff, src, made, "base", language or None) else None


@mcp.tool()
def rubato_plan(input_path: str, base: float = 1.2, slow: float = 1.0, fast: float = 1.5,
                silence: float = 2.0, marks: list[dict] | None = None,
                language: str = "") -> dict:
    """Analyse a video or audio file and build its speed map, without rendering.

    Transcribes the file if no transcript sits next to it, finds pauses, and picks
    takeaways, lists, key numbers and filler from the wording.

    marks: optional overrides from reading the transcript yourself, each
      {"start": seconds or "MM:SS", "end": ..., "label": "key" | "filler" | "normal" | "skip"}
      or {"start": ..., "end": ..., "speed": 0.9}. Marks beat everything else.
    language: spoken language code such as "en" or "it"; blank detects it.

    Returns the summary, the recognised passages and the path of the saved plan
    to pass to rubato_render.
    """
    with contextlib.redirect_stdout(sys.stderr):
        src, stem, _ = _paths(input_path)
        ff = rubato.find_ffmpeg(None)
        an = rubato.analyze(ff, src)
        transcript = _transcript_for(ff, src, stem, language) if an["has_audio"] else None
        words = highlights = None
        if transcript:
            cues = rubato.parse_cues(transcript)
            words = rubato.word_times(cues)
            highlights = rubato.find_highlights(rubato.sentences(cues), an["duration"])
        parsed = None
        if marks:
            parsed = [{"start": rubato.parse_time(m["start"]), "end": rubato.parse_time(m["end"]),
                       "label": m.get("label"), "speed": m.get("speed"), "note": m.get("note")}
                      for m in marks]
        plan = rubato.build_plan(an, _options(base, slow, fast, silence), parsed, words, highlights)
        if not transcript:
            plan["notes"].append("no transcript: speeds follow sound and picture only, not what is said")
        plan_path = stem + ".rubato.plan.json"
        rubato.save_json(plan, plan_path)
        st = plan["stats"]
        return {
            "plan_path": plan_path,
            "transcript_path": transcript,
            "source_length": rubato.fmt_time(st["source_seconds"]),
            "output_length": rubato.fmt_time(st["output_seconds"]),
            "effective_speed": st["effective_speed"],
            "summary": rubato.summary(plan),
            "recognised_passages": [
                {"at": rubato.fmt_time(h["start"]), "start": h["start"], "end": h["end"],
                 "kind": h["kind"], "text": h["text"]} for h in plan.get("highlights", [])],
            "marks_applied": len(parsed or []),
        }


@mcp.tool()
def rubato_transcript(input_path: str, language: str = "") -> str:
    """Return the timestamped transcript of a video or audio file (transcribing it if
    needed), so you can find the takeaways, complete lists and tangents that
    rubato_plan's phrase matching missed, and pass them back as marks."""
    with contextlib.redirect_stdout(sys.stderr):
        src, stem, _ = _paths(input_path)
        ff = rubato.find_ffmpeg(None)
        transcript = _transcript_for(ff, src, stem, language)
        if not transcript:
            raise RubatoError("no speech-to-text engine available and no transcript file "
                              "next to the input")
        lines = [f"[{rubato.fmt_time(s)}] {text}"
                 for s, _, text in rubato.sentences(rubato.parse_cues(transcript)) if text]
        return "\n".join(lines)


@mcp.tool()
def rubato_render(input_path: str, plan_path: str = "", output_path: str = "") -> dict:
    """Render the file at dynamic speed from a plan made by rubato_plan.

    plan_path defaults to the plan saved next to the input; output_path defaults
    to "<name>.rubato.<ext>" next to the input. The source is never modified.
    Rendering a long recording can take a few minutes.
    """
    with contextlib.redirect_stdout(sys.stderr):
        src, stem, ext = _paths(input_path)
        plan_file = os.path.expanduser(plan_path) if plan_path else stem + ".rubato.plan.json"
        if not os.path.isfile(plan_file):
            raise RubatoError(f"plan not found: {plan_file}. Call rubato_plan first.")
        with open(plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        out = os.path.abspath(os.path.expanduser(output_path)) if output_path \
            else f"{stem}.rubato{ext or '.mp4'}"
        rubato.render(rubato.find_ffmpeg(None), src, plan, out, _options(1.2, 1.0, 1.5, 2.0))
        st = rubato.plan_stats(plan)
        return {"output_path": out,
                "source_length": rubato.fmt_time(st["source_seconds"]),
                "output_length": rubato.fmt_time(st["output_seconds"]),
                "effective_speed": st["effective_speed"]}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
