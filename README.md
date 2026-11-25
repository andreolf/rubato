# Rubato

**Speed up your videos dynamically and save time. Not 1.5x everywhere: slow for the takeaways, fast through the filler.**

Rubato is an open-source agent skill for Claude Code, Claude apps, Codex, Cursor and anything else that reads `SKILL.md`, an MCP server, a command-line tool built on ffmpeg, and a web demo. It applies **variable playback speed** to a video or audio file based on what is being said: you give it a baseline speed, it transcribes the recording, slows down for the takeaways, lists and key numbers, speeds up the filler and rambling, and races through silence. Pitch is preserved and nothing is cut.

Good for lectures, talks, meeting recordings, screen recordings, tutorials, demos, podcasts and voice memos.

**Try it in your browser, no install:** https://www.tryrubato.com

**Install by asking your agent:**

> Install the rubato skill from https://github.com/andreolf/rubato

**Or from a terminal:**

```bash
npx skills add andreolf/rubato
```

```
source   0:54  ->  output 0:44   (effective 1.217x; flat 1.2x would give 0:45)
speed    |▅▅▅▅▅▅▅▅███▃▂▂▂▂▂▂▂▂▂▂▂▃█▃▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂█▆▂▂▂▂▂▂▂▃█▁▁▁▁▁▁▁▃▆▅▅▅|   low bar = 1x, tall bar = 2x
share    1x 36%  1.2x 33%  1.5x 18%  2x 13%
content  3 filler, 1 list, 1 takeaway   (from the transcript)
```

| What is happening | Default speed |
| --- | --- |
| A takeaway, a list, key numbers, anything marked as key | 1.0x |
| Everything ordinary | 1.2x |
| Logistics, hesitation, flat stretches, anything marked as filler | 1.5x |
| Dead air (a pause with nothing happening on screen) | 2.0x |

## How it decides

Interesting means content, not volume. Three layers, each overriding the one before:

1. **Sound and picture**, measured with ffmpeg, find dead air and flat, halting stretches. These only ever speed things up.
2. **The transcript, by phrase.** Rubato transcribes the recording (or reads your subtitle file) and spots the sentences that announce themselves: "the key takeaway", "three things you need to know", "number two", "in summary", "remember", figures and percentages. Those slow down. "Can you hear me", "give me a second" and "thanks for watching" speed up.
3. **The transcript, by the agent.** Phrase matching misses every takeaway that is not labelled as one. Used as a skill, the agent reads the transcript and marks the real conclusions, the full lists and the tangents. Its marks override everything.

Used as a plain CLI you get layers 1 and 2. Used as a skill you get all three.

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

## Use as an MCP server

