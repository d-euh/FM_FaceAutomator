import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from release_package import (MANIFEST, REQUIRED, apply_update, create_archive,
                             prepare_release, verify_release)
from release_tools import install_plugins
from scripts.build_release import build_release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'new'
        self.source.mkdir()
        self.guide = self.root / 'guide.md'
        self.guide.write_text('안내', encoding='utf-8')
        self.make_payload(self.source)
        prepare_release(self.source, self.guide, '1.0')
        self.target = self.root / 'installed'
        self.target.mkdir()
        (self.target / 'FMFaceAutomator.exe').write_bytes(b'old app')
        for name in ('config.json', 'state/queue.sqlite', 'workspaces/save/queue.sqlite',
                     'facepack/1.png', 'facepack/config.xml', 'portraits/custom.png',
                     'kits/20.png', '.refresh-diagnostics.json', 'unrelated.txt', '_internal/private/note.txt'):
            file = self.target / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('keep ' + name).encode())
        self.user_data = self.snapshot(self.target)

    def make_payload(self, folder):
        for name in REQUIRED:
            file = folder / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('new ' + name).encode())
        for checksum in folder.rglob('SHA256SUMS'):
            binary = next(p for p in checksum.parent.iterdir() if p.suffix in ('.dll', '.exe'))
            checksum.write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + '  ' + binary.name)

    def snapshot(self, folder):
        return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}

    def test_update_preserves_all_user_data_and_backs_up_replaced_program(self):
        backup = apply_update(self.source, self.target)
        self.assertEqual((backup / 'FMFaceAutomator.exe').read_bytes(), b'old app')
        self.assertEqual((self.target / 'FMFaceAutomator.exe').read_bytes(), b'new FMFaceAutomator.exe')
        for name, data in self.user_data.items():
            if name != 'FMFaceAutomator.exe':
                self.assertEqual((self.target / name).read_bytes(), data, name)
        verify_release(self.target)

    def test_copy_failure_rolls_back_program_files_and_preserves_user_data(self):
        count = 0
        def fail_once(source, target):
            nonlocal count
            count += 1
            if count == 5:
                raise PermissionError('simulated locked file')
            os.replace(source, target)
        with self.assertRaisesRegex(ValueError, '복원했습니다'):
            apply_update(self.source, self.target, replace=fail_once)
        self.assertEqual(self.snapshot(self.target), self.user_data)

    def test_corrupt_release_is_rejected_before_destination_changes(self):
        (self.source / 'FMFaceAutomator.exe').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '손상'):
            apply_update(self.source, self.target)
        self.assertEqual(self.snapshot(self.target), self.user_data)

    def test_companion_original_checksum_is_checked_even_if_manifest_was_regenerated(self):
        name = '_internal/plugins/FMFaceRefresh/FMFaceRefresh.dll'
        (self.source / name).write_bytes(b'corrupted DLL')
        info = json.loads((self.source / MANIFEST).read_text())
        info['files'][name] = hashlib.sha256(b'corrupted DLL').hexdigest()
        (self.source / MANIFEST).write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError, '해시가 다릅니다'):
            apply_update(self.source, self.target)
        self.assertEqual(self.snapshot(self.target), self.user_data)

    def test_manifest_cannot_overwrite_user_data_or_escape_destination(self):
        original = (self.source / MANIFEST).read_text()
        for name in ('config.json', 'state/queue.sqlite', '../config.json', '/absolute',
                     '_internal/../config.json', '_internal\\bad', '_internal/CON', 'fmfaceautomator.exe'):
            with self.subTest(name=name):
                info = json.loads(original)
                info['files'][name] = '0' * 64
                (self.source / MANIFEST).write_text(json.dumps(info))
                with self.assertRaises(ValueError):
                    apply_update(self.source, self.target)
                self.assertEqual(self.snapshot(self.target), self.user_data)

    def test_destination_symlink_does_not_modify_external_files(self):
        outside = self.root / 'outside'
        outside.mkdir()
        file = outside / 'ffa.ico'
        file.write_bytes(b'keep external')
        try:
            (self.target / '_internal/icons').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaisesRegex(ValueError, '링크'):
            apply_update(self.source, self.target)
        self.assertEqual(file.read_bytes(), b'keep external')

    def test_cannot_update_from_same_or_nested_installation(self):
        for destination in (self.source, self.source / 'nested', self.root):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, '설치 폴더 밖'):
                apply_update(self.source, destination)

    def test_locked_installation_is_rejected_before_copy(self):
        with patch('release_package.check_closed', side_effect=ValueError('close app')):
            with self.assertRaisesRegex(ValueError, 'close app'):
                apply_update(self.source, self.target)
        self.assertEqual(self.snapshot(self.target), self.user_data)

    def test_archive_contains_only_manifest_files_and_launchers_need_no_python(self):
        (self.source / 'config.json').write_text('private settings')
        archive = create_archive(self.source, self.root / 'release.zip')
        with zipfile.ZipFile(archive) as stream:
            names = stream.namelist()
            self.assertNotIn('FMFaceAutomator/config.json', names)
            for name in ('install_live_refresh.bat', 'update_windows.bat'):
                script = stream.read('FMFaceAutomator/' + name).decode('ascii')
                self.assertIn('FMFaceTools.exe', script)
                self.assertNotIn('python', script.lower())
                self.assertNotIn('.venv', script)
            self.assertFalse(any('FMTeamBindings' in name or 'FMTeamMetadata' in name for name in names))
            self.assertNotIn('FMFaceAutomator/install_team_bindings.bat', names)
        with self.assertRaisesRegex(ValueError, '사용자 파일'):
            prepare_release(self.source, self.guide, '1.0')

    def test_missing_required_resource_prevents_packaging(self):
        (self.source / '_internal/fonts/koverwatch.ttf').unlink()
        with self.assertRaises(FileNotFoundError):
            create_archive(self.source, self.root / 'bad.zip')
        self.assertFalse((self.root / 'bad.zip').exists())

    def test_build_uses_fresh_dist_path_and_never_changes_installed_dist(self):
        root = self.root / 'repo'
        legacy = root / 'dist' / 'FMFaceAutomator'
        legacy.mkdir(parents=True)
        (legacy / 'config.json').write_text('existing private config')
        (root / 'docs').mkdir()
        (root / 'docs/QUICK_START.ko.md').write_text('guide')
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            if 'PyInstaller' in command:
                output = Path(command[command.index('--distpath') + 1]) / 'FMFaceAutomator'
                self.assertFalse(output.exists())
                self.assertFalse(output.is_relative_to(root / 'dist'))
                self.make_payload(output)
        with patch('scripts.build_release.sys.platform', 'win32'), patch('scripts.build_release.platform.machine', return_value='AMD64'):
            result = build_release(root, runner=runner)
            result2 = build_release(root, runner=runner)
        self.assertEqual((legacy / 'config.json').read_text(), 'existing private config')
        self.assertTrue(result.is_file())
        self.assertEqual(result, result2)
        self.assertEqual(len([call for call in calls if 'PyInstaller' in call]), 2)
        self.assertEqual(len([call for call in calls if any('verify_windows_icon.py' in part for part in call)]), 4)

    def test_failed_build_preserves_previous_zip_and_installed_config(self):
        root = self.root / 'repo'
        installed = root / 'dist/FMFaceAutomator'
        installed.mkdir(parents=True)
        (installed / 'config.json').write_bytes(b'keep config')
        archive = root / 'dist/FMFaceAutomator-Portable-v1.0-windows-x64.zip'
        archive.write_bytes(b'keep previous release')
        def failed_runner(*args, **kwargs):
            raise RuntimeError('build failed')
        with patch('scripts.build_release.sys.platform', 'win32'), patch('scripts.build_release.platform.machine', return_value='AMD64'):
            with self.assertRaisesRegex(RuntimeError, 'build failed'):
                build_release(root, runner=failed_runner)
        self.assertEqual((installed / 'config.json').read_bytes(), b'keep config')
        self.assertEqual(archive.read_bytes(), b'keep previous release')


class ReleasePluginTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'steamapps/common/Football Manager 27'
        core = self.game / 'BepInEx/core'
        core.mkdir(parents=True)
        for name in ('fm.exe', 'GameAssembly.dll'):
            (self.game / name).write_bytes(b'MZ game fixture')
        (core / 'BepInEx.Core.dll').write_bytes(b'6.0.0-be.793')
        (core / 'BepInEx.Unity.IL2CPP.dll').write_bytes(b'MZ')
        self.manifest = self.root / 'steamapps/appmanifest_123.acf'
        self.manifest.write_text('"name" "Football Manager 27" "installdir" "Football Manager 27" "buildid" "26620374"')
        self.bundle = self.root / 'plugins'
        for folder in ('FMTeamBindings', 'FMFaceRefresh'):
            directory = self.bundle / folder
            directory.mkdir(parents=True)
            payload = b'MZ ' + folder.encode()
            (directory / (folder + '.dll')).write_bytes(payload)
            (directory / 'SHA256SUMS').write_text(hashlib.sha256(payload).hexdigest() + '  ' + folder + '.dll')

    def test_installs_only_refresh_preserving_existing_team_dll_loader_and_unrelated_plugins(self):
        old_team = self.game / 'BepInEx/plugins/FMTeamBindings/FMTeamBindings.dll'
        old_team.parent.mkdir(parents=True)
        old_team.write_bytes(b'preserve existing team plugin')
        (self.bundle / 'FMTeamBindings/FMTeamBindings.dll').unlink()
        other = self.game / 'BepInEx/plugins/Other/Other.dll'
        other.parent.mkdir(parents=True)
        other.write_bytes(b'keep')
        with patch('release_tools.game_process_running', return_value=False):
            targets = install_plugins(self.game, bundle=self.bundle)
        self.assertEqual(len(targets), 1)
        self.assertEqual(old_team.read_bytes(), b'preserve existing team plugin')
        self.assertTrue(all(path.is_file() for path in targets))
        self.assertEqual(other.read_bytes(), b'keep')
        self.assertEqual((self.game / 'BepInEx/core/BepInEx.Core.dll').read_bytes(), b'6.0.0-be.793')

    def test_running_game_unsupported_build_or_corrupt_dll_prevents_install(self):
        with patch('release_tools.game_process_running', return_value=True), self.assertRaisesRegex(ValueError, '종료'):
            install_plugins(self.game, bundle=self.bundle)
        self.manifest.write_text(self.manifest.read_text().replace('26620374', '999'))
        with patch('release_tools.game_process_running', return_value=False), self.assertRaisesRegex(ValueError, '26620374'):
            install_plugins(self.game, bundle=self.bundle)
        self.manifest.write_text(self.manifest.read_text().replace('999', '26620374'))
        (self.bundle / 'FMFaceRefresh/FMFaceRefresh.dll').write_bytes(b'bad')
        with patch('release_tools.game_process_running', return_value=False), self.assertRaisesRegex(ValueError, '손상'):
            install_plugins(self.game, bundle=self.bundle)
        self.assertFalse((self.game / 'BepInEx/plugins').exists())
