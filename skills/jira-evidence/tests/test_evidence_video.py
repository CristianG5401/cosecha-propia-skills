#!/usr/bin/env python3
"""Behavior tests for jira-evidence's stdlib video helper."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "evidence_video.py"
REQUIRED = ("qlmanage", "ffmpeg", "ffprobe")


@unittest.skipUnless(all(shutil.which(binary) for binary in REQUIRED), "requires qlmanage, ffmpeg, and ffprobe")
class EvidenceVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("evidence_video", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workdir = Path(self.temp_dir.name) / "work"
        self.workdir.mkdir()
        self.raw = Path(self.temp_dir.name) / "raw.mp4"
        self.output = Path(self.temp_dir.name) / "evidence.mp4"
        self.run_ffmpeg(
            "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(self.raw),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_ffmpeg(self, *args):
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True, text=True)

    def run_cli(self, *args, expected_returncode=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args], text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, expected_returncode, result.stderr)
        return result

    def compose(self, *, title="AC-1 playback starts"):
        return self.run_cli(
            "compose", "--raw", str(self.raw), "--output", str(self.output),
            "--title", title, "--expected", "Playback begins",
            "--result", "PASS", "--observed", "Started within one second",
            "--start", "0.5", "--end", "2.5", "--redact", "0:4:0:0:200:200",
        )

    def test_inspect_writes_metadata_frames_and_contact_sheet(self):
        result = self.run_cli("inspect", "--raw", str(self.raw), "--workdir", str(self.workdir))
        report = json.loads(result.stdout)
        self.assertEqual(report["width"], 640)
        self.assertEqual(report["height"], 360)
        for name in ("metadata.json", "first-frame.png", "last-frame.png", "contact-sheet.jpg"):
            self.assertTrue((self.workdir / name).is_file(), name)

    def test_compose_trims_adds_cards_and_redacts_requested_source_rectangle(self):
        self.compose()
        self.assertTrue(self.output.is_file())
        probe = self.module.probe_video(self.output)
        self.assertEqual((probe["width"], probe["height"]), (1920, 1080))
        self.assertEqual(probe["codec"], "h264")
        self.assertEqual(probe["pix_fmt"], "yuv420p")
        self.assertEqual(probe["audio_streams"], 0)
        self.assertGreaterEqual(probe["duration"], 5.8)  # 2 s trim + two 2 s cards
        frame = Path(self.temp_dir.name) / "body.png"
        self.run_ffmpeg("-ss", "2.3", "-i", str(self.output), "-frames:v", "1", str(frame))
        pixel = subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", str(frame), "-vf", "crop=1:1:300:300",
            "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ])
        self.assertLess(max(pixel), 20, "approved redaction should be black")

    def test_compose_refuses_existing_output(self):
        self.output.write_bytes(b"keep me")
        self.run_cli(
            "compose", "--raw", str(self.raw), "--output", str(self.output),
            "--title", "AC", "--expected", "Expected", "--result", "PASS",
            "--observed", "Observed", "--start", "0", "--end", "1",
            expected_returncode=1,
        )
        self.assertEqual(self.output.read_bytes(), b"keep me")

    def test_compose_renders_long_card_text_with_xml_characters_at_wrap_boundary(self):
        title = "A" * 57 + '<&"' + "B" * 60
        card = Path(self.temp_dir.name) / "card.svg"
        self.module.write_card_svg(card, title, ["Expected: Playback begins"])
        ET.parse(card)
        self.compose(title=title)
        self.assertTrue(self.output.is_file())

    def test_validate_accepts_composed_video(self):
        self.compose()
        report = json.loads(self.run_cli("validate", "--video", str(self.output)).stdout)
        self.assertEqual(report["codec"], "h264")
        self.assertEqual(report["audio_streams"], 0)
        self.assertEqual(len(report["sha256"]), 64)

    def test_validate_rejects_invalid_and_corrupt_video(self):
        invalid = Path(self.temp_dir.name) / "small.mp4"
        self.run_ffmpeg(
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(invalid),
        )
        self.run_cli("validate", "--video", str(invalid), expected_returncode=1)
        corrupt = Path(self.temp_dir.name) / "corrupt.mp4"
        corrupt.write_text("not a video", encoding="utf-8")
        self.run_cli("validate", "--video", str(corrupt), expected_returncode=1)


if __name__ == "__main__":
    unittest.main()
