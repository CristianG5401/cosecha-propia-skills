#!/usr/bin/env python3
"""Create and verify reviewable Jira evidence videos with local macOS tools."""

import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


class EvidenceError(Exception):
    """A clean, actionable command failure."""


def tool(name):
    path = shutil.which(name)
    if not path:
        raise EvidenceError(f"required tool not found on PATH: {name}")
    return path


def run(args, *, text=True):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=text)
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


def svg_text(value, y, size):
    lines = textwrap.wrap(
        value.replace("\x00", ""), width=58, break_long_words=True, break_on_hyphens=False,
    ) or [" "]
    return "".join(
        f'<text x="960" y="{y + index * (size + 18)}" text-anchor="middle" '
        f'font-family="Arial, sans-serif" font-size="{size}" fill="#ffffff">'
        f"{html.escape(line, quote=True)}</text>"
        for index, line in enumerate(lines)
    )


def write_card_svg(path, heading, lines):
    body = svg_text(heading, 300, 64)
    for index, line in enumerate(lines):
        body += svg_text(line, 470 + index * 125, 42)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">'
        '<rect width="1920" height="1080" fill="#111827"/>'
        '<rect x="180" y="180" width="1560" height="720" rx="24" fill="#1f2937" stroke="#3b82f6" stroke-width="4"/>'
        f"{body}</svg>",
        encoding="utf-8",
    )


def render_card(svg, output, tempdir):
    ql_output = tempdir / f"ql-{svg.stem}"
    ql_output.mkdir()
    run([tool("qlmanage"), "-t", "-s", "1920", "-o", str(ql_output), str(svg)])
    thumbnails = list(ql_output.glob("*.png"))
    if len(thumbnails) != 1:
        raise EvidenceError("qlmanage did not create exactly one PNG thumbnail")
    # qlmanage emits a 1920x1920 preview for SVG; the card lives in its top 1080 px.
    run([
        tool("ffmpeg"), "-v", "error", "-i", str(thumbnails[0]), "-vf", "crop=1920:1080:0:0",
        "-frames:v", "1", "-y", str(output),
    ])


def parse_redaction(value, raw_width, raw_height):
    try:
        start, end, x, y, width, height = (float(part) for part in value.split(":"))
    except ValueError as error:
        raise EvidenceError("--redact must be START:END:X:Y:W:H") from error
    if start < 0 or end <= start or x < 0 or y < 0 or width <= 0 or height <= 0:
        raise EvidenceError("--redact values must be positive, with END after START")
    if x + width > raw_width or y + height > raw_height:
        raise EvidenceError("--redact rectangle must fit within raw source dimensions")
    return start, end, x, y, width, height


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
    redact_filter = ""
    if args.redact:
        start, end, x, y, width, height = parse_redaction(args.redact, raw_report["width"], raw_report["height"])
        redact_filter = (
            f"drawbox=x={x}:y={y}:w={width}:h={height}:color=black:t=fill:"
            f"enable='between(t,{start},{end})',"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jira-evidence-", dir=output.parent) as tmp:
        tempdir = Path(tmp)
        opening_svg, closing_svg = tempdir / "opening.svg", tempdir / "closing.svg"
        opening_png, closing_png = tempdir / "opening.png", tempdir / "closing.png"
        write_card_svg(opening_svg, args.title, [f"Expected: {args.expected}"])
        write_card_svg(closing_svg, args.result, [f"Observed: {args.observed}"])
        render_card(opening_svg, opening_png, tempdir)
        render_card(closing_svg, closing_png, tempdir)
        body = (
            f"{redact_filter}trim=start={args.start}:end={args.end},setpts=PTS-STARTPTS,"
            "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )
        temp_output = tempdir / "output.mp4"
        run([
            tool("ffmpeg"), "-v", "error", "-loop", "1", "-t", "2", "-i", str(opening_png),
            "-i", str(raw), "-loop", "1", "-t", "2", "-i", str(closing_png), "-filter_complex",
            f"[0:v]fps=30,format=yuv420p[open];[1:v]{body}[body];[2:v]fps=30,format=yuv420p[close];"
            "[open][body][close]concat=n=3:v=1:a=0[video]",
            "-map", "[video]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-movflags", "+faststart", str(temp_output),
        ])
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


def validate(args):
    print(json.dumps(validate_video(args.video), indent=2))


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
    compose_parser.add_argument("--redact")
    compose_parser.set_defaults(func=compose)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--video", required=True)
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