For Claude Desktop, Claude Code, Cursor and any other MCP client. Nothing to install first; [uv](https://docs.astral.sh/uv/) fetches it:

```json
{
  "mcpServers": {
    "rubato": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/andreolf/rubato", "rubato-mcp"]
    }
  }
}
```

In Claude Code:

```bash
claude mcp add rubato -- uvx --from git+https://github.com/andreolf/rubato rubato-mcp
```

It exposes three tools that work on files on your machine:

| Tool | What it does |
| --- | --- |
| `rubato_plan` | Transcribes, finds pauses, picks takeaways, lists and filler, and returns the speed map. Accepts marks. |
| `rubato_transcript` | Returns the timestamped transcript so the model can find what phrase matching missed. |
| `rubato_render` | Renders the file from the plan. |

## Web demo

Live at https://www.tryrubato.com (files up to 15 minutes). `space/` holds its source: a landing page with an upload box and a small job API (FastAPI), deployed as a Docker app on a Hugging Face Space with `sh space/deploy.sh`. Run it locally:

```bash
uv run --with fastapi --with uvicorn --with python-multipart --with faster-whisper --with imageio-ffmpeg space/app.py
```

## Use as a CLI

Run it straight from GitHub, with ffmpeg and speech-to-text included:

```bash
uvx --from git+https://github.com/andreolf/rubato rubato auto talk.mp4
```

Or from a clone of this repository:


This needs only [uv](https://docs.astral.sh/uv/). It brings ffmpeg and a speech-to-text model with it (about 150 MB on first run):

```bash
uv run --with faster-whisper --with imageio-ffmpeg skills/rubato/scripts/rubato.py auto talk.mp4
```

That transcribes, plans and writes `talk.rubato.mp4` next to the original. Add `--plan-only` to see the speed map and the detected highlights without rendering.

With ffmpeg already installed, plain Python works and needs no packages:

```bash
python3 skills/rubato/scripts/rubato.py auto talk.mp4
```

In that case Rubato reads `talk.srt`, `talk.vtt` or `--transcript FILE` if there is one, and uses the `whisper` command if it is installed. With no transcript at all it falls back to sound and picture only, and says so.

Your own overrides go in a marks file, passed with `--marks marks.json`:

```json
[
  {"start": "12:40", "end": "14:05", "label": "key"},
  {"start": "3:10",  "end": "5:30",  "label": "filler"},
  {"start": 1530,    "end": 1548,    "speed": 0.9}
]
```

Useful flags: `--base 1.2 --fast 1.5 --slow 1.0 --silence 2.0`, `--min-segment 2` (shortest stretch at its own speed), `--language it`, `--model small`, `--cues cues.json` (your own trigger phrases, or another language), `--plan-only`. The steps also exist separately as `transcribe`, `analyze`, `plan` and `render`. `plan.json` is a plain list of `{start, end, speed}` segments and can be edited by hand. `remap-srt` retimes subtitles to match. Audio files work too.

## FAQ

### Is there a Claude skill that speeds up only the boring parts of a video?

Yes, this one. Rubato transcribes the recording and assigns each stretch its own speed, slowing down for takeaways and lists and speeding through filler, instead of applying one multiplier to the whole file.

### How is this different from watching at 1.5x?

A flat 1.5x rushes the parts you need to follow and still wastes time on the parts you don't. Rubato keeps takeaways, lists and key numbers at 1.0x, ordinary passages at 1.2x, filler at 1.5x and dead air at 2x.

### How is this different from silence removal or jump cuts (auto-editor, "remove silence" tools)?

Those tools cut content out, which produces visible jumps and loses pauses entirely. Rubato never removes anything; it only changes speed, so the video stays continuous and subtitles can be retimed exactly.

### How does it know what is important and what is boring?

It reads the transcript. Sentences that announce a takeaway, start or continue a list, or carry numbers are slowed down; logistics and hesitation are sped up; pauses and flat stretches are found from the audio. When Rubato runs as a skill, the agent also reads the whole transcript and marks the important passages that no phrase gives away. Without a transcript only the audio and picture layer runs.

### Does it work in languages other than English?

Transcription works in any language Whisper supports. The built-in trigger phrases are English, so for other languages add your own with `--cues`, or use it as a skill and let the agent mark the transcript.

### Does the audio sound like a chipmunk?

No. Speed changes are time-stretched with ffmpeg's `atempo`, which keeps the pitch.

### Can I choose the speeds?

Yes: `--base`, `--fast`, `--slow` and `--silence`. You can also edit the generated `plan.json` by hand, or give exact speeds for exact time ranges in `marks.json`.

### Is there an MCP server for speeding up videos?

Yes. Rubato ships one: `uvx --from git+https://github.com/andreolf/rubato rubato-mcp`. See "Use as an MCP server" above.

### Does it work without Claude?

Yes. `rubato.py` is a single Python file. It needs ffmpeg, plus a transcript or a Whisper install for the content layer.

### Does it work on audio only, such as podcasts?

Yes. Give it an audio file and an audio output name.

## Limits

- On its own, the CLI recognises important passages by how they are phrased. A takeaway that is never announced as one needs the agent's marks, or yours.
- Built-in phrases are English; see the FAQ for other languages.
- A silent screen recording has nothing to transcribe, so only pauses and on-screen activity drive it.
- Music or steady background noise hides pauses; use marks or `--silence-db`.
- Output is H.264 8-bit with stereo AAC. HDR, surround and extra streams are not preserved.

## License

MIT
