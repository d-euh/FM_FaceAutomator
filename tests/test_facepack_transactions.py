from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import facepack
from engine import write_atomic


class FacepackTransactionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.artifact = self.root / 'new.png'
        self.artifact.write_bytes(b'new image')

    def pack(self, name, image=True, config=True):
        pack = self.root / name
        pack.mkdir()
        if image:
            (pack / '1.png').write_bytes(b'old image')
        if config:
            (pack / 'config.xml').write_bytes(b'<record><!--keep--><list id="maps"><record from="1" to="graphics/pictures/person/1/portrait"/><record from="42" to="graphics/pictures/person/42/portrait"/></list></record>')
        (pack / '42.png').write_bytes(b'unrelated image')
        return pack

    def fail_xml_once(self, after_write):
        failed = False
        def write(path, data):
            nonlocal failed
            if Path(path).name == 'config.xml' and not failed:
                failed = True
                if after_write:
                    write_atomic(path, data)
                raise OSError('simulated XML failure')
            write_atomic(path, data)
        return write

    def test_apply_failure_restores_exact_xml_and_image_or_original_absence(self):
        for image in (False, True):
            for config in (False, True):
                for after_write in (False, True):
                    with self.subTest(image=image, config=config, after_write=after_write):
                        pack = self.pack(f'apply-{image}-{config}-{after_write}', image, config)
                        original = (pack / 'config.xml').read_bytes() if config else None
                        with self.assertRaisesRegex(OSError, 'simulated XML failure'):
                            facepack.apply(pack, '1', 'r-1', self.artifact, 'before', self.fail_xml_once(after_write))
                        self.assertEqual((pack / '1.png').exists(), image)
                        if image:
                            self.assertEqual((pack / '1.png').read_bytes(), b'old image')
                        self.assertEqual((pack / 'config.xml').exists(), config)
                        if config:
                            self.assertEqual((pack / 'config.xml').read_bytes(), original)
                        self.assertEqual((pack / '42.png').read_bytes(), b'unrelated image')

    def test_restore_failure_rolls_back_image_restore_or_deletion_and_xml(self):
        for image in (False, True):
            for after_write in (False, True):
                with self.subTest(image=image, after_write=after_write):
                    pack = self.pack(f'restore-{image}-{after_write}', image)
                    backup = facepack.apply(pack, '1', 'r-1', self.artifact, 'before', write_atomic)
                    current = (pack / 'config.xml').read_bytes()
                    with self.assertRaisesRegex(OSError, 'simulated XML failure'):
                        facepack.restore(pack, backup, self.fail_xml_once(after_write))
                    self.assertEqual((pack / '1.png').read_bytes(), b'new image')
                    self.assertEqual((pack / 'config.xml').read_bytes(), current)
                    self.assertEqual((pack / '42.png').read_bytes(), b'unrelated image')

    def test_failed_image_rollback_still_restores_xml_and_reports_backup(self):
        pack = self.pack('rollback-error')
        before = (pack / 'config.xml').read_bytes()
        failed = False
        def write(path, data):
            nonlocal failed
            if Path(path).name == 'config.xml' and not failed:
                failed = True
                write_atomic(path, data)
                raise OSError('XML failure after replace')
            if failed and Path(path).name == '1.png':
                raise OSError('image rollback unavailable')
            write_atomic(path, data)
        with self.assertRaisesRegex(OSError, '백업:'):
            facepack.apply(pack, '1', 'r-1', self.artifact, 'before', write)
        self.assertEqual((pack / 'config.xml').read_bytes(), before)
        self.assertEqual(next((pack / 'backups').glob('*.images/1.png')).read_bytes(), b'old image')

    def test_apply_parses_xml_once_and_backup_keeps_original_bytes(self):
        pack = self.pack('one-parse')
        original = (pack / 'config.xml').read_bytes()
        with patch.object(facepack, 'document', wraps=facepack.document) as parse:
            backup = facepack.apply(pack, '1', 'r-1', self.artifact, 'before', write_atomic)
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(backup.read_bytes(), original)
