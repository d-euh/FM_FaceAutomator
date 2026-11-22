"""Build in a fresh staging directory; never rebuild over an installed onedir."""
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from diagnostics import APP_VERSION
from release_package import create_archive, prepare_release


def build_release(root=ROOT, runner=subprocess.run):
    root = Path(root).resolve()
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Windows x64의 64비트 Python에서 빌드하세요.')
    if sys.maxsize <= 2**32:
        raise ValueError('64비트 Python이 필요합니다.')
    build = root / 'build'
    build.mkdir(exist_ok=True)
    # Each build has a different dist/work path. PyInstaller may clean only this
    # disposable path, even if the previous dist copy contains live user data.
    with tempfile.TemporaryDirectory(prefix='release-', dir=build) as temporary:
        stage = Path(temporary)
        runner([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                '--distpath', str(stage / 'dist'), '--workpath', str(stage / 'work'),
                str(root / 'packaging' / 'windows_release.spec')], cwd=root, check=True)
        bundle = stage / 'dist' / 'FMFaceAutomator'
        for executable in ('FMFaceAutomator.exe', 'FMFaceTools.exe'):
            runner([sys.executable, str(root / 'scripts' / 'verify_windows_icon.py'),
                    str(bundle / executable), str(root / 'icons' / 'ffa.ico')], cwd=root, check=True)
            runner([str(bundle / executable), '--help'], cwd=bundle, check=True, timeout=30,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        prepare_release(bundle, root / 'docs' / 'QUICK_START.ko.md', APP_VERSION)
        destination = root / 'dist' / f'FMFaceAutomator-v{APP_VERSION}-windows-x64.zip'
        create_archive(bundle, destination)
    print(f'Build output: {destination}', flush=True)
    print('Extract into a separate folder. Use update_windows.bat to update an existing installation.', flush=True)
    return destination


if __name__ == '__main__':
    try:
        build_release()
    except Exception as exc:
        print(f'Build failed: {exc}', file=sys.stderr, flush=True)
        raise SystemExit(1)
