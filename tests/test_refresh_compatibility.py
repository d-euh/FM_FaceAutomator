import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from refresh_compatibility import HELPER, export_compatibility
from refresh_diagnostics import validate_game


class RefreshCompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'steamapps/common/Football Manager 27'
        (self.game / 'BepInEx/interop').mkdir(parents=True)
        for name in ('fm.exe', 'GameAssembly.dll', 'BepInEx/interop/FM.UI.dll'):
            (self.game / name).write_bytes(b'MZ fixture')
        self.manifest = self.root / 'steamapps/appmanifest_test.acf'
        self.manifest.write_text('"name" "Football Manager 27" "installdir" "Football Manager 27" "buildid" "26797085"')
        self.bundle = self.root / 'tool'
        self.bundle.mkdir()
        self.executable = self.bundle / HELPER
        self.executable.write_bytes(b'MZ read-only helper fixture')
        (self.bundle / 'SHA256SUMS').write_text(hashlib.sha256(self.executable.read_bytes()).hexdigest() + '  ' + HELPER)
        self.output = self.root / 'report.json'
        self.output.write_bytes(b'old report')
        self.report = dict(kind='fm_refresh_compatibility', schema_version=1, tool_version='0.1.0',
                           mode='metadata_only', game_methods_invoked=False, refresh_available=False,
                           detected_steam_build='26797085', errors=[])
        self.before = {p: p.read_bytes() for p in self.game.rglob('*') if p.is_file()}

    def runner(self, command, **kwargs):
        self.assertEqual(command[:2], [str(self.executable), str(self.game)])
        self.assertFalse(kwargs['shell'])
        Path(command[2]).write_text(json.dumps(self.report))
        return SimpleNamespace(returncode=0)

    def test_new_build_exports_without_game_execution_installation_or_source_changes(self):
        target = export_compatibility(self.game, self.output, bundle=self.bundle, runner=self.runner)
        self.assertEqual(json.loads(target.read_text()), self.report)
        self.assertEqual(self.before, {p: p.read_bytes() for p in self.game.rglob('*') if p.is_file()})
        self.assertFalse((self.game / 'BepInEx/plugins').exists())
        with self.assertRaisesRegex(ValueError, '26620374'):
            validate_game(self.game)

    def test_corrupt_helper_is_rejected_before_running_or_replacing_report(self):
        self.executable.write_bytes(b'MZ corrupted')
        runner = Mock()
        with self.assertRaisesRegex(ValueError, '손상'):
            export_compatibility(self.game, self.output, bundle=self.bundle, runner=runner)
        runner.assert_not_called()
        self.assertEqual(self.output.read_bytes(), b'old report')

    def test_bad_build_or_execution_claim_cannot_replace_previous_report(self):
        for change in ({'detected_steam_build': '26620374'}, {'game_methods_invoked': True},
                       {'refresh_available': True}, {'kind': 'other'}):
            with self.subTest(change=change):
                original = copy.deepcopy(self.report)
                self.report.update(change)
                with self.assertRaises(ValueError):
                    export_compatibility(self.game, self.output, bundle=self.bundle, runner=self.runner)
                self.assertEqual(self.output.read_bytes(), b'old report')
                self.report = original

    def test_game_folder_output_and_stale_output_on_helper_failure_are_rejected(self):
        runner = Mock(return_value=SimpleNamespace(returncode=1))
        with self.assertRaisesRegex(ValueError, '게임 폴더 밖'):
            export_compatibility(self.game, self.game / 'report.json', bundle=self.bundle, runner=runner)
        runner.assert_not_called()
        with self.assertRaisesRegex(ValueError, '추출 실패'):
            export_compatibility(self.game, self.output, bundle=self.bundle, runner=runner)
        self.assertEqual(self.output.read_bytes(), b'old report')

    def test_steam_update_during_export_keeps_old_report(self):
        def changed(command, **kwargs):
            result = self.runner(command, **kwargs)
            self.manifest.write_text(self.manifest.read_text().replace('26797085', '99999999'))
            return result
        with self.assertRaisesRegex(ValueError, '설치 정보가 바뀌'):
            export_compatibility(self.game, self.output, bundle=self.bundle, runner=changed)
        self.assertEqual(self.output.read_bytes(), b'old report')
