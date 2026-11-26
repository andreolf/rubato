# Rubato Benchmark

Reproducible benchmark of Rubato on real, openly licensed speech clips, across three speed presets.

## Metrics

- **Duration cut %**: how much shorter the output is than the input.
- **WER vs original**: word error rate of the output's transcript against the original's transcript.
  Both transcripts come from the same pinned "judge" model, so 0 means every word survived.
- **Processing (s/min)**: wall time of `rubato auto` (analyse + plan + render, with the transcript
  supplied) per minute of input. Rubato's own speech-to-text time is reported separately per clip.

## Method

1. **Clips**: three real recordings from Wikimedia Commons (an interview and two conference talks,
   178-300 s each). See [SOURCES.md](SOURCES.md) for URLs, licenses and preprocessing.
2. **Planning transcript**: `rubato.py transcribe` with Rubato's default `base` model, passed to
   `rubato auto --transcript` so every preset is timed identically.
3. **Presets**:
   - `default`: slow 1.0, base 1.2, fast 1.5, silence 2.0
   - `conservative`: slow 1.0, base 1.1, fast 1.3, silence 1.5
   - `aggressive`: slow 1.0, base 1.3, fast 1.75, silence 2.5
4. **Scoring**: the original and each output are transcribed by faster-whisper `small.en`
   (batched/VAD decoding, beam 5, temperature 0, `no_repeat_ngram_size=6`, language `en`).
   WER = word-level Levenshtein distance / words in the original's transcript, after lowercasing
   and stripping punctuation.
5. **Judge check against humans**: one clip (`wikimania-privacy-talk`) ships with human captions
   ([references/](references/)). The judge scores 1.44% WER against them on the original, so the judge is
   accurate enough to score with.

Why not `base` as the judge: on these clips Whisper `base`, and the default sequential decoder
with `small.en`, dropped whole passages or looped on a phrase, which put WER between 15% and over 100%,
including on the untouched original. That measured Whisper, not Rubato.

## Running

```bash
pip install faster-whisper      # plus ffmpeg/ffprobe on PATH
cd bench
./fetch_videos.sh               # downloads and converts the 3 clips into work/
python3 run_benchmark.py        # add --delete-outputs to save disk
```

Outputs:
- `results/benchmark_results.json`: every number, plus hardware and versions
- `results/benchmark_results.md`: tables
- `results/logs/<clip>.<preset>.txt`: raw stdout/stderr of each `rubato auto` run
- `results/transcripts/`: judge transcripts of every original and output
- `results/run_output.txt`: console output of the run

Media files stay in `work/` (git-ignored).

## Results

See [results/benchmark_results.md](results/benchmark_results.md) and the Benchmarks section of the
main README. Measured on an 8-vCPU Intel Xeon (KVM), 15.6 GB RAM, no GPU.

## Limitations

- Three clips, all English, 3-5 minutes. Longer or noisier recordings may behave differently.
- WER under about 3% is at the judge's noise floor: the `aggressive` preset sometimes scores
  lower than `conservative`, which is noise, not a real improvement.
- WER measures whether the words are still recognisable, not how pleasant the result sounds.
- Processing time varies by clip (2.4-9.3 s per minute here) and depends on the x264 preset
  (Rubato default `medium`) and the CPU.
