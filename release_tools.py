"""Console companion shipped beside the GUI; no Python installation required."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from refresh_diagnostics import find_steam_games, game_process_running, install_component, validate_game
from release_package import apply_update


def resource_root():
    return Path(__file__).resolve().parent


def install_plugins(game, *, team=True, refresh=True, bundle=None):
    """Use existing installers and gates; do not change any native API or DLL."""
    if game_process_running():
        raise ValueError('FM27을 완전히 종료한 뒤 설치하세요.')
    game = validate_game(game)
    bundle = Path(bundle) if bundle is not None else resource_root() / 'plugins'
    components = []
    if team:
        components.append(('FMTeamBindings', 'FMTeamBindings.dll'))
    if refresh:
        components.append(('FMFaceRefresh', 'FMFaceRefresh.dll'))
    # Verify every supplied DLL before installing the first one.
    for folder, filename in components:
        data = (bundle / folder / filename).read_bytes()
        fields = (bundle / folder / 'SHA256SUMS').read_text(encoding='ascii').split()
        if len(fields) != 2 or fields[1] != filename or hashlib.sha256(data).hexdigest() != fields[0]:
            raise ValueError(f'DLL 배포 파일이 손상됐습니다: {filename}')
    return [install_component(game, bundle / folder, filename, folder) for folder, filename in components]


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ('install-all', 'install-team', 'install-refresh', 'update', 'export-diagnostics',
                 'export-team', 'export-metadata'):
        modes.add_argument('--' + name, action='store_true')
    parser.add_argument('--game', type=Path)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    window = tk.Tk()
    window.withdraw()
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else resource_root()
    try:
        if sys.platform != 'win32':
            raise ValueError('이 배포 도구는 Windows용입니다.')
        if args.update:
            chosen = args.destination or filedialog.askdirectory(parent=window, title='기존 FMFaceAutomator.exe가 있는 폴더 선택')
            if not chosen:
                return 0
            backup = apply_update(root, chosen)
            text = f'업데이트 완료: {chosen}\n설정·작업 기록·페이스팩은 유지했습니다.\n프로그램 파일 백업: {backup}'
        elif args.export_diagnostics:
            from diagnostics import export_bundle
            chosen = args.destination or filedialog.asksaveasfilename(parent=window, title='문제 진단 저장',
                         initialfile='live-refresh-report.json', defaultextension='.json', filetypes=[('JSON', '*.json')])
            if not chosen:
                return 0
            target = export_bundle(chosen, config_path=root / 'config.json', root=root)
            text = f'진단 저장 완료: {target}\n설정 경로가 포함되며 이미지·지시·인증 정보는 포함하지 않습니다.'
        else:
            from team_metadata import find_games
            game = args.game
            if game is None:
                choices = find_games(root)
                game = choices[0] if len(choices) == 1 else None
            if game is None:
                chosen = filedialog.askopenfilename(parent=window, title='FM27 설치 폴더의 fm.exe 선택', filetypes=[('FM27', 'fm.exe')])
                if not chosen:
                    return 0
                game = Path(chosen).parent
            if args.export_team or args.export_metadata:
                filename = 'team-bindings.json' if args.export_team else 'team-metadata.json'
                chosen = args.destination or filedialog.asksaveasfilename(parent=window, title='팀 진단 저장',
                             initialfile=filename, defaultextension='.json', filetypes=[('JSON', '*.json')])
                if not chosen:
                    return 0
                if args.export_team:
                    from team_bindings import export_report
                    target = export_report(game, chosen)
                else:
                    from team_metadata import interop_folder, export_metadata
                    from refresh_diagnostics import steam_manifest
                    game, interop = interop_folder(validate_game(game))
                    target, _ = export_metadata(interop, chosen, build=steam_manifest(game)['build'])
                text = f'팀 진단 저장 완료: {target}\n이 JSON 파일을 첨부해 주세요.'
            else:
                installed = install_plugins(game, team=not args.install_refresh, refresh=not args.install_team)
                from engine import write_atomic
                write_atomic(root / '.refresh-diagnostics.json', json.dumps({'game': str(Path(game).resolve())}).encode('utf-8'))
                text = ('게임 연동 DLL 설치 완료\n' + '\n'.join(map(str, installed)) +
                        '\n\nFM27을 실행하고 연결할 세이브를 불러오세요.\n'
                        '앱의 홈 → 페이스온 새로고침으로 실제 반영을 확인하세요.\n'
                        '자동 반영은 같은 버튼 오른쪽의 생성 후 자동 새로고침을 켜고 설정을 저장하세요.')
        print(text, flush=True)
        messagebox.showinfo('FM Face Automator', text, parent=window)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        messagebox.showerror('FM Face Automator', str(exc), parent=window)
        return 1
    finally:
        window.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
