#!/usr/bin/env python3
"""
Rubato Benchmark Script

Measures:
- % runtime cut (output vs input duration)
- Word Error Rate (WER) between original and Rubato output transcripts
- Processing time per minute of video

Runs against openly licensed talking-head videos with multiple speed presets.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

# Pin versions for reproducibility
WHISPER_MODEL = "base"  # faster-whisper model
RUBATO_VERSION_CMD = ["python3", "../skills/rubato/scripts/rubato.py", "--help"]


def run_command(cmd: List[str], description: str = "", capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"Running: {description or ' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        check=False
    )
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"Error: {result.stderr}", file=sys.stderr)
    return result


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = run_command(cmd, f"Getting duration of {video_path}")
    if result.returncode == 0:
        return float(result.stdout.strip())
    return 0.0


def transcribe_with_whisper(video_path: str, output_json: str) -> bool:
    """Transcribe video using faster-whisper, save as JSON."""
    cmd = [
        "python3", "../skills/rubato/scripts/rubato.py",
        "transcribe", video_path,
        "-o", output_json,
        "--model", WHISPER_MODEL
    ]
    result = run_command(cmd, f"Transcribing {video_path}", capture_output=True)
    return result.returncode == 0 and os.path.exists(output_json)


def extract_transcript_text(transcript_json: str) -> str:
    """Extract plain text from Rubato/Whisper transcript JSON."""
    try:
        with open(transcript_json, 'r') as f:
            data = json.load(f)
        
        segments = data.get("segments", [])
        words = []
        
        for seg in segments:
            # Try word-level first, fall back to segment text
            seg_words = seg.get("words", [])
            if seg_words:
                for w in seg_words:
                    word_text = w.get("word", w.get("text", "")).strip()
                    if word_text:
                        words.append(word_text)
            else:
                text = seg.get("text", "").strip()
                if text:
                    words.extend(text.split())
        
        return " ".join(words).lower()
    except Exception as e:
        print(f"Error reading transcript {transcript_json}: {e}", file=sys.stderr)
        return ""


def normalize_text(text: str) -> List[str]:
    """Normalize text for WER calculation."""
    # Remove punctuation, lowercase, split into words
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().split()


def calculate_wer(reference: str, hypothesis: str) -> Dict[str, Any]:
    """Calculate Word Error Rate using Levenshtein distance."""
    ref_words = normalize_text(reference)
    hyp_words = normalize_text(hypothesis)
    
    # Levenshtein distance (Wagner-Fischer algorithm)
    r = len(ref_words)
    h = len(hyp_words)
    
    # Create distance matrix
    d = [[0] * (h + 1) for _ in range(r + 1)]
    
    for i in range(r + 1):
        d[i][0] = i
    for j in range(h + 1):
        d[0][j] = j
    
    for i in range(1, r + 1):
        for j in range(1, h + 1):
            if ref_words[i-1] == hyp_words[j-1]:
                d[i][j] = d[i-1][j-1]
            else:
                substitution = d[i-1][j-1] + 1
                insertion = d[i][j-1] + 1
                deletion = d[i-1][j] + 1
                d[i][j] = min(substitution, insertion, deletion)
    
    edit_distance = d[r][h]
    wer = edit_distance / r if r > 0 else 0.0
    
    return {
        "wer": wer,
        "edit_distance": edit_distance,
        "ref_words": r,
        "hyp_words": h
    }


def run_rubato(input_video: str, output_video: str, preset: Dict[str, float]) -> Dict[str, Any]:
    """Run Rubato with given preset and measure performance."""
    start_time = time.time()
    
    cmd = [
        "python3", "../skills/rubato/scripts/rubato.py",
        "auto", input_video,
        "-o", output_video,
        "--base", str(preset["base"]),
        "--slow", str(preset["slow"]),
        "--fast", str(preset["fast"]),
        "--silence", str(preset["silence"])
    ]
    
    result = run_command(cmd, f"Running Rubato with preset {preset['name']}", capture_output=True)
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    success = result.returncode == 0 and os.path.exists(output_video)
    
    return {
        "success": success,
        "processing_time": processing_time,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


def benchmark_video(video_info: Dict[str, str], presets: List[Dict], work_dir: Path) -> Dict[str, Any]:
    """Run benchmark on a single video with all presets."""
    video_name = video_info["name"]
    video_path = work_dir / video_info["filename"]
    
    print(f"\n{'='*60}")
    print(f"Benchmarking: {video_name}")
    print(f"{'='*60}\n")
    
    if not video_path.exists():
        print(f"Video not found: {video_path}", file=sys.stderr)
        return {"error": "video not found"}
    
    # Get original duration
    original_duration = get_video_duration(str(video_path))
    if original_duration <= 0:
        print(f"Could not determine video duration", file=sys.stderr)
        return {"error": "could not determine duration"}
    
    # Transcribe original
    original_transcript = work_dir / f"{video_name}.original.transcript.json"
    print(f"Transcribing original video...")
    if not transcribe_with_whisper(str(video_path), str(original_transcript)):
        print(f"Failed to transcribe original video", file=sys.stderr)
        return {"error": "transcription failed"}
    
    original_text = extract_transcript_text(str(original_transcript))
    
    results = {
        "video": video_name,
        "source": video_info.get("source", ""),
        "license": video_info.get("license", ""),
        "original_duration": original_duration,
        "original_transcript_words": len(normalize_text(original_text)),
        "presets": []
    }
    
    # Test each preset
    for preset in presets:
        preset_name = preset["name"]
        print(f"\n--- Preset: {preset_name} ---")
        
        output_video = work_dir / f"{video_name}.{preset_name}.mp4"
        output_transcript = work_dir / f"{video_name}.{preset_name}.transcript.json"
        
        # Run Rubato
        rubato_result = run_rubato(str(video_path), str(output_video), preset)
        
        if not rubato_result["success"]:
            print(f"Rubato failed for preset {preset_name}", file=sys.stderr)
            results["presets"].append({
                "preset": preset_name,
                "error": "rubato failed",
                **preset
            })
            continue
        
        # Get output duration
        output_duration = get_video_duration(str(output_video))
        
        # Transcribe output
        print(f"Transcribing output video...")
        if not transcribe_with_whisper(str(output_video), str(output_transcript)):
            print(f"Failed to transcribe output video", file=sys.stderr)
            results["presets"].append({
                "preset": preset_name,
                "error": "output transcription failed",
                **preset
            })
            continue
        
        output_text = extract_transcript_text(str(output_transcript))
        
        # Calculate WER
        wer_result = calculate_wer(original_text, output_text)
        
        # Calculate metrics
        duration_cut_pct = ((original_duration - output_duration) / original_duration * 100) if original_duration > 0 else 0
        processing_time_per_min = (rubato_result["processing_time"] / (original_duration / 60)) if original_duration > 0 else 0
        effective_speed = original_duration / output_duration if output_duration > 0 else 0
        
        preset_results = {
            "preset": preset_name,
            "settings": {
                "slow": preset["slow"],
                "base": preset["base"],
                "fast": preset["fast"],
                "silence": preset["silence"]
            },
            "original_duration_sec": round(original_duration, 2),
            "output_duration_sec": round(output_duration, 2),
            "duration_cut_pct": round(duration_cut_pct, 2),
            "effective_speed": round(effective_speed, 3),
            "wer": round(wer_result["wer"], 4),
            "wer_edit_distance": wer_result["edit_distance"],
            "wer_ref_words": wer_result["ref_words"],
            "wer_hyp_words": wer_result["hyp_words"],
            "processing_time_sec": round(rubato_result["processing_time"], 2),
            "processing_time_per_min": round(processing_time_per_min, 2)
        }
        
        results["presets"].append(preset_results)
        
        print(f"Duration: {original_duration:.1f}s -> {output_duration:.1f}s ({duration_cut_pct:.1f}% cut)")
        print(f"WER: {wer_result['wer']:.4f}")
        print(f"Processing: {rubato_result['processing_time']:.1f}s ({processing_time_per_min:.1f}s/min)")
    
    return results


def generate_markdown_table(all_results: List[Dict[str, Any]]) -> str:
    """Generate markdown table from benchmark results."""
    lines = []
    lines.append("# Rubato Benchmark Results")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Video | Preset | Duration Cut % | WER | Effective Speed | Processing (s/min) |")
    lines.append("|-------|--------|----------------|-----|-----------------|-------------------|")
    
    for video_result in all_results:
        if "error" in video_result:
            continue
        video = video_result["video"]
        for preset in video_result.get("presets", []):
            if "error" in preset:
                continue
            lines.append(
                f"| {video} | {preset['preset']} | "
                f"{preset['duration_cut_pct']}% | "
                f"{preset['wer']:.4f} | "
                f"{preset['effective_speed']}x | "
                f"{preset['processing_time_per_min']:.1f} |"
            )
    
    lines.append("")
    lines.append("## Detailed Results")
    lines.append("")
    
    for video_result in all_results:
        if "error" in video_result:
            lines.append(f"### {video_result.get('video', 'Unknown')} - ERROR: {video_result['error']}")
            lines.append("")
            continue
        
        lines.append(f"### {video_result['video']}")
        lines.append("")
        lines.append(f"- **Source**: {video_result.get('source', 'N/A')}")
        lines.append(f"- **License**: {video_result.get('license', 'N/A')}")
        lines.append(f"- **Original Duration**: {video_result['original_duration']:.1f}s")
        lines.append(f"- **Original Transcript**: {video_result['original_transcript_words']} words")
        lines.append("")
        
        for preset in video_result.get("presets", []):
            if "error" in preset:
                lines.append(f"#### Preset: {preset['preset']} - ERROR: {preset['error']}")
                lines.append("")
                continue
            
            lines.append(f"#### Preset: {preset['preset']}")
            lines.append("")
            lines.append(f"**Settings**: slow={preset['settings']['slow']}, base={preset['settings']['base']}, "
                        f"fast={preset['settings']['fast']}, silence={preset['settings']['silence']}")
            lines.append("")
            lines.append(f"- Output Duration: {preset['output_duration_sec']:.1f}s")
            lines.append(f"- Duration Cut: **{preset['duration_cut_pct']:.1f}%**")
            lines.append(f"- Effective Speed: **{preset['effective_speed']:.3f}x**")
            lines.append(f"- WER: **{preset['wer']:.4f}** ({preset['wer_edit_distance']} edits / {preset['wer_ref_words']} words)")
            lines.append(f"- Processing Time: {preset['processing_time_sec']:.1f}s ({preset['processing_time_per_min']:.1f}s per minute of video)")
            lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Rubato Benchmark")
    parser.add_argument("--work-dir", type=Path, default=Path("work"),
                       help="Working directory for downloads and outputs")
    parser.add_argument("--results-dir", type=Path, default=Path("results"),
                       help="Directory for final results")
    args = parser.parse_args()
    
    work_dir = args.work_dir
    results_dir = args.results_dir
    
    work_dir.mkdir(exist_ok=True)
    results_dir.mkdir(exist_ok=True)
    
    # Define test videos (will be downloaded by fetch_videos.sh)
    test_videos = [
        {
            "name": "sample1",
            "filename": "sample1.mp4",
            "source": "Downloaded via fetch_videos.sh",
            "license": "CC-BY or Public Domain"
        }
    ]
    
    # Define presets to test
    presets = [
        {
            "name": "default",
            "slow": 1.0,
            "base": 1.2,
            "fast": 1.5,
            "silence": 2.0
        },
        {
            "name": "conservative",
            "slow": 1.0,
            "base": 1.1,
            "fast": 1.3,
            "silence": 1.5
        },
        {
            "name": "aggressive",
            "slow": 1.0,
            "base": 1.3,
            "fast": 1.75,
            "silence": 2.5
        }
    ]
    
    # Run benchmarks
    all_results = []
    for video_info in test_videos:
        result = benchmark_video(video_info, presets, work_dir)
        all_results.append(result)
    
    # Save JSON results
    json_output = results_dir / "benchmark_results.json"
    with open(json_output, 'w') as f:
        json.dump({
            "rubato_version": "main",
            "whisper_model": WHISPER_MODEL,
            "test_videos": test_videos,
            "presets": presets,
            "results": all_results
        }, f, indent=2)
    
    print(f"\nResults saved to {json_output}")
    
    # Generate markdown table
    markdown = generate_markdown_table(all_results)
    markdown_output = results_dir / "benchmark_results.md"
    with open(markdown_output, 'w') as f:
        f.write(markdown)
    
    print(f"Markdown table saved to {markdown_output}")
    print("\nBenchmark complete!")


if __name__ == "__main__":
    main()
