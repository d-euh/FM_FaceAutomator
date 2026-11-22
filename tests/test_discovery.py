import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from discovery import discover_defaults, sample_pack
from engine import DEFAULTS


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "app"
        self.graphics = self.root / "Documents/Sports Interactive/Football Manager 27/graphics"
        self.graphics.mkdir(parents=True)
        self.c = copy.deepcopy(DEFAULTS)
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

    def test_empty_font_is_not_replaced_by_system_font_discovery(self):
        self.c["name_font_path"] = ""
        self.assertNotIn("name_font_path", self.discover())

    def test_one_drive_and_extra_search_location_are_used(self):
        shared = self.root / "OneDrive/Documents/Sports Interactive/Football Manager 2027/graphics/faces"
        shared.mkdir(parents=True)
        Image.new("RGB", (64, 64)).save(shared / "1.png")
        (shared / "config.xml").write_text('<record><list><record from="1" to="graphics/pictures/person/1/portrait"/></list></record>')
        with patch("discovery.find_codex", return_value=""):
            found, _ = discover_defaults(self.c, self.base, home=self.root, environ={"OneDrive":str(self.root / "OneDrive")})
        self.assertEqual(found["portraits_dir"], str(shared))

    def test_saved_paths_skip_all_asset_directory_searches(self):
        face = self.pack('faces', 'graphics/pictures/person/1/portrait')
        kits = self.pack('kits', 'graphics/pictures/team/20/kits/home')
        self.c.update(source=str(self.root / 'career.fm'), portraits_dir=face,
                      kits_dir=kits, pack_dir=str(self.graphics / 'output'), codex='custom-codex')
        with patch('discovery.discover_roots', side_effect=AssertionError('unnecessary root search')):
            self.assertEqual(self.discover(), {})

    def test_output_only_discovery_does_not_scan_pack_contents(self):
        self.c.update(source=str(self.root / 'career.fm'), portraits_dir=str(self.graphics),
                      kits_dir=str(self.graphics), codex='custom-codex')
        with patch('discovery.discover_packs', side_effect=AssertionError('unnecessary pack search')):
            self.assertEqual(self.discover(), {'pack_dir': str(self.graphics / '000_FMFaceAutomator')})

    def test_first_run_classification_does_not_resolve_or_stat_individual_images(self):
        face = self.pack('faces', 'graphics/pictures/person/1/portrait')
        self.pack('kits', 'graphics/pictures/team/20/kits/home')
        with patch.object(Path, 'is_file', side_effect=AssertionError('image file validation during startup')):
            found = self.discover()
        self.assertEqual(found['portraits_dir'], face)
        self.assertEqual(found['kits_dir'], str(self.graphics / 'kits'))

    def test_large_xml_is_sampled_without_reading_the_whole_pack(self):
        xml = self.graphics / 'config.xml'
        xml.write_text('<record><list>' + '<record from="ref" to="graphics/pictures/person/1/portrait"/>' * 20000 + '</list></record>')
        original_open = Path.open
        reads = []

        class Reader:
            def __enter__(self):
                self.stream = original_open(xml, 'rb')
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, size):
                data = self.stream.read(size)
                reads.append(len(data))
                return data

        with patch.object(Path, 'open', return_value=Reader()):
            self.assertGreater(sample_pack(xml)['faces'], 0)
        self.assertLessEqual(sum(reads), 256 * 1024)
        self.assertGreater(xml.stat().st_size, sum(reads))

    def test_textures_and_comments_are_not_mistaken_for_2d_kits(self):
        xml = self.graphics / 'config.xml'
        xml.write_text('<record><!-- <record to="graphics/pictures/team/20/kits/home"/> -->'
                       '<record to="graphics/pictures/team/20/kit_textures/home"/></record>')
        self.assertEqual(sample_pack(xml), {'faces': 0, 'kits': 0})

    def test_sample_counts_do_not_drop_other_facepacks(self):
        self.pack('faces/packA', 'graphics/pictures/person/1/portrait')
        self.pack('faces/packB', 'graphics/pictures/person/2/portrait')
        self.assertEqual(self.discover()['portraits_dir'], str(self.graphics / 'faces'))

    def test_dtd_and_managed_output_are_not_used_as_source_candidates(self):
        folder = Path(self.pack('faces', 'graphics/pictures/person/1/portrait'))
        (folder / '.fm-face-owner').touch()
        kits = Path(self.pack('kits', 'graphics/pictures/team/20/kits/home'))
        (kits / 'config.xml').write_text('<!DOCTYPE record [<!ENTITY x "test">]><record/>')
        found = self.discover()
        self.assertNotIn('portraits_dir', found)
        self.assertNotIn('kits_dir', found)

    def test_cancelled_search_does_not_publish_partial_paths(self):
        stop = threading.Event()
        stop.set()
        with patch('discovery.discover_roots', side_effect=AssertionError('cancelled search started')):
            self.assertEqual(discover_defaults(self.c, self.base, home=self.root, environ={}, stop=stop), ({}, []))
