---
name: rubato
description: Speed up a video or audio recording dynamically instead of with one flat multiplier - slow for the takeaways, lists and key numbers, fast through filler, fastest through dead air, with nothing cut and voices at natural pitch. Use this whenever the user wants to speed up, shorten, tighten or "make less boring" a talk, lecture, meeting recording, tutorial, screen recording, podcast or voice memo and can give a link to the file - including "smart speed", "variable speed", "speed up the boring parts", "don't just put it at 1.5x", "slow down for the important bits". Not for cutting content out or for music.
---

# Rubato

Rubato changes the speed of a recording passage by passage. It transcribes the speech, keeps takeaways, lists and key numbers at normal speed, plays ordinary passages a little faster, filler faster still, and dead air fastest. Nothing is removed and pitch is preserved, so the result is one continuous recording.

This plugin uses the Rubato connector, which has two tools:

- `speed_up_video` starts a job from a link and returns a job id.
- `get_result` reports the stage of a job and, when it is done, the result.

## What is needed from the user

A direct, public link to the media file (MP4, MOV, WebM, MKV, MP3, M4A, WAV), up to 15 minutes and 500 MB, with speech in it. A link to a page that plays the video does not work. If the user only has a file on their computer, or a longer recording, send them to https://www.tryrubato.com to upload it, or to https://github.com/andreolf/rubato for the version that runs on their own machine with no length limit.

Rubato is built for speech. For music, say so rather than running it: varying the speed of music makes the tempo lurch.

## Workflow

1. Call `speed_up_video` with the link. Keep the default speeds unless the user asked for something else:

   | The user wants | Setting |
   | --- | --- |
   | A different baseline, e.g. "around 1.3x" | `base` 1.3 |
   | Key parts slower than normal | `slow` 0.9 |
   | More aggressive on boring parts | `fast` 1.75, `silence` 3 |
   | Pauses treated like any dull part | `silence` equal to `fast` |
   | A language other than English | `language`, e.g. `it` |

   Defaults are `slow` 1.0, `base` 1.2, `fast` 1.5, `silence` 2.0. Speech stays easy to follow up to about 1.75x.

2. Call `get_result` with the job id every few seconds until the stage is `done` or `error`. Stages are queued, fetching, listening, transcribing, planning, rendering. A short clip takes seconds; fifteen minutes can take a few.

3. Report back:
   - the original and new length and the time saved;
   - the passages that were kept slow and the ones that were sped up, with their timestamps, so the user can see what Rubato treated as important;
   - the download link, noting that it expires after 30 minutes.

## Reading the result honestly

- The picks come from how sentences are phrased: "the key takeaway", "three things you need to know", "number two", figures and percentages. A takeaway nobody announced will not be in the list. If the user tells you which parts matter and they were not kept slow, say that the hosted version cannot be steered passage by passage, and point them to the local version, which accepts explicit marks.
- If no passages were recognised, only pauses changed speed. Say so instead of presenting the result as content-aware.
- The built-in phrases are English. Other languages are transcribed, but fewer passages are recognised.
- On `error`, pass the message on. The common ones are a link that is a web page instead of a file, a file that is too long or too large, and a link that is not public.

## Data

The file at the link is downloaded and processed on Rubato's server. The source is deleted when processing ends and the result after 30 minutes. Privacy policy: https://www.tryrubato.com/privacy. Do not send confidential recordings; use the local version for those.
