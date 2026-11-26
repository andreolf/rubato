# Rubato Benchmark Results

> **Note**: This is a sample results file showing the expected format. 
> To generate actual benchmark results, run `./fetch_videos.sh` followed by `python3 run_benchmark.py` with real talking-head videos.
> The synthetic test video provided by default does not contain speech and will produce empty transcripts.

## Hardware

- **CPU**: To be recorded when benchmark runs
- **RAM**: To be recorded  
- **Storage**: SSD
- **OS**: Linux 6.12.113+

## Methodology

### Test Videos

Videos used should be:
- Openly licensed (CC-BY or Public Domain)
- Talking-head format (lectures, presentations, tutorials)
- 1-3 minutes in length for quick benchmarking
- Contain clear speech for transcription

### Transcription

- **Engine**: faster-whisper
- **Model**: `base` (pinned)
- **Configuration**: Default settings

### WER Calculation

Word Error Rate computed as:
```
WER = (Substitutions + Insertions + Deletions) / Total Reference Words
```

Using Levenshtein distance on normalized transcripts (lowercase, punctuation removed).

### Speed Presets Tested

| Preset | Slow | Base | Fast | Silence |
|--------|------|------|------|---------|
| default | 1.0 | 1.2 | 1.5 | 2.0 |
| conservative | 1.0 | 1.1 | 1.3 | 1.5 |
| aggressive | 1.0 | 1.3 | 1.75 | 2.5 |

## Results Summary

### Expected Metrics

**Duration Cut %**: Typically 15-25% for default preset on mixed content (some key parts, some filler, some pauses)

**WER**: Expected to be very low (< 0.05) since speed changes preserve all audio, just at different rates. Higher WER would indicate audio quality issues.

**Processing Time**: Varies by hardware, typically 1-3 seconds per minute of input video on modern hardware.

## Sample Results Format

| Video | Preset | Duration Cut % | WER | Effective Speed | Processing (s/min) |
|-------|--------|----------------|-----|-----------------|-------------------|
| lecture-1 | default | 18.5% | 0.0234 | 1.23x | 2.1 |
| lecture-1 | conservative | 12.1% | 0.0189 | 1.14x | 2.0 |
| lecture-1 | aggressive | 24.3% | 0.0298 | 1.32x | 2.3 |

## Running Your Own Benchmark

1. Replace `work/sample1.mp4` with a real talking-head video:
   ```bash
   cp your-lecture.mp4 bench/work/sample1.mp4
   ```

2. Update metadata in `run_benchmark.py`:
   ```python
   test_videos = [
       {
           "name": "your-video",
           "filename": "sample1.mp4",
           "source": "Your source here",
           "license": "CC-BY / Public Domain / etc."
       }
   ]
   ```

3. Install dependencies:
   ```bash
   pip install faster-whisper imageio-ffmpeg
   ```

4. Run benchmark:
   ```bash
   cd bench
   python3 run_benchmark.py
   ```

## Limitations

- **Synthetic Test Video**: Default video has no speech, so WER calculation is not meaningful
- **Short Duration**: Benchmark uses short clips; longer videos may show different characteristics
- **Hardware Dependent**: Processing times are specific to the hardware used
- **Whisper Variability**: Small variations in WER expected between runs due to Whisper model behavior

## Extending the Benchmark

To add more test videos:
1. Download/create openly licensed videos
2. Add to `test_videos` list in `run_benchmark.py`
3. Place files in `work/` directory
4. Document source and license

To add more presets:
1. Add to `presets` list in `run_benchmark.py`
2. Specify slow/base/fast/silence speeds

## Comparison with Flat Speed

For typical talking-head content:
- **Flat 1.2x**: Uniform speedup, no adaptation to content
- **Rubato default**: Variable speed (1.0-2.0x), adapts to content
  - Similar time savings to flat 1.2x
  - Better comprehension for key parts (slower)
  - Faster through filler and pauses

**Hypothesis**: Rubato achieves similar or better time savings while maintaining higher comprehension due to content-aware slowdown on important passages.

## Future Work

- [ ] Test with multiple video types (lectures, tutorials, meetings)
- [ ] Measure comprehension/retention (would require human testing)
- [ ] Benchmark on different hardware configurations
- [ ] Test with longer videos (30-60 minutes)
- [ ] Compare with other variable-speed tools
