#!/usr/bin/env bash
# Usage: tts.sh <output.mp3> [voice_id]
# Spoken text on stdin. Requires FISH_API_KEY.
set -euo pipefail

if [[ -z "${FISH_API_KEY:-}" ]]; then
  echo "FISH_API_KEY is not set. Create a key at https://fish.audio/app/api-keys then export FISH_API_KEY=..." >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: tts.sh <output.mp3> [voice_id]" >&2
  exit 1
fi

out="$1"
voice_id="${2:-}"
export TTS_VOICE_ID="$voice_id"
text="$(cat)"

body="$(printf '%s' "$text" | python3 -c '
import json, os, sys
payload = {"text": sys.stdin.read(), "format": "mp3"}
voice = os.environ.get("TTS_VOICE_ID") or ""
if voice:
    payload["reference_id"] = voice
print(json.dumps(payload))
')"

tmp="$(mktemp)"

fail_dump() {
  echo "$1" >&2
  head -c 500 "$tmp" >&2
  echo >&2
  rm -f "$tmp"
  exit 1
}

code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer ${FISH_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "model: s2.1-pro" \
  --data "$body")"

if [[ "$code" != "200" ]]; then
  fail_dump "Fish TTS HTTP $code:"
fi

FFPROBE="${FFPROBE:-$(command -v ffprobe || true)}"
if [[ -z "$FFPROBE" && -x /opt/homebrew/bin/ffprobe ]]; then
  FFPROBE="/opt/homebrew/bin/ffprobe"
fi
if [[ -z "$FFPROBE" ]]; then
  fail_dump "ffprobe not found (PATH or /opt/homebrew/bin/ffprobe). TTS body:"
fi

size="$(wc -c < "$tmp" | tr -d ' ')"
if [[ "$size" -lt 1024 ]]; then
  fail_dump "Fish TTS response too small (${size} bytes):"
fi

if ! dur="$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$tmp")"; then
  fail_dump "ffprobe failed on TTS output:"
fi

ok="$(awk -v d="$dur" 'BEGIN { print (d + 0 >= 0.3) ? 1 : 0 }')"
if [[ "$ok" -ne 1 ]]; then
  fail_dump "TTS duration too short (${dur:-unknown}s):"
fi

mv "$tmp" "$out"
echo "$out"
