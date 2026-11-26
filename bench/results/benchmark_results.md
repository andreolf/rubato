# Rubato Benchmark Results

- **CPU**: Intel(R) Xeon(R) Processor (8 vCPUs), 15.6 GB RAM, no GPU
- **OS**: Linux-6.12.113+-x86_64-with-glibc2.41
- **ffmpeg**: ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers
- **faster-whisper**: 1.2.1 (ctranslate2 4.8.4)
- **Rubato commit**: b863ed2827f3278fc3851d9012440a2f0f5924b4

**How to read it.** *WER* = word error rate of the Rubato output's transcript against the original's transcript, both made by the same judge (faster-whisper `small.en`, batched, beam 5, temperature 0). 0 means every word survived. *Processing* = wall time of `rubato auto` (analyse + plan + render, transcript supplied) per minute of input; Rubato's own speech-to-text (`base`) is listed per clip below.

## Summary

| Clip | Preset | Duration cut | Effective speed | WER vs original | Processing (s/min) |
|------|--------|--------------|-----------------|-----------------|--------------------|
| nasa-interview | default | 26.65% | 1.363x | 0.0115 | 8.50 |
| nasa-interview | conservative | 16.81% | 1.202x | 0.0202 | 9.29 |
| nasa-interview | aggressive | 33.51% | 1.504x | 0.0086 | 8.22 |
| wikimania-privacy-talk | default | 22.70% | 1.294x | 0.0048 | 4.02 |
| wikimania-privacy-talk | conservative | 13.62% | 1.158x | 0.0048 | 3.98 |
| wikimania-privacy-talk | aggressive | 29.41% | 1.417x | 0.0080 | 3.56 |
| wikimania-bot-talk | default | 22.86% | 1.296x | 0.0321 | 2.55 |
| wikimania-bot-talk | conservative | 13.60% | 1.157x | 0.0292 | 2.76 |
| wikimania-bot-talk | aggressive | 29.90% | 1.427x | 0.0321 | 2.44 |

## Per clip

### nasa-interview

- Source: NASA SVS 14327, Lesley Ott 2023 Earth Day interview (first 300 s), via Wikimedia Commons
- License: Public Domain (NASA)
- Duration: 300.02 s, 694 words (judge transcript)
- Rubato speech-to-text (`base`): 6.83 s (1.37 s per minute)

- **default** (slow 1.0, base 1.2, fast 1.5, silence 2.0): 300.02 s -> 220.07 s, WER 0.0115 (8 edits / 694 words), processing 42.52 s
- **conservative** (slow 1.0, base 1.1, fast 1.3, silence 1.5): 300.02 s -> 249.59 s, WER 0.0202 (14 edits / 694 words), processing 46.47 s
- **aggressive** (slow 1.0, base 1.3, fast 1.75, silence 2.5): 300.02 s -> 199.49 s, WER 0.0086 (6 edits / 694 words), processing 41.11 s

### wikimania-privacy-talk

- Source: Research and Privacy on Wikipedia, Wikimania 2025 lightning talk, Eli Asikin-Garmager, via Wikimedia Commons
- License: CC0 1.0
- Duration: 283.46 s, 627 words (judge transcript)
- Rubato speech-to-text (`base`): 8.25 s (1.75 s per minute)
- Human captions (624 words): judge WER on the original 0.0144; on outputs: default 0.0192, conservative 0.0144, aggressive 0.0128

- **default** (slow 1.0, base 1.2, fast 1.5, silence 2.0): 283.46 s -> 219.12 s, WER 0.0048 (3 edits / 627 words), processing 18.99 s
- **conservative** (slow 1.0, base 1.1, fast 1.3, silence 1.5): 283.46 s -> 244.85 s, WER 0.0048 (3 edits / 627 words), processing 18.82 s
- **aggressive** (slow 1.0, base 1.3, fast 1.75, silence 2.5): 283.46 s -> 200.08 s, WER 0.0080 (5 edits / 627 words), processing 16.82 s

### wikimania-bot-talk

- Source: Wikimania BoT candidate lightning talk, Fjmustak (Wikimedia Foundation), via Wikimedia Commons
- License: CC BY 4.0
- Duration: 178.17 s, 343 words (judge transcript)
- Rubato speech-to-text (`base`): 4.44 s (1.49 s per minute)

- **default** (slow 1.0, base 1.2, fast 1.5, silence 2.0): 178.17 s -> 137.44 s, WER 0.0321 (11 edits / 343 words), processing 7.58 s
- **conservative** (slow 1.0, base 1.1, fast 1.3, silence 1.5): 178.17 s -> 153.94 s, WER 0.0292 (10 edits / 343 words), processing 8.20 s
- **aggressive** (slow 1.0, base 1.3, fast 1.75, silence 2.5): 178.17 s -> 124.89 s, WER 0.0321 (11 edits / 343 words), processing 7.26 s

