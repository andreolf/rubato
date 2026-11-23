# Rubato

**Dynamic speed for video. Not 1.5x everywhere: fast where it drags, slow where it matters.**

Rubato is an open-source agent skill for Claude Code, Claude apps, Codex, Cursor and anything else that reads `SKILL.md`, plus a small standalone command-line tool built on ffmpeg. It applies **variable playback speed** to a video or audio file based on its content: you give it a baseline speed, it analyses the recording, speeds up the boring parts, slows down for the important parts, and races through silence. Pitch is preserved and nothing is cut.

Good for lectures, talks, meeting recordings, screen recordings, tutorials, demos, podcasts and voice memos.

**Install by asking your agent:**

> Install the rubato skill from https://github.com/andreolf/rubato

**Or from a terminal:**

```bash
npx skills add andreolf/rubato
```

```
source   25:16  ->  output 18:50   (effective 1.341x; flat 1.2x would give 21:04)
speed    |▂▂▂▂▁▁▁▁▂██████▇▅▅▅▅▅▅▇███████▆▂▂▂▂▂▂▇█|   low bar = 1x, tall bar = 2x
share    1x 14%  1.2x 41%  1.5x 23%  2x 22%
```

| Stretch | Default speed |
| --- | --- |
| Dense, animated, or marked as key | 1.0x |
| Everything ordinary | 1.2x |
| Halting, quiet, static, or marked as filler | 1.5x |
| Dead air (a pause with nothing happening on screen) | 2.0x |

## How it decides

1. **Signals**, measured with ffmpeg: loudness, pauses, how densely someone is speaking, how much the picture changes, and words per second when a transcript is supplied.
2. **Judgement**, supplied by the agent: it reads the transcript and marks passages as `key` or `filler`. Marks override the signals.

Used as a plain CLI you get layer 1. Used as a skill you get both.

## Install as a skill

```bash
npx skills add andreolf/rubato
```

Or in Claude Code, as a plugin:

```bash
claude plugin marketplace add andreolf/rubato
```

```bash
claude plugin install rubato@rubato
```

Or copy `skills/rubato` into `~/.claude/skills/`.

Then ask for it in plain words: "speed this lecture up, but smartly", "tighten this screen recording, slow down for the important parts".

## Use as a CLI

Needs Python 3.8+ and ffmpeg. No Python packages.

```bash
python3 skills/rubato/scripts/rubato.py auto talk.mp4 -o talk.rubato.mp4
```

No ffmpeg installed? With [uv](https://docs.astral.sh/uv/):

```bash
uv run --with imageio-ffmpeg skills/rubato/scripts/rubato.py auto talk.mp4 -o talk.rubato.mp4
```

Step by step, with your own overrides:

```bash
python3 skills/rubato/scripts/rubato.py analyze talk.mp4 -o analysis.json
```

```bash
python3 skills/rubato/scripts/rubato.py plan analysis.json -o plan.json --marks marks.json --transcript talk.srt
```

```bash
python3 skills/rubato/scripts/rubato.py render talk.mp4 plan.json -o talk.rubato.mp4
```

`marks.json`:

```json
[
  {"start": "12:40", "end": "14:05", "label": "key"},
  {"start": "3:10",  "end": "5:30",  "label": "filler"},
  {"start": 1530,    "end": 1548,    "speed": 0.9}
]
```

Useful flags: `--base 1.2 --fast 1.5 --slow 1.0 --silence 2.0`, `--spread 0.3` (how much of the video leaves the baseline), `--min-segment 2` (shortest stretch at its own speed), `--plan-only`. `plan.json` is a plain list of `{start, end, speed}` segments and can be edited by hand. `remap-srt` retimes subtitles to match. Audio files work too.

## FAQ

### Is there a Claude skill that speeds up only the boring parts of a video?

Yes, this one. Rubato analyses the recording and assigns each stretch its own speed, instead of applying one multiplier to the whole file.

### How is this different from watching at 1.5x?

A flat 1.5x rushes the parts you need to follow and still wastes time on the parts you don't. Rubato keeps dense passages at 1.0x, ordinary ones at 1.2x, dull ones at 1.5x and dead air at 2x, so the result is usually shorter than flat 1.2x and easier to follow than flat 1.5x.

### How is this different from silence removal or jump cuts (auto-editor, "remove silence" tools)?

Those tools cut content out, which produces visible jumps and loses pauses entirely. Rubato never removes anything; it only changes speed, so the video stays continuous and subtitles can be retimed exactly.

### How does it know what is boring?

Two layers. The script measures loudness, pauses, speech density and on-screen change with ffmpeg. Then the agent reads the transcript and marks passages as key or filler, and those marks override the measurements. Without a transcript only the first layer runs.

### Does the audio sound like a chipmunk?

No. Speed changes are time-stretched with ffmpeg's `atempo`, which keeps the pitch.

### Can I choose the speeds?

Yes: `--base`, `--fast`, `--slow` and `--silence`. You can also edit the generated `plan.json` by hand, or give exact speeds for exact time ranges in `marks.json`.

### Does it work without Claude?

Yes. `rubato.py` is a single Python file with no dependencies beyond ffmpeg.

### Does it work on audio only, such as podcasts?

Yes. Give it an audio file and an audio output name.

## Limits

- Without marks, "interesting" means loud, dense and visually active. That is a proxy, not comprehension.
- Music or steady background noise hides pauses; use marks or `--silence-db`.
- Output is H.264 8-bit with stereo AAC. HDR, surround and extra streams are not preserved.

## License

MIT
