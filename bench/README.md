# Rubato Benchmark

Reproducible benchmark measuring Rubato's performance and accuracy across different speed presets.

## Metrics

- **Duration Cut %**: Percentage reduction in runtime (output duration vs input duration)
- **WER (Word Error Rate)**: Transcription accuracy preservation, measured by comparing Whisper transcripts of original vs processed video
- **Processing Time**: Seconds of processing time per minute of input video

## Methodology

1. **Test Videos**: Uses openly licensed talking-head videos (CC-BY or Public Domain)
2. **Transcription**: Both original and processed videos are transcribed using `faster-whisper` with the `base` model (pinned for reproducibility)
3. **WER Calculation**: Computes Levenshtein edit distance between normalized transcripts
4. **Speed Presets**: Tests multiple configurations:
   - `default`: slow=1.0, base=1.2, fast=1.5, silence=2.0
   - `conservative`: slow=1.0, base=1.1, fast=1.3, silence=1.5
   - `aggressive`: slow=1.0, base=1.3, fast=1.75, silence=2.5

## Running the Benchmark

### Prerequisites

```bash
# Install dependencies
pip install faster-whisper imageio-ffmpeg

# Or use uv (recommended)
uv pip install faster-whisper imageio-ffmpeg
```

Requires:
- Python 3.8+
- ffmpeg (for video processing)
- ffprobe (usually comes with ffmpeg)

### Quick Start

```bash
cd bench

# 1. Fetch test videos
./fetch_videos.sh

# 2. Run benchmark
python3 run_benchmark.py

# Results will be in results/benchmark_results.json and results/benchmark_results.md
```

### Using Your Own Videos

For more realistic benchmarks, replace the synthetic test video with actual talking-head content:

```bash
# Copy your video to the work directory
cp your-lecture.mp4 work/sample1.mp4

# Update run_benchmark.py test_videos list with proper metadata
# Then run the benchmark
python3 run_benchmark.py
```

## Reproducibility

Fixed versions:
- **Whisper Model**: `base` (faster-whisper)
- **Rubato**: Current repository version
- **Random Seeds**: N/A (Rubato is deterministic given the same input and settings)

The benchmark script captures:
- Exact preset parameters
- Input video metadata
- Processing timestamps
- Full stdout/stderr logs (in JSON output)

## Hardware

Benchmark results are hardware-dependent. Document your system when sharing results:

```bash
# Example hardware specification
# CPU: AMD EPYC 7763 64-Core Processor
# RAM: 32 GB
# Storage: SSD
# OS: Linux 6.12.113+
```

## Results

See `results/benchmark_results.md` for the latest run, or check the main README's Benchmarks section.

## Limitations

- **Synthetic Test Video**: Default test video is synthetic (tone-based). Real talking-head videos will show different characteristics.
- **WER Variability**: Whisper transcription has some randomness; WER may vary slightly between runs.
- **Short Clips**: Benchmark uses short clips for speed. Longer videos may show different performance characteristics.
- **Single-threaded**: Processing is currently single-threaded; timing reflects this.

For production benchmarks, use multiple real talking-head videos of varying lengths and styles.

## Extending the Benchmark

To add more test videos:

1. Add video info to `run_benchmark.py` `test_videos` list
2. Place video file in `work/` directory
3. Run benchmark

To add more presets:

1. Add preset dict to `run_benchmark.py` `presets` list
2. Run benchmark

## Raw Logs

All raw logs and intermediate files are preserved in the `work/` directory:
- Original and processed videos
- Transcript JSON files
- Plan JSON files
- Processing logs

Commit the `results/` directory to track benchmark evolution over time.
