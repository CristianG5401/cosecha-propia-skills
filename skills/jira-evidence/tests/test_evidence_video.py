#!/usr/bin/env python3
"""Behavior tests for jira-evidence's video helper."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "evidence_video.py"
REQUIRED = ("npx", "ffmpeg", "ffprobe")
YELLOW, RED, BLUE = "yellow", "red", "blue"


def load_module():
    spec = importlib.util.spec_from_file_location("evidence_video", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True, text=True)


def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)


def make_red_then_green_raw(path):
    run_ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=3",
        "-f", "lavfi", "-i", "color=c=green:s=640x360:r=30:d=1",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(path),
    )


def make_valid_evidence(path, seconds):
    run_ffmpeg(
        "-f", "lavfi", "-i", f"color=c=blue:s=1920x1080:r=30:d={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(path),
    )


def pixel(image, x, y):
    return subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(image), "-vf", f"crop=1:1:{x}:{y}",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])


def make_red_raw(path):
    run_ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(path),
    )


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_parse_callout_keeps_colons_in_text(self):
        self.assertEqual(
            self.module.parse_callout("1:2.5:10:20:Click Save: now"),
            (1.0, 2.5, 10.0, 20.0, "Click Save: now"),
        )

    def test_parse_callout_rejects_missing_text_and_reversed_times(self):
        for value in ("1:2:10:20", "1:2:10:20:", "2:1:10:20:Text", "-1:2:10:20:Text", "a:2:10:20:Text"):
            with self.assertRaises(self.module.EvidenceError, msg=value):
                self.module.parse_callout(value)

    def test_parse_highlight_requires_positive_box(self):
        self.assertEqual(self.module.parse_highlight("1:2:10:20:30:40"), (1.0, 2.0, 10.0, 20.0, 30.0, 40.0))
        for value in ("1:2:10:20:0:40", "1:2:10:20:30", "2:2:10:20:30:40"):
            with self.assertRaises(self.module.EvidenceError, msg=value):
                self.module.parse_highlight(value)

    def test_fit_frame_matches_padded_1920x1080_layout(self):
        self.assertEqual(self.module.fit_frame(640, 360), (3.0, 0.0, 0.0))
        scale, offset_x, offset_y = self.module.fit_frame(1080, 1920)
        self.assertAlmostEqual(scale, 0.5625)
        self.assertAlmostEqual(offset_x, (1920 - 1080 * 0.5625) / 2)
        self.assertEqual(offset_y, 0.0)

    def test_composition_escapes_text_and_maps_raw_times_and_coordinates(self):
        page = self.module.composition_html(
            title='AC-1 <opens> & "loads"', expected="Shown", result="PASS", observed="Seen",
            video_src="raw.mp4", start=0.5, end=2.5, raw_width=640, raw_height=360,
            callouts=[(0.8, 1.4, 50, 50, "Click <here>")], highlights=[(1.5, 2.2, 200, 150, 100, 60)],
        )
        self.assertIn("AC-1 &lt;opens&gt; &amp; &quot;loads&quot;", page)
        self.assertIn("Click &lt;here&gt;", page)
        self.assertNotIn("<here>", page)
        self.assertIn('data-no-timeline', page)
        self.assertIn('data-duration="6.000"', page)
        self.assertIn('data-media-start="0.500"', page)
        self.assertIn('data-start="2.300" data-duration="0.600"', page)
        self.assertIn("left:150.0px;top:150.0px", page)
        self.assertIn("left:600.0px;top:450.0px;width:300.0px;height:180.0px", page)
        self.assertNotIn("http", page.replace('xmlns="http://www.w3.org', ""))

    def test_compose_rejects_overlay_outside_trim_before_rendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, output = Path(tmp) / "raw.mp4", Path(tmp) / "out.mp4"
            make_red_raw(raw)
            result = run_cli(
                "compose", "--raw", str(raw), "--output", str(output), "--title", "AC",
                "--expected", "E", "--result", "PASS", "--observed", "O", "--start", "0.5", "--end", "2.5",
                "--callout", "3:3.5:10:10:Late",
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("--callout must fall within --start/--end", result.stderr)
            self.assertFalse(output.exists())


@unittest.skipUnless(all(shutil.which(binary) for binary in REQUIRED), "requires npx, ffmpeg, and ffprobe")
class RenderedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp_dir.name)
        cls.raw = cls.root / "raw.mp4"
        cls.output = cls.root / "evidence.mp4"
        make_red_then_green_raw(cls.raw)
        cls.result = run_cli(
            "compose", "--raw", str(cls.raw), "--output", str(cls.output),
            "--title", 'AC-1 <opens> & "loads" ' + "A" * 120, "--expected", "Playback begins",
            "--result", "PASS", "--observed", "Started within one second",
            "--start", "0.5", "--end", "3.5",
            "--callout", "0.8:1.4:50:50:Click <here>: now",
            "--highlight", "1.5:2.2:200:150:100:60",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def color_at(self, seconds, x, y):
        frame = self.root / f"frame-{seconds}.png"
        if not frame.exists():
            run_ffmpeg("-ss", str(seconds), "-i", str(self.output), "-frames:v", "1", str(frame))
        r, g, b = pixel(frame, x, y)
        if r > 200 and g > 150 and b < 100:
            return YELLOW
        if r > 200 and g < 60 and b < 60:
            return RED
        if b > 200 and r < 120:
            return BLUE
        return (r, g, b)

    def test_compose_succeeds_and_cleans_up(self):
        self.assertEqual(self.result.returncode, 0, self.result.stderr)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()
                                if not p.name.startswith("frame-") and p.name != "inspection"),
                         ["evidence.mp4", "raw.mp4"])

    def test_output_matches_evidence_format(self):
        probe = self.module.probe_video(self.output)
        self.assertEqual((probe["width"], probe["height"]), (1920, 1080))
        self.assertEqual((probe["codec"], probe["pix_fmt"], probe["audio_streams"]), ("h264", "yuv420p", 0))
        self.assertAlmostEqual(probe["duration"], 7.0, delta=0.1)

    def test_cards_frame_the_trimmed_recording(self):
        self.assertEqual(self.color_at(1.0, 181, 540), BLUE)
        self.assertEqual(self.color_at(1.0, 1738, 540), BLUE)
        self.assertEqual(self.color_at(3.3, 1000, 900), RED)
        self.assertEqual(self.color_at(5.5, 181, 540), BLUE)

    def test_callout_and_highlight_appear_only_in_their_windows(self):
        self.assertEqual(self.color_at(2.6, 158, 155), YELLOW)
        self.assertEqual(self.color_at(3.3, 158, 155), RED)
        self.assertEqual(self.color_at(3.3, 603, 540), YELLOW)
        self.assertEqual(self.color_at(3.3, 750, 540), RED)
        self.assertEqual(self.color_at(2.6, 603, 540), RED)

    def test_validate_sheet_tiles_the_recording_up_to_the_closing_card(self):
        sheet = self.root / "inspection" / "final-sheet.jpg"
        result = run_cli("validate", "--video", str(self.output), "--sheet", str(sheet))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["sha256"]), 64)
        self.assertEqual(report["sheet"], str(sheet.resolve()))
        self.assertEqual(len(report["sheet_seconds"]), 8)
        self.assertGreaterEqual(report["sheet_seconds"][0], 2.0)
        self.assertLess(report["sheet_seconds"][-1], report["duration"] - 2.0)
        probe = self.module.ffprobe_json(sheet)["streams"][0]
        self.assertEqual((probe["width"], probe["height"]), (1960, 564))
        first = pixel(sheet, 8 + 240, 8 + 135)
        last = pixel(sheet, 8 + 3 * 488 + 240, 8 + 278 + 135)
        self.assertGreater(first[0], 180, "first tile should show the recording, not the opening card")
        self.assertLess(first[1], 80)
        self.assertGreater(last[1], 100, "last tile should show the final recorded state")
        self.assertLess(last[0], 80)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.raw = self.root / "raw.mp4"
        self.output = self.root / "evidence.mp4"
        make_red_raw(self.raw)

    def tearDown(self):
        self.temp_dir.cleanup()

    def compose_args(self, *extra):
        return (
            "compose", "--raw", str(self.raw), "--output", str(self.output),
            "--title", "AC", "--expected", "Expected", "--result", "PASS",
            "--observed", "Observed", "--start", "0", "--end", "1", *extra,
        )

    def test_inspect_writes_metadata_frames_and_contact_sheet(self):
        workdir = self.root / "work"
        result = run_cli("inspect", "--raw", str(self.raw), "--workdir", str(workdir))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report["width"], report["height"]), (640, 360))
        for name in ("metadata.json", "first-frame.png", "last-frame.png", "contact-sheet.jpg"):
            self.assertTrue((workdir / name).is_file(), name)

    def test_compose_refuses_existing_output(self):
        self.output.write_bytes(b"keep me")
        self.assertEqual(run_cli(*self.compose_args()).returncode, 1)
        self.assertEqual(self.output.read_bytes(), b"keep me")

    def test_compose_has_no_redaction_option(self):
        result = run_cli(*self.compose_args("--redact", "0:1:0:0:10:10"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --redact", result.stderr)
        self.assertFalse(self.output.exists())

    def test_validate_refuses_existing_sheet_and_requires_sheet_path(self):
        video = self.root / "valid.mp4"
        make_valid_evidence(video, 6)
        sheet = self.root / "final-sheet.jpg"
        sheet.write_bytes(b"keep me")
        self.assertEqual(run_cli("validate", "--video", str(video), "--sheet", str(sheet)).returncode, 1)
        self.assertEqual(sheet.read_bytes(), b"keep me")
        self.assertEqual(run_cli("validate", "--video", str(video)).returncode, 2)

    def test_validate_rejects_video_without_recording_between_cards(self):
        video = self.root / "short.mp4"
        make_valid_evidence(video, 3)
        sheet = self.root / "short-sheet.jpg"
        result = run_cli("validate", "--video", str(video), "--sheet", str(sheet))
        self.assertEqual(result.returncode, 1)
        self.assertIn("no recording between the opening and closing cards", result.stderr)
        self.assertFalse(sheet.exists())

    def test_validate_rejects_invalid_and_corrupt_video(self):
        sheet = self.root / "sheet.jpg"
        self.assertEqual(run_cli("validate", "--video", str(self.raw), "--sheet", str(sheet)).returncode, 1)
        corrupt = self.root / "corrupt.mp4"
        corrupt.write_text("not a video", encoding="utf-8")
        self.assertEqual(run_cli("validate", "--video", str(corrupt), "--sheet", str(sheet)).returncode, 1)
        self.assertFalse(sheet.exists())


if __name__ == "__main__":
    unittest.main()
