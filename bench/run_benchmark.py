#!/usr/bin/env python3
"""
Rubato Benchmark Script

Measures, for each test clip and speed preset:
- % runtime cut (output vs input duration)
- Word Error Rate (WER) of the Rubato output against the original, scored by a pinned
  speech-to-text "judge" (faster-whisper small.en), plus WER against human captions
  where the clip ships with them
- Rubato processing time per minute of input

Run from the bench/ directory after ./fetch_videos.sh.
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

RUBATO = "../skills/rubato/scripts/rubato.py"

# Model Rubato itself uses to read the talk while planning (its default).
RUBATO_MODEL = "base"

# The judge: the speech-to-text used ONLY to score intelligibility. It is deliberately
# stronger and more stable than Rubato's planning model. With `base`, or with the default
# sequential decoder, Whisper itself dropped whole passages or looped on a phrase
# ("that that that ...") on these clips, so WER mostly measured Whisper's own failures.
# Batched (VAD-chunked) decoding with small.en, beam 5, temperature 0 and
# no_repeat_ngram_size=6 was the setting that matched human captions (1.4% WER on the one
# clip that has them) and stopped the loops.
JUDGE_MODEL = "small.en"
JUDGE_LANGUAGE = "en"
JUDGE_OPTS = dict(language=JUDGE_LANGUAGE, beam_size=5, batch_size=8,
                  temperature=0.0, no_repeat_ngram_size=6)

TEST_VIDEOS = [
    {
        "name": "nasa-interview",
        "filename": "nasa-interview.mp4",
        "source": "NASA SVS 14327, Lesley Ott 2023 Earth Day interview (first 300 s), via Wikimedia Commons",
        "license": "Public Domain (NASA)",
    },
    {
        "name": "wikimania-privacy-talk",
        "filename": "wikimania-privacy-talk.mp4",
        "source": "Research and Privacy on Wikipedia, Wikimania 2025 lightning talk, Eli Asikin-Garmager, via Wikimedia Commons",
        "license": "CC0 1.0",
        # Captions embedded in the original WebM (human-written, CC0 with the video)
        "captions": "references/wikimania-privacy-talk.srt",
    },
    {
        "name": "wikimania-bot-talk",
        "filename": "wikimania-bot-talk.mp4",
        "source": "Wikimania BoT candidate lightning talk, Fjmustak (Wikimedia Foundation), via Wikimedia Commons",
        "license": "CC BY 4.0",
    },
]

PRESETS = [
    {"name": "default", "slow": 1.0, "base": 1.2, "fast": 1.5, "silence": 2.0},
    {"name": "conservative", "slow": 1.0, "base": 1.1, "fast": 1.3, "silence": 1.5},
    {"name": "aggressive", "slow": 1.0, "base": 1.3, "fast": 1.75, "silence": 2.5},
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def run_command(cmd: List[str], description: str = "") -> subprocess.CompletedProcess:
    print(f"Running: {description or ' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"Error: {result.stderr}", file=sys.stderr)
    return result


def get_video_duration(video_path: str) -> float:
    result = run_command(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                         f"Getting duration of {video_path}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def normalize_text(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().split()


def calculate_wer(reference: str, hypothesis: str) -> Dict[str, Any]:
    """Word Error Rate via Levenshtein distance on normalised words."""
    ref, hyp = normalize_text(reference), normalize_text(hypothesis)
    prev = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        cur = [i] + [0] * len(hyp)
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            cur[j] = min(prev[j - 1] + cost, cur[j - 1] + 1, prev[j] + 1)
        prev = cur
    dist = prev[len(hyp)]
    return {"wer": dist / len(ref) if ref else 0.0, "edit_distance": dist,
            "ref_words": len(ref), "hyp_words": len(hyp)}


def read_srt_text(path: Path) -> str:
    """Plain text of an SRT, without cue numbers, timings or (Speaker) labels."""
    keep = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.isdigit() or "-->" in s or re.fullmatch(r"\(.*\)", s):
            continue
        keep.append(s)
    return " ".join(keep)


def write_log(log_dir: Path, name: str, stdout: str, stderr: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{name}.txt").write_text(f"# stdout\n{stdout or ''}\n# stderr\n{stderr or ''}")


def collect_hardware() -> Dict[str, Any]:
    info: Dict[str, Any] = {"os": platform.platform(), "python": platform.python_version()}
    try:
        for line in subprocess.run(["lscpu"], capture_output=True, text=True).stdout.splitlines():
            if line.startswith("Model name:"):
                info["cpu"] = line.split(":", 1)[1].strip()
    except OSError:
        pass
    info["cpu_count"] = os.cpu_count()
    try:
        with open("/proc/meminfo") as f:
            info["ram_gb"] = round(int(f.readline().split()[1]) / 1024 / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    try:
        from importlib.metadata import version
        info["faster_whisper"] = version("faster-whisper")
        info["ctranslate2"] = version("ctranslate2")
    except Exception:
        pass
    try:
        info["ffmpeg"] = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                                        text=True).stdout.splitlines()[0]
    except (OSError, IndexError):
        pass
    try:
        info["rubato_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                               text=True).stdout.strip()
    except OSError:
        pass
    return info


# ---------------------------------------------------------------------------
# speech-to-text
# ---------------------------------------------------------------------------

class Judge:
    """faster-whisper small.en used only for scoring. Loaded once."""

    def __init__(self) -> None:
        from faster_whisper import BatchedInferencePipeline, WhisperModel
        self.pipe = BatchedInferencePipeline(model=WhisperModel(JUDGE_MODEL, compute_type="int8"))

    @staticmethod
    def _audio(path: str):
        # Decode with ffmpeg and hand over samples (avoids PyAV version quirks).
        import numpy as np
        pcm = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-vn",
                              "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe(self, path: str, out_txt: Path) -> str:
        segments, _ = self.pipe.transcribe(self._audio(path), **JUDGE_OPTS)
        text = " ".join(s.text.strip() for s in segments)
        out_txt.write_text(text)
        return text


def rubato_transcribe(video: Path, out_json: Path) -> Dict[str, Any]:
    """Rubato's own transcription (what `auto` would do), timed separately."""
    start = time.time()
    r = run_command(["python3", RUBATO, "transcribe", str(video), "-o", str(out_json),
                     "--model", RUBATO_MODEL, "--language", JUDGE_LANGUAGE],
                    f"Rubato transcribe {video}")
    return {"success": r.returncode == 0 and out_json.exists(), "time_sec": time.time() - start}


