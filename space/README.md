---
title: Rubato
emoji: 🎼
colorFrom: indigo
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Speed up videos dynamically and save time.
---

# Rubato demo

Upload a video and get it back at dynamic speed: slower for takeaways, lists and key numbers, faster through filler, fastest through silence.

Source, CLI and agent skill: https://github.com/andreolf/rubato

To deploy, this folder needs a copy of `skills/rubato/scripts/rubato.py` next to `app.py`.
Set `RUBATO_SITE_URL` to the public address so canonical links and the sitemap are correct.
