# Rubato

**Dynamic speed for video. Not 1.5x everywhere: fast where it drags, slow where it matters.**

Rubato is an agent skill (Claude Code, Claude apps, Codex, Cursor, anything that reads `SKILL.md`) plus a small standalone command-line tool. You give it a baseline speed. It analyses the recording, speeds up the dull stretches, eases off on the dense ones, and races through dead air. Pitch is preserved and nothing is cut.

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

## Limits

- Without marks, "interesting" means loud, dense and visually active. That is a proxy, not comprehension.
- Music or steady background noise hides pauses; use marks or `--silence-db`.
- Output is H.264 8-bit with stereo AAC. HDR, surround and extra streams are not preserved.

## License

MIT
