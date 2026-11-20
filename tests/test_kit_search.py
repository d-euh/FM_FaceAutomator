import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from kit_search import KIT_SEASON, validate_web_kit


class KitSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGB',(200,300),'green').save(self.root/'kit.png')
        self.metadata = {'season':KIT_SEASON,'club_id':'680','variant':'gk_away','verified_club':'Manchester United',
                         'source_url':'https://club.example/2026-27-gk','image_url':'https://club.example/kit.png'}

    def source(self, **changes):
        (self.root/'kit-source.json').write_text(json.dumps(self.metadata | changes))

    def test_exact_season_club_and_keeper_variant_are_accepted(self):
        self.source()
        self.assertEqual(validate_web_kit(self.root,'680','gk_away'),self.metadata)

    def test_different_season_club_variant_or_missing_evidence_are_rejected(self):
        for changes in ({'season':'2027/28'}, {'season':'26/27'}, {'club_id':'602'}, {'variant':'away'},
                        {'verified_club':''}, {'source_url':'file:///local'}, {'image_url':'http://example.com/kit.png'},
                        {'source_url':'https://user:secret@club.example/kit'}, {'image_url':None}):
            with self.subTest(changes=changes):
                self.source(**changes)
                with self.assertRaises(ValueError):
                    validate_web_kit(self.root,'680','gk_away')

    def test_download_must_be_a_decodable_png_and_not_a_missing_or_fake_image(self):
        self.source()
        for data in (b'not a png', b'\x89PNG\r\n\x1a\ntruncated'):
            (self.root/'kit.png').write_bytes(data)
            with self.assertRaises((OSError,ValueError)):
                validate_web_kit(self.root,'680','gk_away')

    def test_symlinked_reference_is_rejected(self):
        self.source()
        target=self.root/'outside.png'
        (self.root/'kit.png').rename(target)
        try:
            (self.root/'kit.png').symlink_to(target)
        except OSError:
            self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError):
            validate_web_kit(self.root,'680','gk_away')
