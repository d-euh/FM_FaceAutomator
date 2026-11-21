"""Export static team/squad API metadata without loading the game or any plugin."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from refresh_diagnostics import find_steam_games, steam_manifest


ROOT = Path(__file__).resolve().parent
HELPER = 'FMTeamMetadata.exe'
MAX_REPORT = 24 * 1024 * 1024


def find_games(root=ROOT):
    choices = []
    try:
        saved = json.loads((Path(root)/'.refresh-diagnostics.json').read_text(encoding='utf-8-sig'))
        game = Path(saved['game'])
        if (game/'fm.exe').is_file():
            choices.append(game.resolve())
    except (OSError, ValueError, KeyError, TypeError):
        pass
    for game in find_steam_games():
        if game.resolve() not in choices:
            choices.append(game.resolve())
    return choices


def interop_folder(game):
    game = Path(game).resolve()
    if game.is_file():
        game = game.parent
    if not (game/'fm.exe').is_file() or not (game/'GameAssembly.dll').is_file():
        raise ValueError('FM27 설치 폴더의 fm.exe를 선택하세요.')
    interop = game/'BepInEx'/'interop'
    if not interop.is_dir() or not any(interop.glob('*.dll')):
        raise ValueError('BepInEx interop가 없습니다. 기존 BepInEx 설치 상태에서 FM27을 한 번 실행한 뒤 다시 시도하세요.')
    return game, interop


def helper_path(bundle):
    bundle = Path(bundle)
    executable = bundle/HELPER
    parts = (bundle/'SHA256SUMS').read_text(encoding='ascii').split()
    if len(parts) != 2 or parts[1] != HELPER or len(parts[0]) != 64:
        raise ValueError('팀 진단 도구의 배포 정보가 올바르지 않습니다. git pull로 업데이트하세요.')
    with executable.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('팀 진단 실행 파일이 손상됐습니다.')
        stream.seek(0)
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != parts[0]:
        raise ValueError('팀 진단 실행 파일의 해시가 다릅니다. git pull로 다시 받아 주세요.')
    return executable


def export_metadata(interop, destination, build=None, bundle=None, runner=subprocess.run):
    interop, destination = Path(interop).resolve(), Path(destination).resolve()
    if destination.suffix.lower() != '.json' or destination.is_relative_to(interop):
        raise ValueError('게임 DLL 폴더 밖의 .json 파일로 저장하세요.')
    executable = helper_path(bundle or ROOT/'tools'/'FMTeamMetadata')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never report an old output as a fresh export, or overwrite it on failure.
    with tempfile.TemporaryDirectory(prefix='.team-metadata-',dir=destination.parent) as temporary:
        staged = Path(temporary)/'team-metadata.json'
        command = [str(executable),str(interop),str(staged)]
        if build:
            command.append(str(build))
        result = runner(command, shell=False, timeout=300, check=False)
        if result.returncode:
            raise ValueError(f'팀 메타데이터 추출 실패 · 종료 코드 {result.returncode}. 콘솔의 오류를 확인하세요.')
        if staged.stat().st_size > MAX_REPORT:
            raise ValueError('보고서가 예상 크기를 넘었습니다. 파일 대신 콘솔의 오류를 알려주세요.')
        report = json.loads(staged.read_text(encoding='utf-8-sig'))
        if (not isinstance(report,dict) or report.get('kind') != 'fm_team_metadata' or report.get('schema_version') != 1
                or report.get('mode') != 'metadata_only' or report.get('game_methods_invoked') is not False):
            raise ValueError('읽기 전용 팀 메타데이터 보고서가 아닙니다.')
        if not report.get('scanned_assemblies'):
            raise ValueError('읽을 수 있는 FM/SI interop DLL이 없습니다. BepInEx interop 폴더를 확인하세요.')
        os.replace(staged,destination)
    return destination, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'diagnostics'/'team-metadata.json')
    args = parser.parse_args()
    window = None
    try:
        if os.name != 'nt':
            raise ValueError('Windows PC에서 export_team_metadata.bat를 실행하세요.')
        game = args.game
        if game is None:
            choices = find_games()
            if len(choices) == 1:
                game = choices[0]
            else:
                import tkinter as tk
                from tkinter import filedialog
                window = tk.Tk()
                window.withdraw()
                chosen = filedialog.askopenfilename(parent=window,title='FM27 설치 폴더의 fm.exe 선택',filetypes=[('FM27','fm.exe')])
                if not chosen:
                    return 0
                game = Path(chosen).parent
        game, interop = interop_folder(game)
        try:
            build = steam_manifest(game)['build']
        except (OSError,ValueError):
            build = None
        print('팀·스쿼드 형식 정보를 읽습니다. 게임 실행/재시작·플러그인 재설치는 필요 없습니다.',flush=True)
        target, report = export_metadata(interop,args.output,build)
        print('\n저장 완료: '+str(target),flush=True)
        print(f"읽은 DLL: {report['scanned_assemblies']} · 읽기 오류: {len(report.get('errors',[]))}",flush=True)
        print('team-metadata.json 파일만 대화에 첨부하세요. 게임 DLL·세이브·인증 정보는 보고서에 포함하지 않았습니다.',flush=True)
        try:
            os.startfile(str(target.parent))
        except OSError:
            pass  # Explorer failure does not undo a validated report.
        return 0
    except Exception as exc:
        print('팀 진단 오류: '+str(exc),flush=True)
        return 1
    finally:
        if window is not None:
            window.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
