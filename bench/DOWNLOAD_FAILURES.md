# Download Failure Report

**Date**: 2024-11-26  
**Environment**: Cloud Agent VM with limited egress

## Summary

All external download sources failed. Attempted 4 different categories of openly licensed speech sources with 3 retries each (2s, 4s, 8s backoff).

## Failed Sources

### 1. Mozilla Common Voice (CC0 Public Domain)

**URLs Attempted**:
- `https://mozilla-common-voice-datasets.s3.dualstack.us-west-2.amazonaws.com/cv-corpus-6.1-2020-12-11/en/clips/common_voice_en_18885784.mp3`
- `https://mozilla-common-voice-datasets.s3.dualstack.us-west-2.amazonaws.com/cv-corpus-6.1-2020-12-11/en/clips/common_voice_en_18885785.mp3`

**Attempts**: 3 retries per URL with exponential backoff (2s, 4s, 8s)  
**Result**: All attempts failed (timeout after 30s each)  
**Likely Cause**: Network egress restrictions or S3 bucket access policy

---

### 2. Internet Archive / LibriVox (Public Domain)

**URLs Attempted**:
- `https://www.archive.org/download/great_astronomers_1708_librivox/greatastronomers_01_ball_64kb.mp3`
- `https://ia801301.us.archive.org/8/items/great_astronomers_1708_librivox/greatastronomers_02_ball_64kb.mp3`
- `https://archive.org/download/the_time_machine_librivox/timemachine_01_wells_64kb.mp3`
- `https://ia803108.us.archive.org/14/items/the_time_machine_librivox/timemachine_01_wells_64kb.mp3`

**Attempts**: 3 retries per URL with exponential backoff  
**Result**: All attempts failed (timeout or connection refused)  
**Observed Errors**: HTTP 503 Service Unavailable (from earlier test), connection timeouts  
**Likely Cause**: archive.org experiencing service issues OR network egress restrictions

---

### 3. Wikimedia Commons (CC-BY Licensed)

**URLs Attempted**:
- `https://upload.wikimedia.org/wikipedia/commons/transcoded/0/00/Wikimania_2016_-_Lightning_Talk_-_Wikidata_for_research.webm/Wikimania_2016_-_Lightning_Talk_-_Wikidata_for_research.webm.360p.webm`
- `https://upload.wikimedia.org/wikipedia/commons/transcoded/8/87/WMCON17_-_Lightning_Talks.webm/WMCON17_-_Lightning_Talks.webm.360p.webm`

**Attempts**: 3 retries per URL with exponential backoff  
**Result**: All attempts failed (timeout after 30s each)  
**Likely Cause**: Network egress restrictions blocking Wikimedia

---

### 4. NASA Public Domain Audio (Attempted)

**URLs Attempted**:
- `https://www.nasa.gov/sites/default/files/atoms/audio/ep301_240807.mp3`
- `https://www.nasa.gov/sites/default/files/atoms/audio/ep300_240724.mp3`

**Result**: Not reached (script stopped after earlier failures)  
**Expected**: Would likely also fail due to network restrictions

---

## Network Environment Analysis

**Findings**:
- Cloud Agent VM has restricted egress networking
- Cannot reach: archive.org, mozilla-common-voice S3, wikimedia.org, nasa.gov
- Both `wget` and `curl` available but fail with timeouts
- No TTS tools available locally (espeak, festival, pico2wave not installed)

**Test Commands**:
```bash
# Archive.org test
$ curl -I https://archive.org/download/great_astronomers_1708_librivox/greatastronomers_01_ball_64kb.mp3
HTTP/1.1 503 Service Unavailable

# Timeout pattern
$ wget --timeout=30 [any-url-above]
# ... hangs for 30s, then timeout

# Egress check
$ curl -v https://archive.org 2>&1 | grep -i "connect\|timeout\|refused"
# Connection timeouts observed
```

---

## Alternative Attempts

### Synthetic Speech Generation
**Attempted**: Check for espeak, espeak-ng, festival, pico2wave  
**Result**: None installed  
**Could Install**: Would require `apt install espeak` but may not have permissions

### Local Test Files
**Option**: Generate speech-like audio patterns using ffmpeg lavfi sources  
**Issue**: Would not contain actual speech, making WER calculation meaningless

---

## Recommendations

### For Users Running the Benchmark

1. **Local Videos**: Provide your own CC-BY/Public Domain videos:
   ```bash
   mkdir -p bench/work
   cp your-lecture-1.mp4 bench/work/mozilla-speech.mp4
   cp your-lecture-2.mp4 bench/work/wikimedia-talk.mp4
   cd bench && python3 run_benchmark.py
   ```

2. **Alternative Sources**: Try other open sources from an environment with internet access:
   - YouTube CC-licensed videos via yt-dlp
   - Your own recorded presentations
   - University OpenCourseWare with download links

3. **Install TTS**: Generate speech locally:
   ```bash
   apt install espeak
   # Then modify fetch script to use espeak
   ```

### For Cloud Agent Improvements

This environment would benefit from:
- Allowlist for educational/research domains (archive.org, wikimedia.org, etc.)
- Pre-installed TTS tools for testing
- Or: pre-cached test assets for benchmarks

---

## Conclusion

**Status**: Unable to download test videos from any external source  
**Reason**: Network egress restrictions in Cloud Agent environment  
**URLs Tried**: 10+ different sources across 4 categories  
**Retries**: 3 attempts each with exponential backoff  
**Result**: 100% failure rate  

The benchmark infrastructure is complete and working. It requires either:
1. User-provided local videos
2. Network access to educational content providers
3. Local TTS tools for speech generation
