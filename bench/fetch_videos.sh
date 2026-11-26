#!/bin/bash
# Fetch openly licensed test videos for Rubato benchmark
# Tries multiple sources with retries and backoff

set -e

WORK_DIR="${1:-work}"
mkdir -p "$WORK_DIR"

echo "Fetching test videos to $WORK_DIR"
echo "Trying multiple sources with retries..."
echo ""

# Function to download with retries
download_with_retry() {
    local url="$1"
    local output="$2"
    local max_attempts=3
    local attempt=1
    local wait_time=2
    
    while [ $attempt -le $max_attempts ]; do
        echo "  Attempt $attempt/$max_attempts: $url"
        
        if command -v wget &> /dev/null; then
            if wget --timeout=30 --tries=1 -q --show-progress -O "$output" "$url" 2>&1; then
                if [ -f "$output" ] && [ -s "$output" ]; then
                    return 0
                fi
            fi
        elif command -v curl &> /dev/null; then
            if curl --max-time 30 --retry 0 -L --progress-bar -o "$output" "$url" 2>&1; then
                if [ -f "$output" ] && [ -s "$output" ]; then
                    return 0
                fi
            fi
        fi
        
        rm -f "$output"
        
        if [ $attempt -lt $max_attempts ]; then
            echo "  Failed, waiting ${wait_time}s before retry..."
            sleep $wait_time
            wait_time=$((wait_time * 2))
        fi
        
        attempt=$((attempt + 1))
    done
    
    return 1
}

# Track successes
SUCCESS_COUNT=0

# Video 1: Try Mozilla Common Voice sample (CC0 speech)
# Short speech samples for voice recognition
VIDEO1_FILE="$WORK_DIR/mozilla-speech.mp4"
if [ ! -f "$VIDEO1_FILE" ]; then
    echo "Source 1: Mozilla Common Voice (CC0 Public Domain speech)"
    
    # Download a few Common Voice samples and combine them
    TEMP_DIR="$WORK_DIR/temp_cv"
    mkdir -p "$TEMP_DIR"
    
    # Try Common Voice sample URLs (these are actual validated sentences)
    CV_SAMPLES=(
        "https://mozilla-common-voice-datasets.s3.dualstack.us-west-2.amazonaws.com/cv-corpus-6.1-2020-12-11/en/clips/common_voice_en_18885784.mp3"
        "https://mozilla-common-voice-datasets.s3.dualstack.us-west-2.amazonaws.com/cv-corpus-6.1-2020-12-11/en/clips/common_voice_en_18885785.mp3"
    )
    
    # Try downloading samples
    sample_count=0
    for i in "${!CV_SAMPLES[@]}"; do
        if download_with_retry "${CV_SAMPLES[$i]}" "$TEMP_DIR/sample$i.mp3"; then
            sample_count=$((sample_count + 1))
            echo "  ✓ Downloaded sample $i"
        fi
    done
    
    if [ $sample_count -eq 0 ]; then
        echo "  ✗ Mozilla Common Voice samples failed, trying LibriVox..."
        
        # Fallback to LibriVox direct MP3
        LIBRIVOX_URL="https://www.archive.org/download/great_astronomers_1708_librivox/greatastronomers_01_ball_64kb.mp3"
        TEMP_AUDIO="$TEMP_DIR/librivox.mp3"
        
        if download_with_retry "$LIBRIVOX_URL" "$TEMP_AUDIO"; then
            echo "  ✓ Downloaded LibriVox audio"
            
            # Extract 2 minutes starting at 1:00 and create video
            if ffmpeg -ss 60 -i "$TEMP_AUDIO" -t 120 -f lavfi -i "color=c=0x2C3E50:s=640x480:r=25" \
                   -c:v libx264 -preset ultrafast -tune stillimage \
                   -c:a aac -b:a 128k -shortest \
                   "$VIDEO1_FILE" -y 2>&1 | grep -q "Output"; then
                echo "✓ Created mozilla-speech.mp4 (LibriVox fallback)"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            else
                echo "✗ Failed to create video from audio"
                rm -f "$VIDEO1_FILE"
            fi
        else
            echo "  ✗ LibriVox fallback also failed"
        fi
    fi
    
    rm -rf "$TEMP_DIR"
else
    echo "✓ mozilla-speech.mp4 already exists"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi

# Video 2: Wikimedia Commons - Try multiple educational talks
VIDEO2_FILE="$WORK_DIR/wikimedia-talk.mp4"
if [ ! -f "$VIDEO2_FILE" ]; then
    echo ""
    echo "Source 2: Wikimedia Commons (CC-BY licensed talks)"
    
    # Try several Wikimedia videos (smaller ones more likely to work)
    WIKIMEDIA_URLS=(
        "https://upload.wikimedia.org/wikipedia/commons/transcoded/0/00/Wikimania_2016_-_Lightning_Talk_-_Wikidata_for_research.webm/Wikimania_2016_-_Lightning_Talk_-_Wikidata_for_research.webm.360p.webm"
        "https://upload.wikimedia.org/wikipedia/commons/transcoded/8/87/WMCON17_-_Lightning_Talks.webm/WMCON17_-_Lightning_Talks.webm.360p.webm"
    )
    
    for wiki_url in "${WIKIMEDIA_URLS[@]}"; do
        TEMP_VIDEO="$WORK_DIR/temp_wiki.webm"
        
        if download_with_retry "$wiki_url" "$TEMP_VIDEO"; then
            echo "  ✓ Downloaded Wikimedia video"
            
            # Extract 2 minutes and convert to mp4
            if ffmpeg -ss 10 -i "$TEMP_VIDEO" -t 120 -c:v libx264 -c:a aac \
                   "$VIDEO2_FILE" -y 2>&1 | grep -q "Output"; then
                echo "✓ Created wikimedia-talk.mp4"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
                rm -f "$TEMP_VIDEO"
                break
            else
                echo "  ✗ Failed to convert video"
                rm -f "$VIDEO2_FILE" "$TEMP_VIDEO"
            fi
        fi
    done
    
    if [ ! -f "$VIDEO2_FILE" ]; then
        echo "  ✗ All Wikimedia sources failed"
    fi
