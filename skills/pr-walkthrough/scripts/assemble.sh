#!/usr/bin/env bash
set -euo pipefail

FFMPEG="${FFMPEG:-$(command -v ffmpeg || true)}"
if [[ -z "$FFMPEG" && -x /opt/homebrew/bin/ffmpeg ]]; then
  FFMPEG="/opt/homebrew/bin/ffmpeg"
fi
if [[ -z "$FFMPEG" ]]; then
  echo "Error: ffmpeg not found (PATH or /opt/homebrew/bin/ffmpeg)" >&2
  exit 1
fi

FFPROBE="${FFPROBE:-$(command -v ffprobe || true)}"
if [[ -z "$FFPROBE" && -x /opt/homebrew/bin/ffprobe ]]; then
  FFPROBE="/opt/homebrew/bin/ffprobe"
fi
if [[ -z "$FFPROBE" ]]; then
  echo "Error: ffprobe not found (PATH or /opt/homebrew/bin/ffprobe)" >&2
  exit 1
fi

MAX_BYTES=9961472  # 9.5 MB

usage() {
  echo "Usage: $0 <workdir>" >&2
  exit 1
}

[[ $# -eq 1 ]] || usage

WORKDIR="$1"

if [[ ! -d "$WORKDIR" ]]; then
  echo "Error: workdir not found: $WORKDIR" >&2
  exit 1
fi

WORKDIR="$(cd "$WORKDIR" && pwd)"
cd "$WORKDIR"

# Prefer Playwright webm when both screencast.webm and screencast.mp4 exist.
SCREENCAST=""
if [[ -f screencast.webm ]]; then
  SCREENCAST="screencast.webm"
elif [[ -f screencast.mp4 ]]; then
  SCREENCAST="screencast.mp4"
else
  echo "Error: screencast.webm or screencast.mp4 missing in $WORKDIR" >&2
  exit 1
fi

shopt -s nullglob
beats=(beat-*.mp3)
shopt -u nullglob

if [[ ${#beats[@]} -eq 0 ]]; then
  echo "Error: no beat-*.mp3 files in $WORKDIR" >&2
  exit 1
fi

# Sorted concat list (paths relative to workdir / concat.txt location)
: > concat.txt
while IFS= read -r beat; do
  printf "file '%s'\n" "$beat" >> concat.txt
done < <(ls beat-*.mp3 | sort)

"$FFMPEG" -y -f concat -safe 0 -i concat.txt -c:a aac -b:a 128k narration.m4a

video_dur="$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$SCREENCAST")"
audio_dur="$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 narration.m4a)"

# Compare durations with awk (portable float compare)
video_ge_audio="$(awk -v v="$video_dur" -v a="$audio_dur" 'BEGIN { print (v + 0 >= a + 0) ? 1 : 0 }')"

if [[ "$video_ge_audio" -eq 1 ]]; then
  # Video ≥ audio: pad audio, end on video
  "$FFMPEG" -y -i "$SCREENCAST" -i narration.m4a \
    -map 0:v:0 -map 1:a:0 \
    -c:v libx264 -pix_fmt yuv420p \
    -af apad -c:a aac -b:a 128k \
    -shortest -movflags +faststart \
    walkthrough.mp4
else
  # Audio > video: pad video last frame, end on audio
  "$FFMPEG" -y -i "$SCREENCAST" -i narration.m4a \
    -map 0:v:0 -map 1:a:0 \
    -vf "tpad=stop_mode=clone:stop=-1" -c:v libx264 -pix_fmt yuv420p \
    -c:a aac -b:a 128k \
    -shortest -movflags +faststart \
    walkthrough.mp4
fi

compress_if_needed() {
  local size
  size="$(wc -c < walkthrough.mp4 | tr -d ' ')"
  if [[ "$size" -le "$MAX_BYTES" ]]; then
    return 0
  fi

  "$FFMPEG" -y -i walkthrough.mp4 \
    -vf "scale='min(1280,iw)':-2" \
    -c:v libx264 -crf 28 -preset fast -pix_fmt yuv420p \
    -c:a aac -b:a 96k -movflags +faststart \
    walkthrough.compressed.mp4
  mv -f walkthrough.compressed.mp4 walkthrough.mp4

  size="$(wc -c < walkthrough.mp4 | tr -d ' ')"
  if [[ "$size" -le "$MAX_BYTES" ]]; then
    return 0
  fi

  "$FFMPEG" -y -i walkthrough.mp4 \
    -vf "scale='min(960,iw)':-2" \
    -c:v libx264 -crf 32 -preset fast -pix_fmt yuv420p \
    -c:a aac -b:a 96k -movflags +faststart \
    walkthrough.compressed.mp4
  mv -f walkthrough.compressed.mp4 walkthrough.mp4
}

compress_if_needed

out_path="$WORKDIR/walkthrough.mp4"
out_dur="$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 walkthrough.mp4)"
out_bytes="$(wc -c < walkthrough.mp4 | tr -d ' ')"

echo "path: $out_path"
echo "duration: ${out_dur}s"
echo "bytes: $out_bytes"

exit 0
