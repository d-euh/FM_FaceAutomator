"""Install/export a separate read-only team schema diagnostic; never call Codex."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from refresh_diagnostics import (INSTALL_RECORD, ROOT, EXPECTED_BUILD, game_process_running,
                                 install_component, validate_game)
from team_metadata import find_games

TOOL_VERSION = '0.4.1'
FOLDER = 'FMTeamBindings'
DLL = 'FMTeamBindings.dll'
MAX_REPORT = 8 * 1024 * 1024


def install(game, bundle=None):
    if game_process_running():
        raise ValueError('FM27을 완전히 종료한 뒤 팀 진단 플러그인을 설치하세요.')
    return install_component(game, bundle, DLL, FOLDER)


def export_report(game, destination):
    game = validate_game(game)
    source = game/'BepInEx'/'diagnostics'/FOLDER/'team-bindings.json'
    installed = game/'BepInEx'/'plugins'/FOLDER/DLL
    if not installed.is_file():
        raise ValueError('install_team_bindings.bat로 팀 진단 플러그인을 먼저 설치하세요.')
    if not source.is_file() or source.stat().st_mtime_ns < installed.stat().st_mtime_ns:
        raise ValueError('새 팀 진단 결과가 아직 없습니다. 설치 후 FM27을 실행하고 메인 화면에서 60초 정도 기다린 뒤 다시 실행하세요.')
    before = source.stat()
    if before.st_size > MAX_REPORT:
        raise ValueError('팀 진단 보고서가 예상 크기를 넘었습니다.')
    data = source.read_bytes()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(data) > MAX_REPORT:
        raise ValueError('팀 진단 보고서가 저장 중입니다. 잠시 후 다시 실행하세요.')
    report = json.loads(data.decode('utf-8-sig'))
    if not isinstance(report, dict) or report.get('kind') != 'fm_team_bindings' or report.get('schema_version') != 1:
        raise ValueError('지원하는 팀 진단 보고서가 아닙니다.')
    if report.get('tool_version') != TOOL_VERSION:
        raise ValueError('기존 팀 진단 보고서입니다. 업데이트 후 install_team_bindings.bat로 재설치하고 FM27을 다시 실행하세요.')
    observed = report.get('observations')
    if (report.get('mode') != 'runtime_team_reader_service'
            or report.get('detected_steam_build') != EXPECTED_BUILD
            or not isinstance(report.get('game_data_query_attempted'),bool)
            or report.get('gameplay_state_modified') is not False or report.get('save_files_modified') is not False
            or not isinstance(report.get('probe'),dict)
            or not all(isinstance(report.get(k), list) for k in ('schemas', 'types', 'errors'))
            or not isinstance(observed, dict) or observed.get('observed_existing_ui_values_only') is not True
            or not (isinstance(observed.get('values'), list) or observed.get('values') is None)):
        raise ValueError('지원하는 읽기 전용 팀 속성 보고서가 아닙니다.')
    if report.get('state') in ('waiting_for_main_thread', 'reading_schema'):
        raise ValueError('아직 팀 속성을 읽고 있습니다. FM27 메인 화면에서 60초 정도 기다린 뒤 다시 실행하세요.')
    if report.get('state') not in ('complete', 'complete_with_errors', 'unavailable'):
        raise ValueError('팀 진단 보고서 상태를 확인할 수 없습니다.')
    destination = Path(destination).resolve()
    if destination.suffix.lower() != '.json' or destination.is_relative_to(game):
        raise ValueError('게임 설치 폴더 밖의 .json 파일로 저장하세요.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.team-bindings-')
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--game', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostics'/'team-bindings.json')
    args = parser.parse_args()
    window = None
    try:
        if os.name != 'nt':
            raise ValueError('이 도구는 Windows PC용입니다.')
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
                chosen = filedialog.askopenfilename(parent=window, title='FM27 설치 폴더의 fm.exe 선택', filetypes=[('FM27', 'fm.exe')])
                if not chosen:
                    return 0
                game = Path(chosen).parent
        if args.export:
            target = export_report(game, args.output)
            print('저장 완료: '+str(target), flush=True)
            print('team-bindings.json 파일만 대화에 첨부해 주세요. 선수 이동·합성은 필요 없습니다.', flush=True)
            report = json.loads(target.read_text(encoding='utf-8-sig'))
            rows = report.get('observations', {}).get('values') or []
            print(f'관찰한 팀 관련 값: {len(rows)}개', flush=True)
            probe = report.get('probe',{})
            service = report.get('service') or {}
            print(f"팀 조회 연결: {service.get('reason','확인 불가')} · 처리 {service.get('completed',0)}건", flush=True)
            if not rows:
                print('값이 수집되지 않은 결과도 원인 확인에 필요하므로 그대로 첨부해 주세요.', flush=True)
            try:
                os.startfile(str(target.parent))
            except OSError:
                pass
        else:
            game = Path(game).resolve()
            target = install(game)
            INSTALL_RECORD.write_text(json.dumps({'game':str(game)}, ensure_ascii=False), encoding='utf-8')
            print('팀 구분 조회 플러그인 설치 완료: '+str(target), flush=True)
            print('1. FM27을 실행하고 앱에 연결한 세이브를 불러오세요.\n'
                  '2. 앱의 이적 감지 범위에서 포함할 선수단(1군/리저브/유소년)을 선택하고 저장하세요.\n'
                  '3. 기존 테스트처럼 이적 후 저장하면 생성 전에 선수단을 자동 조회합니다.\n'
                  '문제가 있으면 export_team_bindings.bat의 team-bindings.json을 첨부하세요.\n'
                  '선수 이동, 페이스온 삭제·합성, 새로고침 테스트는 필요 없습니다. 기존 새로고침 플러그인은 변경하지 않았습니다.', flush=True)
        return 0
    except Exception as exc:
        print('팀 속성 진단 오류: '+str(exc), flush=True)
        return 1
    finally:
        if window is not None:
            window.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
