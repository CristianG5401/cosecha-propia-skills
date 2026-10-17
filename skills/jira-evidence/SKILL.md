---
name: jira-evidence
description: Use when assembling auditable Jira acceptance-criteria evidence, especially when a ticket needs a mixed video, test, and source manifest without publishing artifacts.
---

# Jira Evidence

Build evidence a reviewer can inspect, not a presentation. Work in `~/Movies/<TICKET>-evidence/`: preserve user-recorded raw clips in `raw/`; write the English `manifest.md` from [the template](references/manifest-template.md). Never overwrite an artifact.

## Evidence plan first

Read the Jira issue **read-only**, or accept pasted acceptance criteria. Propose this English matrix and wait for explicit approval before recording or processing:

| AC | Evidence | Status | Dependency | Expected proof |
|---|---|---|---|---|
| AC-1 | `VIDEO` \| `TEST` \| `SOURCE` | `PLANNED` \| `PASS` \| `FAIL` \| `PARTIAL` \| `BLOCKED` | prior ACs | concise reviewer check |

Keep one AC per row. Honor state dependencies: evidence for a later state follows the AC that establishes it. Prefer `TEST` for technical behavior: record the exact command, result summary, and relevant output in the manifest; do not make terminal video. Use `SOURCE` for code/config references. Use `VIDEO` only where visible behavior needs it. User records manually; do not start browser/OS recording. Before the user records a `VIDEO` row, read [the recording guide](references/recording-guide.md) and give one guide per AC.

## Video evidence

Inspect each user-provided raw clip to choose the trim range; use its duration, first/last frames, and contact sheet to find where the AC's visible behavior starts and ends:

```bash
python3 <skill-dir>/scripts/evidence_video.py inspect --raw raw/AC-1.mp4 --workdir inspection/AC-1
```

After the user approves the AC, compose one short clip. The command renders two-second opening/closing cards around the approved range with HyperFrames, preserves aspect ratio in a padded 1920×1080 frame, outputs 30 fps H.264/yuv420p/faststart without audio, and atomically moves the output only after validation.

```bash
python3 <skill-dir>/scripts/evidence_video.py compose \
  --raw raw/AC-1.mp4 --output AC-1.mp4 --title "AC-1: profile opens" \
  --expected "Profile screen appears" --result PASS --observed "Visible after selection" \
  --start 12 --end 34 \
  --callout "14:17:640:300:Click Profile" --highlight "18:22:600:250:500:120"
python3 <skill-dir>/scripts/evidence_video.py validate --video AC-1.mp4 --sheet inspection/AC-1/final-sheet.jpg
```

Use optional, repeatable overlays only to point the reviewer at the proof: `--callout START:END:X:Y:TEXT` shows a label; `--highlight START:END:X:Y:W:H` outlines a box. Times are raw-clip seconds inside `--start`/`--end`; coordinates are raw-clip pixels, the same values you read from `inspect` frames.

`validate` writes a contact sheet of the composed clip's recording, ending just before the closing card. Open it and confirm its last tiles show the guide's **Reviewer must see** result; if they do not, re-compose with a new output name and adjusted `--start`/`--end`. Mark the AC `PASS` only after that check, and paste the exact `compose` command into the manifest.

The helper needs Node.js 22+ (`npx`), `ffmpeg`, and `ffprobe`. The first render downloads HyperFrames' headless Chrome (~200 MB) to `~/.cache/hyperframes`. Do not run `hyperframes init`: it installs global agent skills and a Whisper model. The helper refuses output overwrite, preserves inputs on failure, and warns when final runtime falls outside 20–60 seconds.

## Finish

Update the approved matrix as each AC is complete. `PASS`, `FAIL`, `PARTIAL`, and `BLOCKED` must say what a reviewer can verify and link the local video, command/output, or source reference. Do not auto-publish, delete raws, mutate Jira/GitHub/Git, or create a release/upload.

## Common mistakes

- Do not make video for an AC that a command or source reference proves better.
- Do not reorder dependent state or overwrite an evidence file.
