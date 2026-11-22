import gc
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref

from PIL import Image, PngImagePlugin
from assets import AssetCatalog
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
