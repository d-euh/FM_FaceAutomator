from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [(str(root / 'icons' / name), 'icons') for name in ('ffa.png', 'ffa.ico')]
datas += [(str(root / 'fonts'), 'fonts')]
datas += [(str(root / 'plugins' / name), 'plugins/' + name)
          for name in ('FMFaceRefresh', 'FMFaceRefreshDiagnostics')]
binaries, hiddenimports = [], []
for package in ('fmsave', 'backports.zstd', 'PIL'):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports

a = Analysis([str(root / 'app.py'), str(root / 'release_tools.py')], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)

def entry_scripts(name):
    assert {'app', 'release_tools'} <= {entry[0] for entry in a.scripts}
    return [entry for entry in a.scripts if entry[0] not in ('app', 'release_tools') or entry[0] == name]

gui = EXE(pyz, entry_scripts('app'), [], exclude_binaries=True, name='FMFaceAutomator',
          debug=False, strip=False, upx=False, console=False, icon=str(root / 'icons' / 'ffa.ico'))
tools = EXE(pyz, entry_scripts('release_tools'), [], exclude_binaries=True, name='FMFaceTools',
            debug=False, strip=False, upx=False, console=True, icon=str(root / 'icons' / 'ffa.ico'))
bundle = COLLECT(gui, tools, a.binaries, a.datas, strip=False, upx=False, name='FMFaceAutomator')