def run_rubato(video: Path, output: Path, preset: Dict[str, Any], transcript: Path) -> Dict[str, Any]:
    """Time `rubato auto` (analyse + plan + render) with the transcript supplied, so every
    preset is timed the same way. Without --transcript the first preset would also pay for
    speech-to-text and later presets would silently reuse the sidecar file."""
    cmd = ["python3", RUBATO, "auto", str(video), "-o", str(output),
           "--transcript", str(transcript),
           "--base", str(preset["base"]), "--slow", str(preset["slow"]),
           "--fast", str(preset["fast"]), "--silence", str(preset["silence"])]
    start = time.time()
    r = run_command(cmd, f"Rubato auto, preset {preset['name']}")
    return {"success": r.returncode == 0 and output.exists(), "processing_time": time.time() - start,
            "stdout": r.stdout, "stderr": r.stderr}


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------

def benchmark_video(info: Dict[str, Any], judge: Judge, work: Path, results: Path,
                    keep_outputs: bool) -> Dict[str, Any]:
    name = info["name"]
    video = work / info["filename"]
    print(f"\n{'=' * 60}\nBenchmarking: {name}\n{'=' * 60}\n")
    if not video.exists():
        return {"video": name, "error": f"video not found: {video} (run ./fetch_videos.sh)"}
    duration = get_video_duration(str(video))
    if duration <= 0:
        return {"video": name, "error": "could not determine duration"}

    tx_dir = results / "transcripts"
    tx_dir.mkdir(parents=True, exist_ok=True)

    plan_tx = work / f"{name}.rubato-{RUBATO_MODEL}.transcript.json"
    tx = rubato_transcribe(video, plan_tx)
    if not tx["success"]:
        return {"video": name, "error": "rubato transcription failed"}

    original_text = judge.transcribe(str(video), tx_dir / f"{name}.original.txt")
    out: Dict[str, Any] = {
        "video": name, "source": info["source"], "license": info["license"],
        "original_duration": round(duration, 2),
        "original_words": len(normalize_text(original_text)),
        "rubato_transcription_time_sec": round(tx["time_sec"], 2),
        "rubato_transcription_time_per_min": round(tx["time_sec"] / (duration / 60), 2),
        "presets": [],
    }
    captions_text: Optional[str] = None
    if info.get("captions") and Path(info["captions"]).exists():
        captions_text = read_srt_text(Path(info["captions"]))
        c = calculate_wer(captions_text, original_text)
        out["caption_words"] = c["ref_words"]
        out["original_caption_wer"] = round(c["wer"], 4)

    for preset in PRESETS:
        pname = preset["name"]
        print(f"\n--- Preset: {pname} ---")
        output = work / f"{name}.{pname}.mp4"
        r = run_rubato(video, output, preset, plan_tx)
        write_log(results / "logs", f"{name}.{pname}", r["stdout"], r["stderr"])
        if not r["success"]:
            out["presets"].append({"preset": pname, "error": "rubato failed",
                                   "stderr_tail": (r["stderr"] or "")[-500:]})
            continue
        out_dur = get_video_duration(str(output))
        output_text = judge.transcribe(str(output), tx_dir / f"{name}.{pname}.txt")
        if not keep_outputs:
            output.unlink(missing_ok=True)
        w = calculate_wer(original_text, output_text)
        res = {
            "preset": pname,
            "settings": {k: preset[k] for k in ("slow", "base", "fast", "silence")},
            "original_duration_sec": round(duration, 2),
            "output_duration_sec": round(out_dur, 2),
            "duration_cut_pct": round((duration - out_dur) / duration * 100, 2),
            "effective_speed": round(duration / out_dur, 3) if out_dur else 0,
            "wer": round(w["wer"], 4),
            "wer_edit_distance": w["edit_distance"],
            "wer_ref_words": w["ref_words"],
            "wer_hyp_words": w["hyp_words"],
            "processing_time_sec": round(r["processing_time"], 2),
            "processing_time_per_min": round(r["processing_time"] / (duration / 60), 2),
        }
        if captions_text is not None:
            res["caption_wer"] = round(calculate_wer(captions_text, output_text)["wer"], 4)
        out["presets"].append(res)
        print(f"Duration: {duration:.1f}s -> {out_dur:.1f}s ({res['duration_cut_pct']:.1f}% cut)")
        print(f"WER vs original: {w['wer']:.4f}" +
              (f" | vs captions: {res['caption_wer']:.4f} (original {out['original_caption_wer']:.4f})"
               if captions_text is not None else ""))
        print(f"Processing: {r['processing_time']:.1f}s ({res['processing_time_per_min']:.1f}s/min)")
    return out


