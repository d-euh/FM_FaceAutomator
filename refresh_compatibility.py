"""Collect offline refresh API metadata; never install or enable a game plugin."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from engine import write_atomic
from refresh_diagnostics import steam_manifest
from team_metadata import find_games, interop_folder

ROOT = Path(__file__).resolve().parent
HELPER = 'FMRefreshMetadata.exe'


def export_compatibility(game, destination, *, bundle=None, runner=subprocess.run):
    game, interop = interop_folder(game)
    manifest = steam_manifest(game)
    if manifest['name'].casefold() != 'football manager 27':
        raise ValueError('FM27 Steam 설치 폴더를 선택하세요.')
    destination = Path(destination).resolve()
    if destination.suffix.lower() != '.json' or destination.is_relative_to(game):
        raise ValueError('게임 폴더 밖의 .json 파일로 저장하세요.')
    bundle = Path(bundle) if bundle is not None else ROOT / 'tools' / 'FMRefreshMetadata'
    executable = bundle / HELPER
    fields = (bundle / 'SHA256SUMS').read_text(encoding='ascii').split()
    with executable.open('rb') as stream:
        if (len(fields) != 2 or fields[1] != HELPER or stream.read(2) != b'MZ'):
            raise ValueError('새로고침 진단 도구의 배포 정보가 올바르지 않습니다.')
        stream.seek(0)
        if hashlib.file_digest(stream, 'sha256').hexdigest() != fields[0]:
            raise ValueError('새로고침 진단 도구가 손상됐습니다. 저장소를 업데이트하세요.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.refresh-compatibility-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'refresh-compatibility.json'
        result = runner([str(executable), str(game), str(staged)], shell=False, timeout=300, check=False)
        if result.returncode:
            raise ValueError(f'새로고침 메타데이터 추출 실패 · 종료 코드 {result.returncode}')
        if staged.stat().st_size > 24 * 1024 * 1024:
            raise ValueError('진단 보고서가 24MiB를 넘습니다.')
        report = json.loads(staged.read_text(encoding='utf-8-sig'))
        if (not isinstance(report, dict) or report.get('kind') != 'fm_refresh_compatibility' or report.get('schema_version') != 1
                or report.get('tool_version') != '0.1.0' or report.get('mode') != 'metadata_only'
                or report.get('game_methods_invoked') is not False or report.get('refresh_available') is not False
                or report.get('detected_steam_build') != manifest['build']):
            raise ValueError('현재 게임의 읽기 전용 새로고침 진단 보고서가 아닙니다.')
        if steam_manifest(game) != manifest:
            raise ValueError('진단 중 Steam 설치 정보가 바뀌었습니다. 업데이트가 끝난 뒤 다시 실행하세요.')
        write_atomic(destination, staged.read_bytes())
    return destination


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox
    window = tk.Tk()
    window.withdraw()
    try:
        choices = find_games(ROOT)
        game = choices[0] if len(choices) == 1 else None
        if game is None:
            chosen = filedialog.askopenfilename(parent=window, title='업데이트된 FM27의 fm.exe 선택',
                                                filetypes=[('FM27', 'fm.exe')])
            if not chosen:
                return
            game = Path(chosen).parent
        target = export_compatibility(game, ROOT / 'diagnostics' / 'refresh-compatibility.json')
        messagebox.showinfo('새로고침 호환 진단', f'완료: {target}\n이 JSON 파일을 대화에 첨부해 주세요.\n'
                            '게임 파일 해시와 API 서명만 읽었으며 DLL 설치·게임 API 실행은 하지 않았습니다.', parent=window)
    except Exception as exc:
        messagebox.showerror('새로고침 호환 진단', str(exc), parent=window)
    finally:
        window.destroy()


if __name__ == '__main__':
    main()
