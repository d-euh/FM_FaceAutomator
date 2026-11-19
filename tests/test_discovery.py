import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageFont
from discovery import discover_defaults, find_name_font
from engine import DEFAULTS


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "app"
        self.graphics = self.root / "Documents/Sports Interactive/Football Manager 27/graphics"
        self.graphics.mkdir(parents=True)
        self.c = copy.deepcopy(DEFAULTS)
        font_patch = patch("discovery.find_name_font", return_value="")
        self.find_font = font_patch.start()
        self.addCleanup(font_patch.stop)
        for key, directory in (("portraits_dir", "portraits"), ("kits_dir", "kits"), ("state_dir", "state"), ("pack_dir", "facepack")):
            self.c[key] = str(self.base / directory)

    def tearDown(self):
        self.temp.cleanup()

    def pack(self, folder, target):
        folder = self.graphics / folder
        folder.mkdir(parents=True)
        Image.new("RGB", (64, 64)).save(folder / "ref.png")
        (folder / "config.xml").write_text(f'<record><list><record from="ref" to="{target}"/></list></record>')
        return str(folder)

    def discover(self):
        with patch("discovery.find_codex", return_value="/usr/bin/codex"):
            return discover_defaults(self.c, self.base, home=self.root, environ={})[0]

    def test_first_run_fills_source_faces_all_kits_output_and_codex(self):
        face = self.pack("faces", "graphics/pictures/person/1/portrait")
        self.pack("kits/leagueA", "graphics/pictures/team/20/kits/home")
        self.pack("kits/leagueB", "graphics/pictures/team/30/kits/home")
        games = self.graphics.parent / "games"; games.mkdir()
        old = games / "old.fm"; old.write_bytes(b"old")
        recent = games / "recent.fm"; recent.write_bytes(b"new")
        os.utime(old, (1, 1)); os.utime(recent, (2, 2))
        found = self.discover()
        self.assertEqual(found["source"], str(recent))
        self.assertEqual(found["portraits_dir"], face)
        self.assertEqual(found["kits_dir"], str(self.graphics / "kits"))
        self.assertEqual(found["pack_dir"], str(self.graphics / "000_FMFaceAutomator"))
        self.assertEqual(found["codex"], "/usr/bin/codex")

    def test_existing_custom_choices_are_preserved_even_when_missing(self):
        self.pack("faces", "graphics/pictures/person/1/portrait")
        self.pack("kits", "graphics/pictures/team/20/kits/home")
        self.c.update(source="D:/chosen.fm", portraits_dir=str(self.root / "myfaces"), kits_dir=str(self.root / "mykits"), pack_dir=str(self.root / "myoutput"), codex="custom-codex")
        self.assertEqual(self.discover(), {})

    def test_nothing_found_does_not_invent_paths(self):
        self.graphics.rmdir()
        with patch("discovery.find_codex", return_value=""):
            found, _ = discover_defaults(self.c, self.base, home=self.root, environ={})
        self.assertEqual(found, {})

    def test_missing_font_path_is_populated_from_validated_system_font(self):
        self.find_font.return_value = str(self.root / "Windows/Fonts/malgunbd.ttf")
        found = self.discover()
        self.assertEqual(found["name_font_path"], self.find_font.return_value)

    def test_existing_font_is_preserved_even_when_file_is_missing(self):
        self.c["name_font_path"] = str(self.root / "my-font.otf")
        self.assertNotIn("name_font_path", self.discover())
        self.find_font.assert_not_called()

    def test_font_search_does_not_invent_a_path_when_no_font_can_be_loaded(self):
        # Call the actual helper rather than the discovery fixture's stub.
        with patch("discovery.name_font", side_effect=ValueError("No usable font")):
            self.assertEqual(find_name_font(), "")

    def test_discovered_font_can_render_an_english_player_name(self):
        font = find_name_font()
        self.assertTrue(Path(font).is_absolute())
        self.assertTrue(Path(font).is_file())
        bounds = ImageFont.truetype(font, 23).getbbox("Djed Spence")
        self.assertGreater(bounds[2] - bounds[0], 0)

    def test_one_drive_and_extra_search_location_are_used(self):
        shared = self.root / "OneDrive/Documents/Sports Interactive/Football Manager 2027/graphics/faces"
        shared.mkdir(parents=True)
        Image.new("RGB", (64, 64)).save(shared / "1.png")
        (shared / "config.xml").write_text('<record><list><record from="1" to="graphics/pictures/person/1/portrait"/></list></record>')
        with patch("discovery.find_codex", return_value=""):
            found, _ = discover_defaults(self.c, self.base, home=self.root, environ={"OneDrive":str(self.root / "OneDrive")})
        self.assertEqual(found["portraits_dir"], str(shared))
