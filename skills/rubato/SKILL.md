---
name: rubato
description: Content-aware dynamic speed for video and audio. Instead of one flat multiplier, play dull stretches faster and dense or important stretches slower around a baseline (default 1.2x, dull 1.5x, lively 1.0x, dead air 2x). Use this whenever the user wants to speed up, shorten, tighten or "make less boring" a video, screen recording, lecture, talk, meeting recording, tutorial, podcast or voice memo - including requests like "variable speed", "smart speed", "speed ramp the boring parts", "don't just put it at 1.5x", "slow down for the important bits" - even if they only ask to "speed it up". Not for cutting content out, jump cuts, or cinematic slow-motion ramps.
compatibility: Needs Python 3.8+ and ffmpeg. No other dependencies.
---

# Rubato

Rubato is the musician's habit of stretching and squeezing tempo to follow the phrase. This skill does the same to a recording: a baseline speed, faster where little is happening, slower where a lot is.

Everything runs through one script, `scripts/rubato.py` (standard library only, drives ffmpeg). Pitch is preserved, nothing is cut, and audio and picture stay in sync.

## Two layers of "boring"

The script measures signals: loudness, pauses, how densely someone is talking, how much the picture changes, and words per second if it gets a transcript. Those are decent proxies. Halting, quiet, static stretches go faster, dense and animated ones go slower, and dead air goes fastest.

Signals cannot know that a quiet sentence is the thesis of the talk, or that an energetic two minutes is a sponsor read. That judgement is yours. When a transcript exists or can be made, read it and write **marks** that override the signals. This is what separates a good result from a merely plausible one, so do it whenever the recording is mostly speech and matters to the user.

## Workflow

### 1. Check ffmpeg

The script finds ffmpeg on `PATH`, in `$RUBATO_FFMPEG`, or via `--ffmpeg`. If none is installed, either ask the user to install it (`brew install ffmpeg`, `apt install ffmpeg`) or, when `uv` is available, run the script as `uv run --with imageio-ffmpeg scripts/rubato.py ...`, which brings its own ffmpeg binary.

### 2. Quick pass (signals only)

```bash
python3 scripts/rubato.py auto input.mp4 -o output.mp4
```

This analyses, writes `output.plan.json`, prints a summary and renders. Add `--plan-only` to stop before rendering, which is the right first step on anything long: show the user the summary and let them react before spending the encode time.

The summary looks like this:

```
source   25:16  ->  output 18:50   (effective 1.341x; flat 1.2x would give 21:04)
speed    |▂▂▂▂▁▁▁▁▂██████▇▅▅▅▅▅▅▇███████▆▂▂▂▂▂▂▇█|   low bar = 1x, tall bar = 2x
share    1x 14%  1.2x 41%  1.5x 23%  2x 22%
segments 514
```

### 3. Full pass (signals + your judgement)

```bash
python3 scripts/rubato.py analyze input.mp4 -o analysis.json
# get a transcript, read it, write marks.json (see below)
python3 scripts/rubato.py plan analysis.json -o plan.json --marks marks.json --transcript input.srt
python3 scripts/rubato.py render input.mp4 plan.json -o output.mp4
```

**Getting a transcript.** Use one the user already has (`.srt`, `.vtt`, or Whisper-style `.json` sitting next to the video). Otherwise use whatever speech-to-text is installed (`whisper`, `whisper-cli`, `mlx_whisper`, `faster-whisper`) with SRT or JSON output. If nothing is available, say so and continue with the quick pass rather than installing a model unasked.

**Writing marks.** `marks.json` is a list of time ranges with a label or an explicit speed:

```json
[
  {"start": "12:40", "end": "14:05", "label": "key",    "note": "states the main result"},
  {"start": "3:10",  "end": "5:30",  "label": "filler", "note": "audio check and housekeeping"},
  {"start": 1530,    "end": 1548,    "speed": 0.9,      "note": "reads a dense formula aloud"}
]
```

Labels: `key` plays at the slow speed, `filler` at the fast speed, `normal` at the baseline, `skip` at the dead-air speed. Times are seconds, `MM:SS` or `HH:MM:SS`. Marks win over everything, including pauses inside them, so a dramatic pause in a key passage survives.

What tends to deserve `key`: the thesis, definitions, numbers and results, the payoff of a demo, a punchline, instructions the viewer has to follow, anything the user told you they care about. What tends to be `filler`: greetings and logistics, waiting for something to load, repeated explanations, recaps of what was just said, tangents, sponsor reads.

Mark sparingly. If more than about a quarter of the recording is `key`, nothing stands out and the video barely gets shorter. Leave the ordinary middle to the signals.

### 4. Show, adjust, render

Tell the user the before and after durations and the effective speed, and name the stretches you marked and why. If they want changes, either re-plan with different numbers or edit `plan.json` directly: `segments` is a plain list of `{start, end, speed}`, gaps are filled with the baseline, and `python3 scripts/rubato.py show plan.json` reprints the summary after edits.

If there are subtitles, retime them to the new cut:

```bash
python3 scripts/rubato.py remap-srt plan.json input.srt -o output.srt
```

## Tuning

Translate what the user says into these flags (on `auto` or `plan`):

| The user wants | Flags |
| --- | --- |
| A different baseline, e.g. "around 1.3x" | `--base 1.3` (move `--fast` and `--slow` with it) |
| More aggressive on boring parts | `--fast 1.75`, `--silence 3` |
| Never slower than baseline | `--slow` equal to `--base` |
| Real slow-down on the good parts | `--slow 0.9` |
| More of the video away from baseline | `--spread 0.4` (default 0.30, max 0.5) |
| Only pauses change speed | `--spread 0` |
| Pauses treated like any dull part, not 2x | `--silence` equal to `--fast` |
| Fewer, longer speed changes | `--min-segment 4` |
| Pauses not detected, or noise counted as speech | `--silence-db -35` (dBFS; default is adaptive) |

The defaults are `--slow 1.0 --base 1.2 --fast 1.5 --silence 2.0`. Speech stays comfortably intelligible up to roughly 1.75x; go past that only for dead air or when the user asks.

## Things to know

- **Honest framing.** Without marks, "interesting" means loud, dense and visually active. Say so if the user asks how it decides.
- **Music and constant background noise** hide pauses. The plan prints a note when it sees this; rely on marks, or pass `--silence-db`.
- **Screen recordings and demos.** A quiet stretch with a lot happening on screen is treated as action (fast speed), not dead air. `--busy-motion` sets how much change counts.
- **Audio-only input** works too. Give an audio output name (`.m4a`, `.mp3`, `.wav`).
- **Output** is H.264 8-bit with stereo AAC, at the source frame rate. HDR, surround layouts, extra audio tracks and embedded subtitle streams are not carried over.
- **Length.** A 25 minute file with about 500 speed changes renders in well under a minute on a laptop. Rendering needs temporary disk space for the audio, roughly 700 MB per hour of output.
- The source file is never modified, and the script refuses to write over it.
