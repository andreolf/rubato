# Rubato Benchmark Results

**Status**: Not yet run - all external sources failed

## Issue

The benchmark could not be completed because all external video download sources failed after extensive retry attempts. The Cloud Agent environment has restricted network egress that blocks access to educational content providers.

**Comprehensive Attempt Made**: Tried 10+ URLs across 4 source categories with 3 retries each (exponential backoff: 2s, 4s, 8s). See [DOWNLOAD_FAILURES.md](../DOWNLOAD_FAILURES.md) for complete failure details.

## What Was Attempted

1. **Script Setup**: Complete benchmark pipeline with WER calculation, duration measurement, and processing time tracking
2. **Video Sources**: Attempted 4 categories of openly licensed sources:
   - Mozilla Common Voice (CC0) - 2 URLs, 3 retries each - **FAILED: timeout**
   - Internet Archive/LibriVox (Public Domain) - 4 URLs, 3 retries each - **FAILED: 503/timeout**
   - Wikimedia Commons (CC-BY) - 2 URLs, 3 retries each - **FAILED: timeout**
   - NASA (Public Domain) - 2 URLs queued - **NOT REACHED**
3. **Network Environment**: Cloud Agent VM with restricted egress - cannot reach archive.org, wikimedia.org, mozilla CDN, nasa.gov
4. **Alternative Attempts**: Checked for local TTS tools (espeak, festival) - **NONE INSTALLED**

**Complete failure details**: See [DOWNLOAD_FAILURES.md](../DOWNLOAD_FAILURES.md) with all URLs, retry attempts, and error patterns.

## Next Steps to Complete Benchmark

To generate actual results:

1. **Wait for service availability**: Retry when Internet Archive is accessible
2. **Or use alternative sources**: Replace fetch_videos.sh URLs with accessible alternatives
3. **Or provide local videos**: Place 2-3 talking-head MP4 files in `work/` directory and update test_videos list in run_benchmark.py

```bash
# Manual video placement
cp your-lecture-1.mp4 work/mit-lecture.mp4
cp your-lecture-2.mp4 work/astronomy-lecture.mp4
cp your-lecture-3.mp4 work/librivox-talk.mp4

# Then run benchmark
python3 run_benchmark.py
```

## Expected Results Format

Once the benchmark runs with real speech videos, results will appear here:

### Hardware

- **CPU**: (To be recorded when benchmark runs)
- **RAM**: (To be recorded)
- **Storage**: SSD
- **OS**: Linux 6.12.113+

### Results Summary

| Video | Preset | Duration Cut % | WER | Effective Speed | Processing (s/min) |
|-------|--------|----------------|-----|-----------------|-------------------|
| (awaiting run) | - | - | - | - | - |

### Detailed Results by Video

(Results will be populated here after successful run)

## Methodology

### Test Videos

Videos must be:
- Openly licensed (CC-BY, CC-BY-SA, CC-BY-NC-SA, or Public Domain)
- Talking-head format with clear speech
- 2-3 minutes in length
- Properly attributed (see SOURCES.md)

### Metrics

1. **Duration Cut %**: `(original_duration - output_duration) / original_duration * 100`
2. **WER (Word Error Rate)**: Levenshtein distance on normalized transcripts (original vs processed)
   - Both transcribed with faster-whisper `base` model
   - Transcripts normalized: lowercase, punctuation removed
   - `WER = edit_distance / reference_word_count`
3. **Processing Time**: Total processing seconds / input video minutes

### Speed Presets

| Preset | Slow | Base | Fast | Silence | Use Case |
|--------|------|------|------|---------|----------|
| default | 1.0 | 1.2 | 1.5 | 2.0 | General purpose, balanced |
| conservative | 1.0 | 1.1 | 1.3 | 1.5 | Minimal speedup, maximum safety |
| aggressive | 1.0 | 1.3 | 1.75 | 2.5 | Maximum time savings |

### Reproducibility

- **Whisper Model**: `base` (faster-whisper) - pinned
- **Rubato Version**: Current repository HEAD
- **Deterministic**: Yes (same input + settings = same output)
- **Raw Logs**: Saved in `work/` directory (not committed - see .gitignore)
- **Results JSON**: Committed to track evolution over time

## Limitations

- **No Results Yet**: Benchmark has not completed a successful run
- **Hardware Dependent**: Processing times vary significantly by CPU
- **Whisper Variability**: Small WER variations expected between runs (~0.001-0.01)
- **Short Videos**: 2-minute clips are fast to benchmark but may not represent hour-long content
- **Network Dependency**: Requires external downloads unless videos are provided locally

## Running the Benchmark Yourself

If you have access to suitable test videos:

```bash
cd bench

# Option 1: Try the download script (may fail if archive.org is down)
./fetch_videos.sh

# Option 2: Provide your own videos
mkdir -p work
cp your-talking-head-video-1.mp4 work/mit-lecture.mp4
cp your-talking-head-video-2.mp4 work/astronomy-lecture.mp4
cp your-talking-head-video-3.mp4 work/librivox-talk.mp4

# Install dependencies
pip install faster-whisper imageio-ffmpeg

# Run benchmark
python3 run_benchmark.py

# Results will be written to this file
```

## Comparison with Flat Speed

**Hypothesis** (to be tested): 

For typical talking-head content, Rubato's variable-speed approach should achieve similar time savings to a flat 1.2x speedup while maintaining or improving comprehension by:
- Keeping key content (takeaways, lists, numbers) at 1.0x
- Speeding through filler and transitions at 1.5x
- Racing through pauses at 2.0x

This would result in similar WER (since no content is cut) but hypothetically better viewer comprehension (not measured by WER alone).

**Testing Required**: This hypothesis needs real benchmark data to validate or refute.

---

**Last Updated**: 2024-11-26  
**Status**: Infrastructure complete, awaiting successful video downloads
