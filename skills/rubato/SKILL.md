---
name: rubato
description: Content-aware dynamic speed for video and audio. Instead of one flat multiplier, slow down for what matters (takeaways, lists, key numbers, important statements, found by reading the transcript) and speed through filler, rambling and dead air, around a baseline (default 1.2x, key parts 1.0x, filler 1.5x, dead air 2x). Use this whenever the user wants to speed up, shorten, tighten or "make less boring" a video, screen recording, lecture, talk, meeting recording, tutorial, podcast or voice memo - including requests like "variable speed", "smart speed", "speed up the boring parts", "don't just put it at 1.5x", "slow down for the important bits" - even if they only ask to "speed it up". Not for cutting content out, jump cuts, or cinematic slow-motion ramps.
compatibility: Needs Python 3.8+ and ffmpeg. Reading the content needs a transcript, from an existing subtitle file or from faster-whisper / the whisper CLI.
---

# Rubato

Rubato is the musician's habit of stretching and squeezing tempo to follow the phrase. This skill does the same to a recording: a baseline speed, slower where something worth catching is said, faster where nothing is.

Everything runs through one script, `scripts/rubato.py` (standard library only, drives ffmpeg). Pitch is preserved, nothing is cut, and audio and picture stay in sync.

## What counts as interesting

Interesting means **content**: the takeaways, the lists, the numbers, the statements the viewer came for. It does not mean loud or animated. So the speed map is built from the transcript, in three layers, each overriding the one before:

1. **Sound and picture** find dead air and flat, halting stretches. These only ever speed things up.
2. **The transcript, by phrase.** The script spots sentences that announce themselves: "the key takeaway", "three things you need to know", "number two", "in summary", "remember", figures and percentages. Those play at the slow speed. Logistics and hesitation ("can you hear me", "give me a second", "thanks for watching") play at the fast speed.
3. **The transcript, by you.** Phrase matching misses every takeaway that is not labelled as one, and cannot tell a tangent from the point. You can. Read the transcript and write marks. This is the layer that makes the result good, so do it whenever the recording is mostly speech.

Without a transcript only layer 1 runs, and the summary says so. Tell the user that the result is then based on sound, not meaning.

## Workflow

### 1. Run it with a transcript

If `uv` is available, this needs nothing installed. It brings ffmpeg and a speech-to-text model with it (the first run downloads the model, about 150 MB):

```bash
uv run --with faster-whisper --with imageio-ffmpeg scripts/rubato.py auto input.mp4 --plan-only
```

With ffmpeg already installed, `python3 scripts/rubato.py auto input.mp4 --plan-only` works too. Either way `auto` looks for a transcript in this order: `--transcript FILE`, then `input.srt` / `input.vtt` / `input.transcript.json` next to the video, then it transcribes by itself if faster-whisper or the `whisper` CLI is present and saves `input.transcript.json`. Pass `--language it` (or any code) if detection gets the language wrong, and `--model small` for better accuracy on hard audio.

`--plan-only` stops before rendering. It writes `input.rubato.plan.json` and prints:

```
source   0:54  ->  output 0:44   (effective 1.217x; flat 1.2x would give 0:45)
speed    |▅▅▅▅▅▅▅▅███▃▂▂▂▂▂▂▂▂▂▂▂▃█▃▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂█▆▂▂▂▂▂▂▂▃█▁▁▁▁▁▁▁▃▆▅▅▅|   low bar = 1x, tall bar = 2x
share    1x 36%  1.2x 33%  1.5x 18%  2x 13%
content  3 filler, 1 list, 1 takeaway   (from the transcript; listed in the plan under "highlights")
```

### 2. Read the transcript and add your marks

Open the transcript and the `highlights` list in the plan. Then write `marks.json` for what the phrase layer got wrong or missed:

