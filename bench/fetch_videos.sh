#!/bin/bash
# Fetch the openly licensed test clips used by the Rubato benchmark.
# All three come from Wikimedia Commons (upload.wikimedia.org), which was reachable
# when the published numbers were measured. archive.org returned HTTP 503 at that time.
#
# Each clip is downloaded as the original WebM, then converted to H.264/AAC MP4
# (720p max, CRF 20). The NASA interview is trimmed to its first 300 seconds.
# See SOURCES.md for titles, authors and licenses.

set -euo pipefail

WORK_DIR="${1:-work}"
mkdir -p "$WORK_DIR"
UA="rubato-benchmark/1.0 (https://github.com/andreolf/rubato)"

fetch() {
    local url="$1" out="$2" attempt=1 wait=2
    while [ $attempt -le 4 ]; do
        echo "  attempt $attempt: $url"
        if curl -fsSL -A "$UA" --retry 0 --max-time 600 -o "$out" "$url" && [ -s "$out" ]; then
            return 0
        fi
        rm -f "$out"; sleep $wait; wait=$((wait * 2)); attempt=$((attempt + 1))
    done
    return 1
}

# name|url|extra ffmpeg input args|video filter
CLIPS=(
  "nasa-interview|https://upload.wikimedia.org/wikipedia/commons/b/b3/NASA_Interview_Opportunity-_Celebrate_our_Dynamic_Planet_with_a_NASA_Expert_this_Earth_Day_%28SVS14327_-_Lesley_Ott_2023EarthDay_Interview%29.webm|-t 300|scale=-2:720"
  "wikimania-privacy-talk|https://upload.wikimedia.org/wikipedia/commons/2/29/Research_and_Privacy_on_Wikipedia_-_Wikimania_2025_Lightning_Talk_-_Eli_Asikin-Garmager.webm||scale=-2:720"
  "wikimania-bot-talk|https://upload.wikimedia.org/wikipedia/commons/c/c1/Wikimania_BoT_candidate_lightning_talk_-_Fjmustak.webm||null"
)

for entry in "${CLIPS[@]}"; do
    IFS='|' read -r name url extra vf <<< "$entry"
    out="$WORK_DIR/$name.mp4"
    if [ -s "$out" ]; then echo "ok  $out already exists"; continue; fi
    echo "get $name"
    src="$WORK_DIR/$name.source.webm"
    fetch "$url" "$src"
    # shellcheck disable=SC2086
    ffmpeg -nostdin -loglevel error -y -i "$src" $extra -map 0:v:0 -map 0:a:0 \
        -vf "$vf" -c:v libx264 -preset veryfast -crf 20 -c:a aac -b:a 128k "$out"
    rm -f "$src"
    echo "ok  $out ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out") s)"
done
