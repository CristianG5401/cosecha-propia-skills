#!/usr/bin/env python3
"""Create and verify reviewable Jira evidence videos with ffmpeg and HyperFrames."""

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from string import Template


CARD_SECONDS = 2.0
SHEET_TILES = 8


class EvidenceError(Exception):
    """A clean, actionable command failure."""


def tool(name):
    path = shutil.which(name)
    if not path:
        raise EvidenceError(f"required tool not found on PATH: {name}")
    return path


def run(args, *, text=True, cwd=None, env=None):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=text, cwd=cwd, env=env)
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        raise EvidenceError(f"command failed ({Path(args[0]).name}): {detail.strip()[-1000:]}") from error


def ffprobe_json(video):
    result = run([
        tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video),
    ])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise EvidenceError("ffprobe did not return JSON") from error


def fraction(value):
    numerator, denominator = value.split("/", 1)
    denominator = float(denominator)
    if not denominator:
        raise ValueError("zero denominator")
    return float(numerator) / denominator


def probe_video(video):
    document = ffprobe_json(video)
    streams = document.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise EvidenceError(f"expected exactly one video stream; found {len(videos)}")
    stream = videos[0]
    try:
        duration = float(document["format"]["duration"])
        frame_rate = fraction(stream.get("avg_frame_rate", "0/1"))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise EvidenceError("video metadata is incomplete") from error
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": frame_rate,
        "pix_fmt": stream.get("pix_fmt"),
        "duration": duration,
        "audio_streams": len(audios),
        "metadata": document,
    }


def require_file(path, label):
    if not path.is_file():
        raise EvidenceError(f"{label} does not exist or is not a file: {path}")


def require_absent(path):
    if path.exists():
        raise EvidenceError(f"refusing to overwrite existing output: {path}")


def extract_frame(raw, output, timestamp):
    run([
        tool("ffmpeg"), "-v", "error", "-ss", f"{timestamp:.3f}", "-i", str(raw),
        "-frames:v", "1", "-y", str(output),
    ])


def inspect(args):
    raw = Path(args.raw).expanduser().resolve()
    workdir = Path(args.workdir).expanduser().resolve()
    require_file(raw, "raw video")
    workdir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "metadata": workdir / "metadata.json",
        "first_frame": workdir / "first-frame.png",
        "last_frame": workdir / "last-frame.png",
        "contact_sheet": workdir / "contact-sheet.jpg",
    }
    for output in outputs.values():
        require_absent(output)
    report = probe_video(raw)
    outputs["metadata"].write_text(json.dumps(report["metadata"], indent=2) + "\n", encoding="utf-8")
    extract_frame(raw, outputs["first_frame"], 0)
    extract_frame(raw, outputs["last_frame"], max(report["duration"] - 0.1, 0))
    run([
        tool("ffmpeg"), "-v", "error", "-i", str(raw), "-vf",
        "fps=1/2,scale=480:-2,tile=2x2:padding=8:margin=8", "-frames:v", "1", "-y",
        str(outputs["contact_sheet"]),
    ])
    result = {key: str(value) for key, value in outputs.items()}
    result.update({key: report[key] for key in ("codec", "width", "height", "fps", "duration")})
    print(json.dumps(result, indent=2))