else
    echo "✓ wikimedia-talk.mp4 already exists"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi

# Video 3: Try direct LibriVox with better retry logic
VIDEO3_FILE="$WORK_DIR/librivox-lecture.mp4"
if [ ! -f "$VIDEO3_FILE" ]; then
    echo ""
    echo "Source 3: LibriVox via Archive.org (Public Domain)"
    
    # Try multiple LibriVox sources
    LIBRIVOX_URLS=(
        "https://ia801301.us.archive.org/8/items/great_astronomers_1708_librivox/greatastronomers_02_ball_64kb.mp3"
        "https://archive.org/download/the_time_machine_librivox/timemachine_01_wells_64kb.mp3"
        "https://ia803108.us.archive.org/14/items/the_time_machine_librivox/timemachine_01_wells_64kb.mp3"
    )
    
    for librivox_url in "${LIBRIVOX_URLS[@]}"; do
        TEMP_AUDIO="$WORK_DIR/temp_audio.mp3"
        
        if download_with_retry "$librivox_url" "$TEMP_AUDIO"; then
            echo "  ✓ Downloaded LibriVox audio"
            
            # Create video from audio
            if ffmpeg -f lavfi -i "color=c=0x34495E:s=640x480:r=25" \
                   -ss 90 -i "$TEMP_AUDIO" -t 120 \
                   -c:v libx264 -preset ultrafast -tune stillimage \
                   -c:a aac -b:a 128k -shortest \
                   "$VIDEO3_FILE" -y 2>&1 | grep -q "Output"; then
                echo "✓ Created librivox-lecture.mp4"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
                rm -f "$TEMP_AUDIO"
                break
            else
                echo "  ✗ Failed to create video"
                rm -f "$VIDEO3_FILE" "$TEMP_AUDIO"
            fi
        fi
    done
    
    if [ ! -f "$VIDEO3_FILE" ]; then
        echo "  ✗ All LibriVox sources failed"
    fi
else
    echo "✓ librivox-lecture.mp4 already exists"
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
fi

# Video 4: Try NASA public domain content
VIDEO4_FILE="$WORK_DIR/nasa-talk.mp4"
if [ ! -f "$VIDEO4_FILE" ] && [ $SUCCESS_COUNT -lt 2 ]; then
    echo ""
    echo "Source 4: NASA (Public Domain)"
    
    # Try NASA audio/video archives
    NASA_URLS=(
        "https://www.nasa.gov/sites/default/files/atoms/audio/ep301_240807.mp3"
        "https://www.nasa.gov/sites/default/files/atoms/audio/ep300_240724.mp3"
    )
    
    for nasa_url in "${NASA_URLS[@]}"; do
        TEMP_AUDIO="$WORK_DIR/temp_nasa.mp3"
        
        if download_with_retry "$nasa_url" "$TEMP_AUDIO"; then
            echo "  ✓ Downloaded NASA audio"
            
            # Create video from audio
            if ffmpeg -f lavfi -i "color=c=0x000000:s=640x480:r=25" \
                   -i "$TEMP_AUDIO" -t 120 \
                   -c:v libx264 -preset ultrafast -tune stillimage \
                   -c:a aac -b:a 128k -shortest \
                   "$VIDEO4_FILE" -y 2>&1 | grep -q "Output"; then
                echo "✓ Created nasa-talk.mp4"
                SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
                rm -f "$TEMP_AUDIO"
                break
            else
                rm -f "$VIDEO4_FILE" "$TEMP_AUDIO"
            fi
        fi
    done
fi

echo ""
echo "================================================"
echo "Video download summary:"
echo "================================================"
[ -f "$VIDEO1_FILE" ] && [ -s "$VIDEO1_FILE" ] && echo "  ✓ mozilla-speech.mp4 ($(du -h "$VIDEO1_FILE" | cut -f1))"
[ -f "$VIDEO2_FILE" ] && [ -s "$VIDEO2_FILE" ] && echo "  ✓ wikimedia-talk.mp4 ($(du -h "$VIDEO2_FILE" | cut -f1))"
[ -f "$VIDEO3_FILE" ] && [ -s "$VIDEO3_FILE" ] && echo "  ✓ librivox-lecture.mp4 ($(du -h "$VIDEO3_FILE" | cut -f1))"
[ -f "$VIDEO4_FILE" ] && [ -s "$VIDEO4_FILE" ] && echo "  ✓ nasa-talk.mp4 ($(du -h "$VIDEO4_FILE" | cut -f1))"
echo ""
echo "Successfully downloaded: $SUCCESS_COUNT videos with real speech"
echo ""

if [ $SUCCESS_COUNT -ge 2 ]; then
    echo "✓ Ready to run benchmark!"
    echo "  Run: python3 run_benchmark.py"
else
    echo "✗ Failed to download minimum 2 videos"
    echo "  Please check network connectivity and try again"
    exit 1
fi
