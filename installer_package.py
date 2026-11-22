"""Compile the Windows installer and publish a two-file distribution ZIP."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from release_package import MANIFEST, verify_release


def find_compiler(explicit=None):
    if explicit:
        candidates = [Path(explicit)]
    else:
        executable = shutil.which('ISCC.exe') or shutil.which('iscc')
        candidates = [Path(executable)] if executable else []
        for key in ('ProgramFiles(x86)', 'ProgramFiles'):
            if os.environ.get(key):
                candidates.append(Path(os.environ[key]) / 'Inno Setup 6' / 'ISCC.exe')
        if os.environ.get('LOCALAPPDATA'):
            candidates.append(Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe')
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError('설치 EXE 빌드에는 Inno Setup 6.3 이상이 필요합니다. https://jrsoftware.org/isdl.php 에서 설치하거나 '
                     '--iscc "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"로 지정하세요. '
                     '배포받는 사용자에게는 Inno Setup과 Python이 필요하지 않습니다.')


def inno_text(value):
    # Braces in literal filenames must not become Inno constants.
    return str(value).replace('{', '{{').replace('"', '""')


def write_includes(bundle, directory):
    bundle, directory = Path(bundle).resolve(), Path(directory)
    info = verify_release(bundle)
    names = sorted([*info['files'], MANIFEST])
    files, backup = [], ['procedure AddProgramFiles(Files: TStringList);', 'begin']
    for name in names:
        relative = name.replace('/', '\\')
        parent = relative.rpartition('\\')[0]
        destination = '{app}' + ('\\' + inno_text(parent) if parent else '')
        files.append(f'Source: "{inno_text(bundle / name)}"; DestDir: "{destination}"; Flags: ignoreversion')
        backup.append("  Files.Add('" + relative.replace("'", "''") + "');")
    backup.append('end;')
    file_list, backup_list = directory / 'installer-files.iss', directory / 'installer-backup.iss'
    file_list.write_text('\n'.join(files) + '\n', encoding='utf-8-sig')
    backup_list.write_text('\n'.join(backup) + '\n', encoding='utf-8-sig')
    return file_list, backup_list


def create_installer_archive(bundle, destination, *, root, version, compiler, runner=subprocess.run):
    root, destination = Path(root).resolve(), Path(destination)
    if not re.fullmatch(r'\d+(?:\.\d+){0,3}', version):
        raise ValueError('설치 버전은 숫자 1~4개를 점으로 구분해야 합니다.')
    version_info = '.'.join([*version.split('.'), *(['0'] * (4 - len(version.split('.'))))])
    with tempfile.TemporaryDirectory(prefix='installer-', dir=Path(bundle).parent) as temporary:
        stage = Path(temporary)
        files, backup = write_includes(bundle, stage)
        readme = (root / 'docs' / 'DISTRIBUTION_README.txt').read_text(encoding='utf-8-sig')
        readme_file = stage / 'README.txt'
        readme_file.write_bytes(readme.replace('\n', '\r\n').encode('utf-8-sig'))
        script = stage / 'setup.iss'
        script.write_text((root / 'packaging' / 'setup.iss').read_text(encoding='utf-8-sig'), encoding='utf-8-sig')
        runner([str(compiler), '/Qp', f'/DAppVersion={version}', f'/DFFAVersionInfo={version_info}',
                f'/DFFAOutputDir={stage}', f'/DFFAFiles={files}', f'/DFFABackupList={backup}',
                f'/DFFAIcon={root / "icons" / "ffa.ico"}', f'/DFFAReadme={readme_file}',
                str(script)], cwd=root, check=True)
        installer = stage / f'FMFaceAutomator-Setup-v{version}.exe'
        with installer.open('rb') as stream:
            if stream.read(2) != b'MZ':
                raise ValueError('설치 EXE 빌드 결과가 올바르지 않습니다.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, staging_zip = tempfile.mkstemp(prefix='.setup-release-', suffix='.zip', dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(staging_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(installer, installer.name)
                archive.write(readme_file, 'README.txt')
            os.replace(staging_zip, destination)
        finally:
            Path(staging_zip).unlink(missing_ok=True)
    return destination
