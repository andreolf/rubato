#!/bin/bash
# Fetch openly licensed test videos for Rubato benchmark
#
# All videos are either Public Domain or CC-BY licensed.
# Sources and licenses are documented in SOURCES.md

set -e

WORK_DIR="${1:-work}"
mkdir -p "$WORK_DIR"

echo "Fetching test videos to $WORK_DIR"

# Video 1: Internet Archive - MIT Lecture excerpt
# "How to Speak" by Patrick Winston
# License: CC-BY-NC-SA (MIT OpenCourseWare)
# Note: Using a 2-minute excerpt for benchmark purposes (fair use for testing)
VIDEO1_URL="https://archive.org/download/MIT6.S095IAP18/MIT6_S095IAP18_lec01_300k.mp4"
VIDEO1_FILE="$WORK_DIR/mit-lecture.mp4"
VIDEO1_FULL="$WORK_DIR/mit-lecture-full.mp4"

if [ ! -f "$VIDEO1_FILE" ]; then
    echo "Downloading MIT lecture excerpt..."
    
    if ! command -v wget &> /dev/null && ! command -v curl &> /dev/null; then
        echo "Error: Neither wget nor curl found. Please install wget or curl."
        exit 1
    fi
    
    # Download with wget or curl
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$VIDEO1_FULL" "$VIDEO1_URL" 2>&1 || {
            echo "Warning: Download failed for MIT lecture"
            rm -f "$VIDEO1_FULL"
        }
    else
        curl -L --progress-bar -o "$VIDEO1_FULL" "$VIDEO1_URL" 2>&1 || {
            echo "Warning: Download failed for MIT lecture"
            rm -f "$VIDEO1_FULL"
        }
    fi
    
    # Extract 2-minute segment starting at 5:00 (after intro)
    if [ -f "$VIDEO1_FULL" ] && [ -s "$VIDEO1_FULL" ]; then
        echo "Extracting 2-minute segment..."
        ffmpeg -ss 300 -i "$VIDEO1_FULL" -t 120 -c:v libx264 -c:a aac "$VIDEO1_FILE" -y 2>&1 | grep -E "(Duration|Stream|Output)" || true
        rm -f "$VIDEO1_FULL"
        if [ -f "$VIDEO1_FILE" ] && [ -s "$VIDEO1_FILE" ]; then
            echo "✓ Downloaded and prepared mit-lecture.mp4"
        else
            echo "✗ Failed to prepare mit-lecture.mp4"
            rm -f "$VIDEO1_FILE"
        fi
    fi
else
    echo "✓ mit-lecture.mp4 already exists"
fi

# Video 2: Internet Archive - Public Domain lecture
# "Great Astronomers" by Robert Stawell Ball (LibriVox)
# License: Public Domain
# Creating audio-over-still-image video (simulates talking-head with slides)
VIDEO2_FILE="$WORK_DIR/astronomy-lecture.mp4"
AUDIO_URL="https://archive.org/download/great_astronomers_1708_librivox/greatastronomers_01_ball_64kb.mp3"
AUDIO_FILE="$WORK_DIR/astronomy-audio.mp3"

if [ ! -f "$VIDEO2_FILE" ]; then
    echo "Downloading public domain astronomy lecture..."
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$AUDIO_FILE" "$AUDIO_URL" 2>&1 || {
            echo "Warning: Download failed for astronomy lecture"
            rm -f "$AUDIO_FILE"
        }
    else
        curl -L --progress-bar -o "$AUDIO_FILE" "$AUDIO_URL" 2>&1 || {
            echo "Warning: Download failed for astronomy lecture"
            rm -f "$AUDIO_FILE"
        }
    fi
    
    # Extract 2 minutes starting at 1:00 and create video with still image
    if [ -f "$AUDIO_FILE" ] && [ -s "$AUDIO_FILE" ]; then
        echo "Creating video from audio..."
        ffmpeg -f lavfi -i "color=c=0x2C3E50:s=640x480:r=25" \
               -ss 60 -i "$AUDIO_FILE" -t 120 \
               -c:v libx264 -preset ultrafast -tune stillimage \
               -c:a aac -b:a 128k -shortest \
               "$VIDEO2_FILE" -y 2>&1 | grep -E "(Duration|Stream|Output)" || true
        rm -f "$AUDIO_FILE"
        if [ -f "$VIDEO2_FILE" ] && [ -s "$VIDEO2_FILE" ]; then
            echo "✓ Created astronomy-lecture.mp4"
        else
            echo "✗ Failed to create astronomy-lecture.mp4"
            rm -f "$VIDEO2_FILE"
        fi
    fi
else
    echo "✓ astronomy-lecture.mp4 already exists"
fi

# Video 3: Internet Archive - Another public domain lecture
# Using a different chapter/talk for variety
VIDEO3_FILE="$WORK_DIR/librivox-talk.mp4"
AUDIO3_URL="https://archive.org/download/great_astronomers_1708_librivox/greatastronomers_02_ball_64kb.mp3"
AUDIO3_FILE="$WORK_DIR/librivox-audio.mp3"

if [ ! -f "$VIDEO3_FILE" ]; then
    echo "Downloading second public domain lecture..."
    
    if command -v wget &> /dev/null; then
        wget -q --show-progress -O "$AUDIO3_FILE" "$AUDIO3_URL" 2>&1 || {
            echo "Warning: Download failed for second lecture"
            rm -f "$AUDIO3_FILE"
        }
    else
        curl -L --progress-bar -o "$AUDIO3_FILE" "$AUDIO3_URL" 2>&1 || {
            echo "Warning: Download failed for second lecture"
            rm -f "$AUDIO3_FILE"
        }
    fi
    
    # Extract 2 minutes and create video
    if [ -f "$AUDIO3_FILE" ] && [ -s "$AUDIO3_FILE" ]; then
        echo "Creating video from audio..."
        ffmpeg -f lavfi -i "color=c=0x34495E:s=640x480:r=25" \
               -ss 90 -i "$AUDIO3_FILE" -t 120 \
               -c:v libx264 -preset ultrafast -tune stillimage \
               -c:a aac -b:a 128k -shortest \
               "$VIDEO3_FILE" -y 2>&1 | grep -E "(Duration|Stream|Output)" || true
        rm -f "$AUDIO3_FILE"
        if [ -f "$VIDEO3_FILE" ] && [ -s "$VIDEO3_FILE" ]; then
            echo "✓ Created librivox-talk.mp4"
        else
            echo "✗ Failed to create librivox-talk.mp4"
            rm -f "$VIDEO3_FILE"
        fi
    fi
else
    echo "✓ librivox-talk.mp4 already exists"
fi

echo ""
echo "Video preparation complete!"
echo ""
echo "Downloaded videos:"
[ -f "$VIDEO1_FILE" ] && [ -s "$VIDEO1_FILE" ] && echo "  ✓ mit-lecture.mp4 (MIT OpenCourseWare, CC-BY-NC-SA)"
[ -f "$VIDEO2_FILE" ] && [ -s "$VIDEO2_FILE" ] && echo "  ✓ astronomy-lecture.mp4 (LibriVox, Public Domain)"
[ -f "$VIDEO3_FILE" ] && [ -s "$VIDEO3_FILE" ] && echo "  ✓ librivox-talk.mp4 (LibriVox, Public Domain)"
echo ""
echo "See SOURCES.md for detailed attribution and licensing information."
