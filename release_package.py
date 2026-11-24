"""Build and update a portable release without replacing user data directories."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

MANIFEST = 'release-manifest.json'
LAUNCHERS = {
    'install_live_refresh.bat': '--install-refresh',
    'export_diagnostics.bat': '--export-diagnostics',
    'update_windows.bat': '--update',
}
ROOT_FILES = {'FMFaceAutomator.exe', 'FMFaceTools.exe', 'QUICK_START.ko.md', *LAUNCHERS}
REQUIRED = {
    'FMFaceAutomator.exe', 'FMFaceTools.exe', 'QUICK_START.ko.md', *LAUNCHERS,
    '_internal/icons/ffa.ico', '_internal/icons/ffa.png',
    '_internal/fonts/koverwatch.ttf', '_internal/fonts/BebasNeue.otf',
    '_internal/fonts/venus rising rg.ttf',
    '_internal/fonts/README.md',
}
for folder, dll in (('FMFaceRefresh', 'FMFaceRefresh.dll'),
                    ('FMFaceRefreshDiagnostics', 'FMFaceRefresh.Diagnostics.dll')):
    REQUIRED.update({f'_internal/plugins/{folder}/{dll}', f'_internal/plugins/{folder}/SHA256SUMS'})


def digest(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def owned_path(name):
    """Only release resources can ever be replaced; root user files are excluded."""
    path = PurePosixPath(name)
    devices = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if (not name or '\\' in name or path.is_absolute() or path.as_posix() != name
            or any(part in ('.', '..') or ':' in part or part.endswith((' ', '.'))
                   or part.split('.')[0].upper() in devices for part in path.parts)):
        return False
    return name in ROOT_FILES or (len(path.parts) > 1 and path.parts[0] == '_internal')


def reject_links(path, root):
    current = path
    while current != root.parent:
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ValueError(f'링크·정션 경로에는 업데이트할 수 없습니다: {current}')
        if current == root:
            break
        current = current.parent


def verify_release(folder):
    folder = Path(folder).resolve()
    manifest = folder / MANIFEST
    if manifest.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('배포 목록 크기가 올바르지 않습니다.')
    info = json.loads(manifest.read_text(encoding='utf-8'))
    files = info.get('files')
    if info.get('schema_version') != 1 or not isinstance(files, dict) or not REQUIRED <= files.keys():
        raise ValueError('필수 파일이 빠진 배포 묶음입니다.')
    seen = set()
    for name, expected in files.items():
        if not owned_path(name) or name.casefold() in seen:
            raise ValueError(f'배포 목록에 허용되지 않은 경로가 있습니다: {name}')
        seen.add(name.casefold())
        file = folder / name
        reject_links(file, folder)
        if not isinstance(expected, str) or len(expected) != 64 or digest(file) != expected:
            raise ValueError(f'배포 파일이 누락되었거나 손상됐습니다: {name}')
    checksum_files = [folder / name for name in sorted(REQUIRED) if name.endswith('/SHA256SUMS')]
    for checksum in checksum_files:
        fields = checksum.read_text(encoding='ascii').split()
        if len(fields) != 2 or Path(fields[1]).name != fields[1] or '/' in fields[1] or '\\' in fields[1]:
            raise ValueError(f'게임 연동 도구의 배포 정보가 올바르지 않습니다: {checksum}')
        if digest(checksum.parent / fields[1]) != fields[0]:
            raise ValueError(f'게임 연동 도구의 해시가 다릅니다: {fields[1]}')
    return info


def prepare_release(folder, guide, version):
    """Only call this on a fresh build directory, never an installed copy."""
    folder = Path(folder)
    shutil.copyfile(guide, folder / 'QUICK_START.ko.md')
    for name, command in LAUNCHERS.items():
        text = ('@echo off\r\ncd /d "%~dp0"\r\n'
                f'"%~dp0FMFaceTools.exe" {command}\r\n'
                'set "ffa_exit=%errorlevel%"\r\npause\r\nexit /b %ffa_exit%\r\n')
        (folder / name).write_bytes(text.encode('ascii'))
    files = {}
    for file in sorted(folder.rglob('*')):
        reject_links(file, folder)
        if file.is_file():
            relative = file.relative_to(folder).as_posix()
            if not owned_path(relative):
                raise ValueError(f'배포에 사용자 파일 또는 예상 밖의 파일이 포함됐습니다: {relative}')
            files[relative] = digest(file)
    (folder / MANIFEST).write_text(json.dumps({'schema_version': 1, 'app_version': version, 'files': files},
                                             ensure_ascii=False, indent=2), encoding='utf-8')
    verify_release(folder)


def create_archive(folder, destination):
    folder, destination = Path(folder), Path(destination)
    info = verify_release(folder)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.release-', suffix='.zip', dir=destination.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in [*info['files'], MANIFEST]:
                archive.write(folder / name, f'FMFaceAutomator/{name}')
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def check_closed(folder):
    if os.name != 'nt':
        return
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                  ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    for name in ('FMFaceAutomator.exe', 'FMFaceTools.exe'):
        file = folder / name
        if not file.exists():
            continue
        handle = kernel.CreateFileW(str(file), 0x40000000, 0, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ValueError('기존 FM Face Automator와 도구를 종료하고 설치 폴더의 쓰기 권한을 확인하세요.')
        kernel.CloseHandle(handle)


def apply_update(source, destination, replace=os.replace):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('새 ZIP은 기존 설치 폴더 밖에 풀고 그 안의 업데이트 도구를 실행하세요.')
    reject_links(destination, destination)
    if not (destination / 'FMFaceAutomator.exe').is_file():
        raise ValueError('기존 FMFaceAutomator.exe가 있는 폴더를 선택하세요.')
    info = verify_release(source)
    names = [*info['files'], MANIFEST]
    for name in names:
        target = destination / name
        reject_links(target, destination)
        if target.exists() and not target.is_file():
            raise ValueError(f'프로그램 파일 위치에 폴더가 있습니다: {target}')
    check_closed(destination)
    backup = Path(tempfile.mkdtemp(prefix='FMFaceAutomator-backup-', dir=destination.parent))
    changed = []
    with tempfile.TemporaryDirectory(prefix='.ffa-update-', dir=destination.parent) as temporary:
        stage = Path(temporary)
        try:
            for name in names:
                staged = stage / name
                staged.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, staged)
            verify_release(stage)
            for name in names:
                target = destination / name
                reject_links(target, destination)
                previous = backup / name
                existed = target.exists()
                if existed:
                    previous.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, previous)
                target.parent.mkdir(parents=True, exist_ok=True)
                replace(stage / name, target)
                changed.append((name, existed))
        except Exception as exc:
            rollback_errors = []
            for name, existed in reversed(changed):
                try:
                    if existed:
                        os.replace(backup / name, destination / name)
                    else:
                        (destination / name).unlink(missing_ok=True)
                except OSError as rollback:
                    rollback_errors.append(str(rollback))
            detail = '일부 프로그램 파일 복원이 필요합니다.' if rollback_errors else '변경한 프로그램 파일은 복원했습니다.'
            raise ValueError(f'업데이트 실패: {exc}\n{detail}\n백업: {backup}') from exc
    return backup
