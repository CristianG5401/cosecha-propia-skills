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

Keep one AC per row. Honor state dependencies: evidence for a later state follows the AC that establishes it. Prefer `TEST` for technical behavior: record the exact command, result summary, and relevant output in the manifest; do not make terminal video. Use `SOURCE` for code/config references. Use `VIDEO` only where visible behavior needs it. User records manually; do not start browser/OS recording.

## Video evidence

Before any compose operation, inspect each user-provided raw clip:

```bash
python3 <skill-dir>/scripts/evidence_video.py inspect --raw raw/AC-1.mp4 --workdir inspection/AC-1
```

Review the raw and its first/last frames/contact sheet for sensitive data. If any is suspected, **stop**. Ask the user to choose **crop**, **redact**, or **re-record**. Never decide, infer approval, or process sensitive raw first.

After the user approves the AC and any redaction, compose one short clip. The command creates two-second opening/closing cards, trims the approved range, preserves aspect ratio in a padded 1920×1080 frame, outputs 30 fps H.264/yuv420p/faststart without audio, and atomically moves the output only after validation. `--redact` is an approved timed black box in raw source coordinates.

```bash
python3 <skill-dir>/scripts/evidence_video.py compose \
  --raw raw/AC-1.mp4 --output AC-1.mp4 --title "AC-1: profile opens" \
  --expected "Profile screen appears" --result PASS --observed "Visible after selection" \
  --start 12 --end 34 --redact 14:18:120:80:420:90
python3 <skill-dir>/scripts/evidence_video.py validate --video AC-1.mp4
```

The helper needs macOS `qlmanage`, `ffmpeg`, `ffprobe`, and `libx264`. It refuses output overwrite, preserves inputs on failure, and warns when final runtime falls outside 20–60 seconds.

## Finish

Update the approved matrix as each AC is complete. `PASS`, `FAIL`, `PARTIAL`, and `BLOCKED` must say what a reviewer can verify and link the local video, command/output, or source reference. Do not auto-publish, delete raws, mutate Jira/GitHub/Git, or create a release/upload.

## Common mistakes

- Do not make video for an AC that a command or source reference proves better.
- Do not process a sensitive clip before the user makes an explicit choice.
- Do not reorder dependent state or overwrite an evidence file.
