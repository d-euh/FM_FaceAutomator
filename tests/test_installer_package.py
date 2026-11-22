import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch
import zipfile

from installer_package import create_installer_archive, find_compiler, write_includes
from release_package import MANIFEST
from scripts.build_release import build_release
import test_release_package as fixtures


class InstallerPackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReleaseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.bundle = self.fixture.source
        project = Path(__file__).resolve().parents[1]
        for name in ('packaging/setup.iss', 'docs/DISTRIBUTION_README.txt'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / name, target)
        self.compiler = self.root / 'ISCC.exe'
        self.compiler.write_bytes(b'MZ mock compiler')

    def compiler_runner(self, command, **kwargs):
        output = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DFFAOutputDir=')))
        readme = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DFFAReadme=')))
        self.assertTrue(readme.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertTrue(Path(command[-1]).read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertIn('/DFFAVersionInfo=1.0.0.0', command)
        (output / 'FMFaceAutomator-Setup-v1.0.exe').write_bytes(b'MZ mock setup')

    def test_distribution_zip_contains_exactly_setup_and_korean_readme(self):
        (self.bundle / 'config.json').write_text('private settings')
        destination = self.root / 'release.zip'
        create_installer_archive(self.bundle, destination, root=self.root, version='1.0',
                                 compiler=self.compiler, runner=self.compiler_runner)
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(archive.namelist(), ['FMFaceAutomator-Setup-v1.0.exe', 'README.txt'])
            raw = archive.read('README.txt')
            text = raw.decode('utf-8-sig')
            self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
            self.assertIn('\r\n', text)
            self.assertIn('설치 방법 및 주의사항', text)
            self.assertIn('26620374', text)
            self.assertIn('기존 사용자 업데이트', text)
            self.assertIn('설정·작업 기록·페이스팩', text)
            self.assertNotIn('private settings', text)

    def test_install_and_backup_lists_include_only_verified_program_files(self):
        (self.bundle / 'config.json').write_text('private config')
        directory = self.root / 'includes'
        directory.mkdir()
        files, backup = write_includes(self.bundle, directory)
        entries = files.read_text(encoding='utf-8-sig').splitlines()
        info = json.loads((self.bundle / MANIFEST).read_text())
        self.assertEqual(len(entries), len(info['files']) + 1)
        self.assertTrue(all('DestDir: "{app}' in entry for entry in entries))
        self.assertFalse(any('recursesubdirs' in entry or '*' in entry for entry in entries))
        self.assertNotIn('config.json', files.read_text(encoding='utf-8-sig'))
        self.assertNotIn('config.json', backup.read_text(encoding='utf-8-sig'))
        script = (self.root / 'packaging/setup.iss').read_text()
        self.assertNotIn('[InstallDelete]', script)
        self.assertNotIn('[UninstallDelete]', script)
        self.assertIn('program-backups', script)
        self.assertIn('FileCopy(Source, Target, False)', script)
        self.assertIn('IsLinkedPath', script)
        self.assertIn('CloseApplications=yes', script)
        self.assertIn('UsePreviousAppDir=yes', script)

    def test_tampered_manifest_cannot_include_user_config_in_installer(self):
        info = json.loads((self.bundle / MANIFEST).read_text())
        info['files']['config.json'] = '0' * 64
        (self.bundle / MANIFEST).write_text(json.dumps(info))
        runner = Mock()
        with self.assertRaisesRegex(ValueError, '허용되지 않은'):
            create_installer_archive(self.bundle, self.root / 'bad.zip', root=self.root,
                                     version='1.0', compiler=self.compiler, runner=runner)
        runner.assert_not_called()

    def test_compile_failure_preserves_previous_release_and_existing_installation(self):
        archive = self.root / 'previous.zip'
        archive.write_bytes(b'previous release')
        runner = Mock(side_effect=subprocess.CalledProcessError(1, ['ISCC']))
        with self.assertRaises(subprocess.CalledProcessError):
            create_installer_archive(self.bundle, archive, root=self.root,
                                     version='1.0', compiler=self.compiler, runner=runner)
        self.assertEqual(archive.read_bytes(), b'previous release')
        self.assertEqual(self.fixture.snapshot(self.fixture.target), self.fixture.user_data)

    def test_invalid_installer_output_is_not_published(self):
        def broken_runner(command, **kwargs):
            self.compiler_runner(command, **kwargs)
            output = Path(next(arg.split('=', 1)[1] for arg in command if arg.startswith('/DFFAOutputDir=')))
            (output / 'FMFaceAutomator-Setup-v1.0.exe').write_bytes(b'not PE')
        with self.assertRaisesRegex(ValueError, '설치 EXE'):
            create_installer_archive(self.bundle, self.root / 'bad.zip', root=self.root,
                                     version='1.0', compiler=self.compiler, runner=broken_runner)
        self.assertFalse((self.root / 'bad.zip').exists())

    def test_installer_build_preflights_compiler_and_keeps_portable_installation(self):
        (self.root / 'docs/QUICK_START.ko.md').write_text('guide')
        def runner(command, **kwargs):
            if 'PyInstaller' in command:
                output = Path(command[command.index('--distpath') + 1]) / 'FMFaceAutomator'
                self.fixture.make_payload(output)
            elif command[0] == str(self.compiler):
                self.compiler_runner(command, **kwargs)
        with patch('scripts.build_release.sys.platform', 'win32'), patch('scripts.build_release.platform.machine', return_value='AMD64'):
            result = build_release(self.root, runner=runner, make_setup=True, iscc=self.compiler)
        with zipfile.ZipFile(result) as archive:
            self.assertEqual(len(archive.namelist()), 2)
        self.assertEqual(self.fixture.snapshot(self.fixture.target), self.fixture.user_data)

    def test_missing_compiler_stops_before_pyinstaller_or_old_zip_changes(self):
        runner = Mock()
        with patch('scripts.build_release.sys.platform', 'win32'), patch('scripts.build_release.platform.machine', return_value='AMD64'):
            with self.assertRaisesRegex(ValueError, 'Inno Setup'):
                build_release(self.root, runner=runner, make_setup=True, iscc=self.root / 'missing.exe')
        runner.assert_not_called()

    def test_compiler_search_accepts_explicit_location(self):
        self.assertEqual(find_compiler(self.compiler), self.compiler)
        with self.assertRaisesRegex(ValueError, 'Inno Setup'):
            find_compiler(self.root / 'absent.exe')
