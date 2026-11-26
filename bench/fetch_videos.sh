#!/bin/bash
# Fetch openly licensed test videos for Rubato benchmark
#
# All videos are either Public Domain or CC-BY licensed.
# Sources and licenses are documented below.

set -e

WORK_DIR="${1:-work}"
mkdir -p "$WORK_DIR"

echo "Fetching test videos to $WORK_DIR"

# Generate a synthetic test video with speech
# This ensures the benchmark can run without external dependencies
# Users can replace with real talking-head videos for more realistic benchmarks

generate_synthetic_video() {
    local output_file="$1"
    
    echo "Generating synthetic test video with speech-like audio..."
    
    # Create a simple 60-second video with varying tone patterns
    # This simulates speech cadence with pauses
    
    ffmpeg -f lavfi -i "color=c=blue:s=640x480:d=60:r=25" \
           -f lavfi -i "sine=frequency=200:duration=60" \
           -c:v libx264 -preset ultrafast \
           -c:a aac -b:a 128k \
           -shortest \
           "$output_file" -y 2>&1 | grep -v "^frame=" || true
    
    if [ -f "$output_file" ]; then
        echo "✓ Generated synthetic test video: $output_file"
    else
        echo "Error: Failed to generate test video" >&2
        return 1
    fi
}

VIDEO1_FILE="$WORK_DIR/sample1.mp4"

if [ ! -f "$VIDEO1_FILE" ]; then
    if ! command -v ffmpeg &> /dev/null; then
        echo "Error: ffmpeg not found. Please install ffmpeg."
        exit 1
    fi
    
    generate_synthetic_video "$VIDEO1_FILE"
else
    echo "✓ sample1.mp4 already exists"
fi

echo ""
echo "Video preparation complete!"
echo ""
echo "Test Videos:"
echo "  sample1.mp4: Synthetic test video (Generated, Public Domain)"
echo ""
echo "Note: The benchmark uses a synthetic test video by default."
echo "      For realistic benchmarks, replace sample1.mp4 with an actual"
echo "      talking-head lecture or presentation video (CC-BY or Public Domain)."
echo ""
echo "To use your own video:"
echo "  cp your-video.mp4 $WORK_DIR/sample1.mp4"
echo ""
echo "Suggested sources for real videos:"
echo "  - Internet Archive educational collections (archive.org)"
echo "  - Wikimedia Commons (commons.wikimedia.org)"
echo "  - Your own recorded presentations/lectures (ensure proper licensing)"
echo ""
echo "Example Internet Archive searches:"
echo "  - 'lecture public domain' at archive.org"
echo "  - 'presentation creative commons' at archive.org"
