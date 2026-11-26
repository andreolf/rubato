# Test clip sources and licenses

The published benchmark numbers were measured on these three clips. All are real recorded
speech (no synthetic audio), downloaded from Wikimedia Commons on 2026-11-26 by
`fetch_videos.sh`. The media files are not committed; run `./fetch_videos.sh` to recreate them.

Preprocessing (identical for all clips): original WebM converted to H.264/AAC MP4 with
`ffmpeg -vf scale=-2:720 -c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 128k`
(the 480p clip keeps its native size). Only the NASA clip is trimmed.

| File | Content | Length used | License |
|------|---------|-------------|---------|
| `work/nasa-interview.mp4` | Interview: scientist answering on camera, with silent on-screen question cards between answers | 300.0 s (first 5:00 of 6:13) | Public domain (NASA) |
| `work/wikimania-privacy-talk.mp4` | Remote lightning talk: slides with the speaker's webcam inset | 283.5 s (full) | CC0 1.0 |
| `work/wikimania-bot-talk.mp4` | Conference lightning talk: speaker at a podium beside slides | 178.2 s (full) | CC BY 4.0 |

## 1. NASA Earth Day interview (Lesley Ott)

- **Title**: NASA Interview Opportunity: Celebrate our Dynamic Planet with a NASA Expert this Earth Day (SVS14327 – Lesley Ott 2023 Earth Day Interview)
- **Credit**: NASA's Scientific Visualization Studio
- **Commons page**: https://commons.wikimedia.org/wiki/File:NASA_Interview_Opportunity-_Celebrate_our_Dynamic_Planet_with_a_NASA_Expert_this_Earth_Day_(SVS14327_-_Lesley_Ott_2023EarthDay_Interview).webm
- **File URL**: https://upload.wikimedia.org/wikipedia/commons/b/b3/NASA_Interview_Opportunity-_Celebrate_our_Dynamic_Planet_with_a_NASA_Expert_this_Earth_Day_%28SVS14327_-_Lesley_Ott_2023EarthDay_Interview%29.webm
- **License**: Public domain (work of NASA)
- **Original**: 1920x1080, 372.7 s

## 2. Research and Privacy on Wikipedia (Eli Asikin-Garmager)

- **Title**: Research and Privacy on Wikipedia – Wikimania 2025 Lightning Talk
- **Author**: Eli Asikin-Garmager
- **Commons page**: https://commons.wikimedia.org/wiki/File:Research_and_Privacy_on_Wikipedia_-_Wikimania_2025_Lightning_Talk_-_Eli_Asikin-Garmager.webm
- **File URL**: https://upload.wikimedia.org/wikipedia/commons/2/29/Research_and_Privacy_on_Wikipedia_-_Wikimania_2025_Lightning_Talk_-_Eli_Asikin-Garmager.webm
- **License**: CC0 1.0 (https://creativecommons.org/publicdomain/zero/1.0/)
- **Original**: 1920x1080, 284.0 s
- **Human captions**: the WebM carries an embedded English subtitle track. It is saved as
  `references/wikimania-privacy-talk.srt` (CC0 with the video) and used to check the scoring model.

## 3. Wikimania Board of Trustees candidate lightning talk (Fjmustak)

- **Title**: Wikimania BoT candidate lightning talk – Fjmustak
- **Author**: Wikimedia Foundation
- **Commons page**: https://commons.wikimedia.org/wiki/File:Wikimania_BoT_candidate_lightning_talk_-_Fjmustak.webm
- **File URL**: https://upload.wikimedia.org/wikipedia/commons/c/c1/Wikimania_BoT_candidate_lightning_talk_-_Fjmustak.webm
- **License**: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Attribution: Wikimedia Foundation, via Wikimedia Commons.
- **Original**: 852x480, 178.2 s

## Sources tried earlier that did not work

- **archive.org** (LibriVox, MIT OCW mirrors): download URLs returned HTTP 503 from both the cloud
  agent and the benchmark machine on 2026-11-26.
- **Mozilla Common Voice S3 clips**: not reachable from the cloud agent; not needed once
  Wikimedia Commons worked.
