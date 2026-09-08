---
name: pr-walkthrough
description: Graba un screencast con Playwright, lo narra en español con Fish Audio TTS, muxea con ffmpeg y opcionalmente adjunta el MP4 a un PR de GitHub. Usar cuando el usuario pida un video de walkthrough de PR, demo narrada, video de un bug, /pr-walkthrough, voz en el screencast, Playwright, o Fish TTS sobre una grabación de Playwright.
---

Workdir: `~/.grok/walkthroughs/<slug>/`. Voice cache: `~/.grok/walkthroughs/voice.json`. Default language: Spanish (`es`).

Copy beats shape from [references/beats.example.json](references/beats.example.json).

Skill dir: `~/.grok/skills/pr-walkthrough/`. Agent CWD is the repo, not the skill dir — invoke `~/.grok/skills/pr-walkthrough/scripts/record.mjs`, `~/.grok/skills/pr-walkthrough/scripts/tts.sh`, and `~/.grok/skills/pr-walkthrough/scripts/assemble.sh`. Do not use `/Users/<username>/...`.

## Beats

Fields: `title`, `language` (`es` | `en`, default `es`), `slug`, `start_url` (required), `beats[]`.

- `id`: zero-padded two digits, unique. Sort order = play order.
- `narration`: spoken text. Square-bracket Fish tags (`[calm]`, `[whispering]`) are performed, not spoken. Target ~8–20 seconds (~25–40 Spanish words). Prefer 3–8 beats. Total video 30–90s. One sentence per beat, tied to a visible UI action. Keep each narration under ~2000 characters; if longer, split into two beats.
- `play` (required): `{ "do": "goto" | "click" | "hover" | "wait" | "fill" | "waitFor" }`.
  - `goto` takes optional `url` (default `start_url`).
  - `click` and `hover` take `text` (first visible substring) and/or `selector` (CSS). `play.selector` wins over `text`.
  - `fill` types `play.value` (required) into the field located by `selector` (wins) or `text` (accessible name via `getByLabel`, not the label text node).
  - `waitFor` waits until `selector` or `text` is visible (timeout ~15s). `selector` wins over `text`.
  - `wait` holds the frame with no page action.
- `action`: optional notes, not executed.

## Procedure

1. **Preconditions.** Resolve `ffmpeg` / `ffprobe` from PATH (`command -v ffmpeg`, `command -v ffprobe`); if missing, fall back to `/opt/homebrew/bin/ffmpeg` and `/opt/homebrew/bin/ffprobe`. Confirm they are executable. Confirm `node` and `~/.grok/skills/pr-walkthrough/scripts/record.mjs` exist. Confirm Fish TTS via `search_tool` query `fish-audio text_to_speech`. If Fish MCP is missing, require `FISH_API_KEY` and use `~/.grok/skills/pr-walkthrough/scripts/tts.sh`.

2. **Voice.** If `~/.grok/walkthroughs/voice.json` exists and its `language` matches the beats language, reuse `voice_id` (old `reference_id` is `voice_id`). Else omit `voice_id` (Fish default for the language). Optional: the user can paste a voice id from https://fish.audio; write `{ "voice_id", "name", "language" }`. Do not hardcode a `voice_id`.

3. **Draft beats.** From the PR / diff / bug, write `~/.grok/walkthroughs/<slug>/beats.json`. Show the narrations to the user and wait for a short OK before recording if more than 3 beats.

4. **Delegate after OK.** After the user OKs the beats, delegate TTS + record + assemble (steps 5–8) to a **background subagent**. The parent does not run those steps itself. When the subagent finishes, the parent only reports path, duration, and bytes.

5. **TTS per beat (sequential).** One beat after another — never in parallel. Prefer MCP: `fish-audio__text_to_speech` with `text = narration`, `voice_id` from `voice.json` if present, `language` from beats. Download `audio_url` with `curl` to `<workdir>/beat-NN.mp3`. Fallback: `printf '%s' "$narration" | ~/.grok/skills/pr-walkthrough/scripts/tts.sh "<workdir>/beat-NN.mp3" [voice_id]`. After each MP3, require size ≥ 1 KB **and** `ffprobe` duration ≥ 0.3 s. If not, dump `head -c 500` of the file and abort. On any failure, stop immediately (do not record silent video; do not start the next beat).

```bash
mp3="<workdir>/beat-NN.mp3"
FFPROBE="${FFPROBE:-$(command -v ffprobe || true)}"
if [[ -z "$FFPROBE" && -x /opt/homebrew/bin/ffprobe ]]; then FFPROBE="/opt/homebrew/bin/ffprobe"; fi
[[ -n "$FFPROBE" ]] || { echo "ffprobe not found (PATH or /opt/homebrew/bin/ffprobe)"; exit 1; }
bytes=$(wc -c < "$mp3" | tr -d ' ')
[[ "$bytes" -ge 1024 ]] || { echo "TTS too small (${bytes} bytes)"; head -c 500 "$mp3"; exit 1; }
dur=$("$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "$mp3") \
  || { echo "ffprobe failed"; head -c 500 "$mp3"; exit 1; }
awk -v d="$dur" 'BEGIN { exit (d + 0 >= 0.3) ? 0 : 1 }' \
  || { echo "TTS too short (${dur}s)"; head -c 500 "$mp3"; exit 1; }
```

6. **Durations.** `ffprobe` each validated `<workdir>/beat-NN.mp3` → `<workdir>/durations.txt` (`01 8.42`). The 0.4 s pad is added by `record.mjs`; do not add it again here.

```bash
"$FFPROBE" -v error -show_entries format=duration -of csv=p=0 "<workdir>/beat-NN.mp3"
```

7. **Record.** `node ~/.grok/skills/pr-walkthrough/scripts/record.mjs <workdir>`. Per beat: run `play`, then wait `max(0, durationS + 0.4s - elapsed)`. On failure, stop.

8. **Assemble.** Run `~/.grok/skills/pr-walkthrough/scripts/assemble.sh <workdir>`. Skip this step if no screencast file was written.

9. **Deliver.** Tell the user the mp4 path, duration, and size. On macOS run `open <workdir>/walkthrough.mp4`. If a PR exists and they asked to attach: `gh pr comment --attach <workdir>/walkthrough.mp4` (body: title + one-line summary). If no PR, stop at the file.

10. **Failure modes.** Never commit Fish keys, mp3s, or walkthrough videos into git.