def generate_markdown(all_results: List[Dict[str, Any]], hw: Dict[str, Any]) -> str:
    L = ["# Rubato Benchmark Results", "",
         f"- **CPU**: {hw.get('cpu', 'unknown')} ({hw.get('cpu_count')} vCPUs), {hw.get('ram_gb')} GB RAM, no GPU",
         f"- **OS**: {hw.get('os')}",
         f"- **ffmpeg**: {hw.get('ffmpeg')}",
         f"- **faster-whisper**: {hw.get('faster_whisper')} (ctranslate2 {hw.get('ctranslate2')})",
         f"- **Rubato commit**: {hw.get('rubato_commit')}", "",
         "**How to read it.** *WER* = word error rate of the Rubato output's transcript against the "
         f"original's transcript, both made by the same judge (faster-whisper `{JUDGE_MODEL}`, batched, beam 5, "
         "temperature 0). 0 means every word survived. *Processing* = wall time of `rubato auto` "
         "(analyse + plan + render, transcript supplied) per minute of input; Rubato's own speech-to-text "
         f"(`{RUBATO_MODEL}`) is listed per clip below.", "",
         "## Summary", "",
         "| Clip | Preset | Duration cut | Effective speed | WER vs original | Processing (s/min) |",
         "|------|--------|--------------|-----------------|-----------------|--------------------|"]
    for v in all_results:
        for p in v.get("presets", []):
            if "error" in p:
                L.append(f"| {v['video']} | {p['preset']} | error: {p['error']} | | | |")
                continue
            L.append(f"| {v['video']} | {p['preset']} | {p['duration_cut_pct']:.2f}% | "
                     f"{p['effective_speed']:.3f}x | {p['wer']:.4f} | {p['processing_time_per_min']:.2f} |")
    L += ["", "## Per clip", ""]
    for v in all_results:
        if "error" in v:
            L += [f"### {v['video']}: ERROR {v['error']}", ""]
            continue
        L += [f"### {v['video']}", "",
              f"- Source: {v['source']}", f"- License: {v['license']}",
              f"- Duration: {v['original_duration']:.2f} s, {v['original_words']} words (judge transcript)",
              f"- Rubato speech-to-text (`{RUBATO_MODEL}`): {v['rubato_transcription_time_sec']:.2f} s "
              f"({v['rubato_transcription_time_per_min']:.2f} s per minute)"]
        if "original_caption_wer" in v:
            L.append(f"- Human captions ({v['caption_words']} words): judge WER on the original "
                     f"{v['original_caption_wer']:.4f}; on outputs: " +
                     ", ".join(f"{p['preset']} {p['caption_wer']:.4f}" for p in v["presets"] if "caption_wer" in p))
        L.append("")
        for p in v["presets"]:
            if "error" in p:
                L += [f"- **{p['preset']}**: ERROR {p['error']}"]
                continue
            s = p["settings"]
            L.append(f"- **{p['preset']}** (slow {s['slow']}, base {s['base']}, fast {s['fast']}, "
                     f"silence {s['silence']}): {p['original_duration_sec']:.2f} s -> {p['output_duration_sec']:.2f} s, "
                     f"WER {p['wer']:.4f} ({p['wer_edit_distance']} edits / {p['wer_ref_words']} words), "
                     f"processing {p['processing_time_sec']:.2f} s")
        L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rubato Benchmark")
    ap.add_argument("--work-dir", type=Path, default=Path("work"))
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument("--delete-outputs", action="store_true",
                    help="delete each rendered video after it is scored (saves disk)")
    args = ap.parse_args()
    args.work_dir.mkdir(exist_ok=True)
    args.results_dir.mkdir(exist_ok=True)

    hw = collect_hardware()
    judge = Judge()
    all_results = [benchmark_video(v, judge, args.work_dir, args.results_dir, not args.delete_outputs)
                   for v in TEST_VIDEOS]

    with open(args.results_dir / "benchmark_results.json", "w") as f:
        json.dump({"rubato_commit": hw.get("rubato_commit"), "rubato_model": RUBATO_MODEL,
                   "judge_model": JUDGE_MODEL, "judge_options": JUDGE_OPTS, "hardware": hw,
                   "test_videos": TEST_VIDEOS, "presets": PRESETS, "results": all_results}, f, indent=2)
    (args.results_dir / "benchmark_results.md").write_text(generate_markdown(all_results, hw) + "\n")
    print(f"\nResults saved to {args.results_dir}/benchmark_results.json and .md")


if __name__ == "__main__":
    main()