```json
[
  {"start": "12:40", "end": "14:05", "label": "key",    "note": "the actual conclusion, never announced as one"},
  {"start": "3:10",  "end": "5:30",  "label": "filler", "note": "tangent about the office move"},
  {"start": "8:02",  "end": "8:20",  "label": "normal", "note": "says 'three things' but it is a joke"},
  {"start": 1530,    "end": 1548,    "speed": 0.9,      "note": "reads a dense formula aloud"}
]
```

Labels: `key` plays at the slow speed, `filler` at the fast speed, `normal` at the baseline (use it to cancel a false highlight), `skip` at the dead-air speed. Times are seconds, `MM:SS` or `HH:MM:SS`. Marks win over everything, including pauses inside them.

What to mark `key`:

- **Takeaways and conclusions**, especially unannounced ones: the sentence you would quote if asked what the video said.
- **Lists and enumerations** in full. The phrase layer catches "number one" but often loses items three and four when the speaker stops counting aloud. Extend the mark to the end of the list.
- **Numbers, results, definitions, names, instructions** the viewer has to act on.
- **The payoff of a demo or a story**, and anything the user said they care about.

What to mark `filler`: greetings and logistics, waiting for something to load, tangents, anecdotes that do not serve the point, repeated explanations, recaps of what was just said, sponsor reads.

Keep `key` to the passages that earn it. If half the recording is slow, nothing stands out and it barely gets shorter.

### 3. Re-plan, show, render

```bash
python3 scripts/rubato.py auto input.mp4 --marks marks.json --plan-only
python3 scripts/rubato.py auto input.mp4 --marks marks.json -o output.mp4
```

Before rendering anything long, show the user the summary and list the passages that will be slowed down and sped up, with a few words each on why. That list is the product; let them correct it.

`plan.json` can also be edited by hand: `segments` is a plain list of `{start, end, speed}`, gaps are filled with the baseline, `rubato.py show plan.json` reprints the summary, and `rubato.py render input.mp4 plan.json -o output.mp4` renders it. Each step is also available on its own (`transcribe`, `analyze`, `plan`, `render`).

Subtitles can be retimed to the new cut:

```bash
python3 scripts/rubato.py remap-srt plan.json input.srt -o output.srt
```

## Tuning

| The user wants | Flags |
| --- | --- |
| A different baseline, e.g. "around 1.3x" | `--base 1.3` (move `--fast` and `--slow` with it) |
| More aggressive on boring parts | `--fast 1.75`, `--silence 3` |
| Real slow-down on the key parts | `--slow 0.9` |
| Key parts at baseline, never slower | `--slow` equal to `--base` |
| Pauses treated like any dull part, not 2x | `--silence` equal to `--fast` |
| Fewer, longer speed changes | `--min-segment 4` |
| Their own trigger phrases, or another language | `--cues cues.json` with `{"key": ["regex"], "filler": ["regex"]}` |
| Only their marks, no phrase matching | `--no-content` |
| Pauses not detected, or noise counted as speech | `--silence-db -35` (dBFS; default is adaptive) |

Defaults are `--slow 1.0 --base 1.2 --fast 1.5 --silence 2.0`. Speech stays comfortably intelligible up to roughly 1.75x; go past that only for dead air or when the user asks.

## Things to know

- **Languages.** The built-in phrases are English. For any other language the transcript still works, so rely on your marks, and add recurring phrases with `--cues`.
- **Music and constant background noise** hide pauses. The plan prints a note; rely on the transcript and marks, or pass `--silence-db`.
- **Screen recordings and demos.** A quiet stretch with a lot happening on screen counts as action (fast speed), not dead air. A silent demo has no transcript to read, so mark its payoff moments yourself.
- **Audio-only input** works. Give an audio output name (`.m4a`, `.mp3`, `.wav`).
- **Output** is H.264 8-bit with stereo AAC at the source frame rate. HDR, surround, extra audio tracks and embedded subtitle streams are not carried over.
- **Length.** A 25 minute file with about 500 speed changes renders in well under a minute on a laptop. Rendering needs temporary disk space for the audio, roughly 700 MB per hour of output.
- The source file is never modified, and the script refuses to write over it.