HYPERFRAMES = "hyperframes@0.8.155"
FRAME_WIDTH, FRAME_HEIGHT = 1920, 1080
PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1920px; height: 1080px; overflow: hidden; background: #111827; font-family: Arial, Helvetica, sans-serif; }
.clip { position: absolute; inset: 0; }
.card { display: flex; align-items: center; justify-content: center; }
.panel { width: 1560px; min-height: 720px; max-height: 1000px; overflow: hidden; background: #1f2937; border: 4px solid #3b82f6; border-radius: 24px; color: #fff; text-align: center; padding: 60px 80px; display: flex; flex-direction: column; justify-content: center; gap: 48px; }
.panel h1 { font-size: 64px; overflow-wrap: anywhere; }
.panel p { font-size: 42px; overflow-wrap: anywhere; }
video.clip { width: 1920px; height: 1080px; object-fit: contain; background: #000; }
.callout, .highlight { inset: auto; z-index: 2; }
.callout { max-width: 900px; padding: 12px 24px; border-radius: 12px; background: #facc15; color: #111827; font-size: 40px; font-weight: bold; overflow-wrap: anywhere; }
.highlight { border: 8px solid #facc15; border-radius: 8px; }
</style>
</head>
<body>
<div id="root" data-composition-id="evidence" data-no-timeline data-start="0" data-duration="$total" data-width="1920" data-height="1080">
<section id="opening" class="clip card" data-start="0" data-duration="$card"><div class="panel"><h1>$title</h1><p>Expected: $expected</p></div></section>
<video id="recording" class="clip" src="$src" muted playsinline data-start="$card" data-duration="$body" data-media-start="$start"></video>
$overlays
<section id="closing" class="clip card" data-start="$closing" data-duration="$card"><div class="panel"><h1>$result</h1><p>Observed: $observed</p></div></section>
</div>
</body>
</html>
""")


def seconds(value):
    return f"{value:.3f}"


def parse_numbers(values, flag, form):
    try:
        numbers = tuple(float(value) for value in values)
    except ValueError as error:
        raise EvidenceError(f"{flag} must be {form}") from error
    start, end = numbers[:2]
    if start < 0 or end <= start or any(number < 0 for number in numbers[2:]):
        raise EvidenceError(f"{flag} needs non-negative values with END after START")
    return numbers


def parse_callout(value):
    parts = value.split(":", 4)
    if len(parts) != 5 or not parts[4].strip():
        raise EvidenceError("--callout must be START:END:X:Y:TEXT")
    return (*parse_numbers(parts[:4], "--callout", "START:END:X:Y:TEXT"), parts[4])


def parse_highlight(value):
    parts = value.split(":")
    if len(parts) != 6:
        raise EvidenceError("--highlight must be START:END:X:Y:W:H")
    numbers = parse_numbers(parts, "--highlight", "START:END:X:Y:W:H")
    if numbers[4] <= 0 or numbers[5] <= 0:
        raise EvidenceError("--highlight width and height must be positive")
    return numbers


def fit_frame(width, height):
    """Scale and offsets that place the raw frame inside the padded 1920x1080 frame."""
    scale = min(FRAME_WIDTH / width, FRAME_HEIGHT / height)
    return scale, (FRAME_WIDTH - width * scale) / 2, (FRAME_HEIGHT - height * scale) / 2


def require_overlay_fits(flag, overlay, args, raw_report):
    start, end, x, y = overlay[:4]
    width, height = (overlay[4], overlay[5]) if flag == "--highlight" else (0, 0)
    if start < args.start or end > args.end:
        raise EvidenceError(f"{flag} must fall within --start/--end")
    if x + width > raw_report["width"] or y + height > raw_report["height"]:
        raise EvidenceError(f"{flag} must fit within raw source dimensions")


def composition_html(*, title, expected, result, observed, video_src, start, end,
                     raw_width, raw_height, callouts, highlights):
    scale, offset_x, offset_y = fit_frame(raw_width, raw_height)

    def place(x, y):
        return f"left:{offset_x + x * scale:.1f}px;top:{offset_y + y * scale:.1f}px"

    def timing(overlay_start, overlay_end):
        return (
            f'data-start="{seconds(CARD_SECONDS + overlay_start - start)}" '
            f'data-duration="{seconds(overlay_end - overlay_start)}"'
        )

    overlays = [
        f'<div id="callout-{index}" class="clip callout" style="{place(x, y)}" {timing(t0, t1)}>'
        f"{html.escape(text, quote=True)}</div>"
        for index, (t0, t1, x, y, text) in enumerate(callouts, 1)
    ] + [
        f'<div id="highlight-{index}" class="clip highlight" '
        f'style="{place(x, y)};width:{width * scale:.1f}px;height:{height * scale:.1f}px" {timing(t0, t1)}></div>'
        for index, (t0, t1, x, y, width, height) in enumerate(highlights, 1)
    ]
    body = end - start
    return PAGE.substitute(
        total=seconds(body + 2 * CARD_SECONDS), card=seconds(CARD_SECONDS), body=seconds(body),
        closing=seconds(CARD_SECONDS + body), start=seconds(start), src=html.escape(video_src, quote=True),
        title=html.escape(title, quote=True), expected=html.escape(expected, quote=True),
        result=html.escape(result, quote=True), observed=html.escape(observed, quote=True),
        overlays="\n".join(overlays),
    )


def render_composition(page, raw, video_src, tempdir):
    project = tempdir / "project"
    project.mkdir()
    (project / "index.html").write_text(page, encoding="utf-8")
    (project / video_src).symlink_to(raw)
    output = tempdir / "output.mp4"
    env = os.environ | {"HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_SKIP_SKILLS": "1"}
    run([
        tool("npx"), "--yes", HYPERFRAMES, "render", "--fps", "30", "--video-frame-format", "png",
        "--frames-cache-dir", str(tempdir / "frames"), "--quiet", "--output", str(output),
    ], cwd=project, env=env)
    return output


def compose(args):
    raw = Path(args.raw).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    require_file(raw, "raw video")
    require_absent(output)
    if args.end <= args.start:
        raise EvidenceError("--end must be greater than --start")
    raw_report = probe_video(raw)
    if args.start < 0 or args.end > raw_report["duration"]:
        raise EvidenceError("trim range must be within the raw video duration")
    callouts = [parse_callout(value) for value in args.callout]
    highlights = [parse_highlight(value) for value in args.highlight]
    for flag, overlays in (("--callout", callouts), ("--highlight", highlights)):
        for overlay in overlays:
            require_overlay_fits(flag, overlay, args, raw_report)
    video_src = f"recording{raw.suffix.lower()}"
    page = composition_html(
        title=args.title, expected=args.expected, result=args.result, observed=args.observed,
        video_src=video_src, start=args.start, end=args.end, raw_width=raw_report["width"],
        raw_height=raw_report["height"], callouts=callouts, highlights=highlights,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jira-evidence-", dir=output.parent) as tmp:
        temp_output = render_composition(page, raw, video_src, Path(tmp))
        validate_video(temp_output)
        os.replace(temp_output, output)
    duration = probe_video(output)["duration"]
    if not 20 <= duration <= 60:
        print(f"warning: final duration {duration:.2f}s is outside the 20-60s target", file=sys.stderr)
    print(json.dumps({"output": str(output), "duration": duration}, indent=2))


def validate_video(video):
    video = Path(video).expanduser().resolve()
    require_file(video, "video")
    report = probe_video(video)
    failures = []
    for key, expected in (("codec", "h264"), ("width", 1920), ("height", 1080), ("pix_fmt", "yuv420p"), ("audio_streams", 0)):
        if report[key] != expected:
            failures.append(f"{key} is {report[key]!r}, expected {expected!r}")
    if abs(report["fps"] - 30) > 0.01:
        failures.append(f"fps is {report['fps']:.4f}, expected 30")
    if failures:
        raise EvidenceError("invalid evidence video: " + "; ".join(failures))
    run([tool("ffmpeg"), "-v", "error", "-i", str(video), "-map", "0:v:0", "-f", "null", "-"])
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    return {key: report[key] for key in ("codec", "width", "height", "fps", "pix_fmt", "duration", "audio_streams")} | {
        "bytes": video.stat().st_size,
        "sha256": digest,
    }


def write_sheet(video, sheet, duration):
    """Tile evenly spaced frames of the recording, ending just before the closing card."""
    sheet = Path(sheet).expanduser().resolve()
    require_absent(sheet)
    last = duration - CARD_SECONDS - 0.1
    if last <= CARD_SECONDS:
        raise EvidenceError("no recording between the opening and closing cards")
    seconds = [round(CARD_SECONDS + (last - CARD_SECONDS) * index / (SHEET_TILES - 1), 3) for index in range(SHEET_TILES)]
    sheet.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jira-evidence-sheet-", dir=sheet.parent) as tmp:
        tempdir = Path(tmp)
        for index, second in enumerate(seconds):
            run([
                tool("ffmpeg"), "-v", "error", "-ss", f"{second:.3f}", "-i", str(video),
                "-frames:v", "1", "-vf", "scale=480:-2", f"tile-{index:02d}.png",
            ], cwd=tempdir)
        run([
            tool("ffmpeg"), "-v", "error", "-i", "tile-%02d.png", "-vf", "tile=4x2:padding=8:margin=8",
            "-frames:v", "1", "sheet.jpg",
        ], cwd=tempdir)
        os.replace(tempdir / "sheet.jpg", sheet)
    return sheet, seconds


def validate(args):
    report = validate_video(args.video)
    sheet, seconds = write_sheet(Path(args.video).expanduser().resolve(), args.sheet, report["duration"])
    print(json.dumps(report | {"sheet": str(sheet), "sheet_seconds": seconds}, indent=2))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--raw", required=True)
    inspect_parser.add_argument("--workdir", required=True)
    inspect_parser.set_defaults(func=inspect)
    compose_parser = commands.add_parser("compose")
    compose_parser.add_argument("--raw", required=True)
    compose_parser.add_argument("--output", required=True)
    compose_parser.add_argument("--title", required=True)
    compose_parser.add_argument("--expected", required=True)
    compose_parser.add_argument("--result", required=True)
    compose_parser.add_argument("--observed", required=True)
    compose_parser.add_argument("--start", required=True, type=float)
    compose_parser.add_argument("--end", required=True, type=float)
    compose_parser.add_argument("--callout", action="append", default=[], metavar="START:END:X:Y:TEXT")
    compose_parser.add_argument("--highlight", action="append", default=[], metavar="START:END:X:Y:W:H")
    compose_parser.set_defaults(func=compose)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--video", required=True)
    validate_parser.add_argument("--sheet", required=True, help="new image to write: frames of the recording between the cards")
    validate_parser.set_defaults(func=validate)
    return result


def main():
    try:
        arguments = parser().parse_args()
        arguments.func(arguments)
        return 0
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
