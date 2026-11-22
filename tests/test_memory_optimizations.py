import gc
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image, PngImagePlugin
from assets import AssetCatalog
from manual_ui import ManualPanel
import test_queue_controls as fixtures


class MemoryOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QueueControlTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.e = self.fixture.engine

    def test_refresh_releases_the_previous_catalog_before_allocating_a_new_one(self):
        folder = self.e.c['portraits_dir']
        old = weakref.ref(self.e.asset_catalog(folder))
        def build(*args, **kwargs):
            gc.collect()
            self.assertIsNone(old())
            return AssetCatalog(*args, **kwargs)
        with patch('engine.AssetCatalog', side_effect=build):
            refreshed = self.e.asset_catalog(folder, refresh=True)
        self.assertEqual(refreshed.face('1')[0], Path(folder) / '1.png')

    def test_missing_reference_refresh_releases_exception_traceback_and_finds_new_file(self):
        folder = self.e.c['portraits_dir']
        old = weakref.ref(self.e.asset_catalog(folder))
        photo = Path(folder) / '404.png'
        Image.new('RGB', (350, 350), 'gray').save(photo)
        def build(*args, **kwargs):
            gc.collect()
            self.assertIsNone(old())
            return AssetCatalog(*args, **kwargs)
        with patch('engine.AssetCatalog', side_effect=build):
            self.assertEqual(self.e.lookup_asset(folder, 'face', '404')[0], photo)

    def test_close_releases_cached_catalogs(self):
        old = weakref.ref(self.e.asset_catalog(self.e.c['portraits_dir']))
        self.e.close()
        gc.collect()
        self.assertIsNone(old())

    def test_expired_unchanged_catalog_is_reused_but_xml_changes_are_seen(self):
        folder = self.e.c['portraits_dir']
        catalog = self.e.asset_catalog(folder)
        checked = self.e._asset_catalogs[folder][0]
        with patch('engine.time.monotonic', return_value=checked + 61), patch('engine.AssetCatalog', side_effect=AssertionError('unnecessary rebuild')):
            self.assertIs(self.e.asset_catalog(folder), catalog)
        xml = Path(folder) / 'config.xml'
        xml.write_text('<record><list><record from="2" to="graphics/pictures/person/404/portrait"/></list></record>')
        with patch('engine.time.monotonic', return_value=checked + 122):
            replacement = self.e.asset_catalog(folder)
        self.assertIsNot(replacement, catalog)
        self.assertEqual(replacement.face('404')[0], Path(folder) / '2.png')

    def test_manual_preview_is_small_and_original_reference_is_unchanged(self):
        photo = self.fixture.root / 'large.png'
        with Image.new('RGB', (2048, 1024), 'gray') as image:
            image.save(photo)
        original = photo.read_bytes()
        panel = SimpleNamespace(player={'id': '1'}, parent=Mock(), reference_name=Mock(),
                                remove_photo_button=Mock(), draw_reference=Mock())
        with patch('manual_ui.filedialog.askopenfilename', return_value=str(photo)):
            ManualPanel.choose_reference(panel)
        self.addCleanup(panel.reference_image.close)
        self.assertEqual(panel.reference_image.size, (512, 256))
        self.assertEqual(panel.reference_path, str(photo))
        self.assertEqual(photo.read_bytes(), original)

    def test_catalog_detects_xml_rewrite_even_when_size_and_mtime_are_preserved(self):
        folder = self.e.c['portraits_dir']
        xml = Path(folder) / 'config.xml'
        xml.write_text('<record><record from="2" to="graphics/pictures/person/404/portrait"/></record>')
        catalog = self.e.asset_catalog(folder)
        original = xml.stat()
        xml.write_text(xml.read_text().replace('/404/', '/405/'))
        os.utime(xml, ns=(original.st_atime_ns, original.st_mtime_ns))
        checked = self.e._asset_catalogs[folder][0]
        with patch('engine.time.monotonic', return_value=checked + 61):
            replacement = self.e.asset_catalog(folder)
        self.assertIsNot(replacement, catalog)
        self.assertEqual(replacement.face('405')[0], Path(folder) / '2.png')

    def test_recent_cards_refill_past_corruption_and_detect_an_old_file_rewritten(self):
        paths = []
        with self.e.db:
            for i in range(5):
                path = self.fixture.root / f'valid-{i}.png'
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text('PlayerName', f'Card {i}')
                Image.new('RGB', (350, 350), 'gray').save(path, pnginfo=metadata)
                os.utime(path, (100+i, 100+i))
                paths.append(path)
                self.e.db.execute("INSERT INTO jobs(player_id,data,status,created,artifact) VALUES ('test',?,'applied',1,?)",
                                  (json.dumps({'name':'Test', 'club_name':'Club', 'unused':'x'*200000}), str(path)))
            for i in range(35):
                path = self.fixture.root / f'broken-{i}.png'
                path.write_bytes(b'broken')
                os.utime(path, (200+i, 200+i))
                self.e.db.execute("INSERT INTO jobs(player_id,data,status,created,artifact) VALUES ('test','{}','applied',1,?)", (str(path),))
        queries = []
        self.e.db.set_trace_callback(queries.append)
        try:
            cards = self.e.recent_results()
        finally:
            self.e.db.set_trace_callback(None)
        self.assertEqual([card['name'] for card in cards], ['Card 4','Card 3','Card 2','Card 1','Card 0'])
        self.assertEqual(sum(query.startswith('SELECT data,status,artifact') for query in queries), 5)
        self.assertFalse(any(query.startswith('SELECT id,data,artifact') for query in queries))
        os.utime(paths[0], (500, 500))
        self.assertEqual(self.e.recent_results()[0]['name'], 'Card 0')
