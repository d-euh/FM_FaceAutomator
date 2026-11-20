"""Read-only, small squad-assignment reports from local FM saves; never call AI."""
from __future__ import annotations

import argparse
import json
from importlib.metadata import version
from pathlib import Path
import shutil
import tempfile

from engine import COMPATIBLE_FM27_BUILDS, check_save_reader, write_atomic


DEFAULT_PLAYER_IDS = ('2000256110', '2000382120')
PLAYER_FIELDS = ('name', 'team_id', 'team_slot', 'club_uid', 'club_name',
                 'team_club_uid', 'team_club_name', 'on_loan')


def coded(value):
    if value is None:
        return None
    return {'raw': getattr(value, 'raw', None), 'label': getattr(value, 'label_text', str(value))}


def extract(save, player_ids):
    """Expose the reader's raw team/slot evidence, without assigning squad meanings."""
    clubs = {club.uid: club for club in save.clubs()}
    found, related = {}, set()
    for player in save.players():
        pid = str(player.unique_id)
        if pid not in player_ids:
            continue
        item = {'id': pid, **{key: getattr(player, key, None) for key in PLAYER_FIELDS}}
        item['club_id'] = getattr(clubs.get(item['club_uid']), 'unique_id', None)
        contract = getattr(player, 'contract', None)
        item['contract'] = {key: getattr(contract, key, None) for key in ('club_uid', 'team_id', 'club_name')}
        item['contract'].update(kind=coded(getattr(contract, 'kind', None)),
                                squad_status=coded(getattr(contract, 'squad_status', None)))
        found[pid] = item
        related.update(uid for uid in (item['club_uid'], item['team_club_uid']) if uid is not None)
        if len(found) == len(player_ids):
            break
    catalog = []
    for uid in sorted(related):
        club = clubs.get(uid)
        if club is not None:
            catalog.append({'uid': uid, 'id': getattr(club, 'unique_id', None), 'name': club.name,
                            'parent_club_uid': getattr(club, 'parent_club_uid', None),
                            'teams': [{key: getattr(team, key, None) for key in ('team_id','slot','club_uid','is_affiliate')}
                                      for team in getattr(club, 'teams', ())]})
    return {'game': save.info.game, 'build': save.info.build, 'known_build': save.info.known_build,
            'game_date': str(save.info.game_date or ''), 'players': list(found.values()),
            'missing_player_ids': [pid for pid in player_ids if pid not in found], 'clubs': catalog}


def stamp(path):
    value = path.stat()
    return value.st_size, value.st_mtime_ns, value.st_ino


def read_snapshot(path, player_ids, opener=None):
    path = Path(path).resolve()
    before = stamp(path)
    with tempfile.TemporaryDirectory(prefix='fm-squad-check-') as folder:
        copied = Path(folder)/'snapshot.fm'
        shutil.copyfile(path, copied)
        if stamp(path) != before:
            raise ValueError('세이브가 저장 중입니다. 게임 저장이 끝난 뒤 다시 실행하세요.')
        if opener is None:
            import fmsave
            opener = fmsave.open
        with opener(copied, strict=True) as save:
            if save.info.game != 'FM27' or (not save.info.known_build and save.info.build not in COMPATIBLE_FM27_BUILDS):
                raise ValueError(f'지원하지 않는 세이브 빌드: {save.info.game} {save.info.build}')
            result = extract(save, player_ids)
        if stamp(path) != before:
            raise ValueError('분석 도중 세이브가 변경됐습니다. 저장을 멈춘 뒤 다시 실행하세요.')
    return result | {'file':path.name, 'size_bytes':before[0]}


def compare(snapshots, player_ids):
    result = []
    for pid in player_ids:
        rows = []
        for snapshot in snapshots:
            player = next((row for row in snapshot.get('players', []) if row['id'] == pid), None)
            if player:
                rows.append({'file':snapshot['file'], **player})
        fields = ('team_id','team_slot','club_uid','club_id','team_club_uid','on_loan','contract')
        changed = [key for key in fields if len({json.dumps(row.get(key), sort_keys=True, ensure_ascii=False) for row in rows}) > 1]
        result.append({'player_id':pid, 'complete':len(rows)==len(snapshots) and len(rows)>=2,
                       'changed_fields':changed, 'values_by_save':rows})
    return result


def initial_directory():
    try:
        config = json.loads((Path(__file__).resolve().parent/'config.json').read_text(encoding='utf-8-sig'))
        source = Path(config.get('source', ''))
        if source.is_file():
            return str(source.parent)
    except (OSError, ValueError):
        pass
    return str(Path.home()/'Documents')


def main():
    parser = argparse.ArgumentParser(description='Compare registered teams in FM27 saves without AI calls or save edits.')
    parser.add_argument('saves', nargs='*', type=Path)
    parser.add_argument('--player-ids', nargs='+', default=DEFAULT_PLAYER_IDS)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ids = tuple(dict.fromkeys(str(value) for value in args.player_ids))
    if not ids or any(not value.isdigit() for value in ids):
        parser.error('Player IDs must be numbers.')
    saves, output = args.saves, args.output
    root = None
    try:
        if not saves or output is None:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            if not saves:
                saves = [Path(path) for path in filedialog.askopenfilenames(parent=root, title='팀검증 1군·U21·U18 세이브를 함께 선택하세요',
                            initialdir=initial_directory(), filetypes=[('FM 세이브','*.fm'),('모든 파일','*')])]
                if not saves:
                    return 0
            if output is None:
                chosen = filedialog.asksaveasfilename(parent=root,title='작은 팀 구분 진단 JSON 저장', initialfile='squad-diagnostic.json',
                            initialdir=str(Path(__file__).resolve().parent),defaultextension='.json',filetypes=[('JSON','*.json')])
                if not chosen:
                    return 0
                output = Path(chosen)
        paths = [path.resolve() for path in saves]
        if len(paths) < 2 or len(set(paths)) != len(paths):
            raise ValueError('서로 다른 세이브를 2개 이상 선택하세요.')
        if output.resolve() in paths or output.suffix.lower() != '.json':
            raise ValueError('세이브와 다른 경로의 .json 파일로 저장하세요.')
        check_save_reader()
        report = {'kind':'fm_squad_assignment_diagnostic', 'schema_version':1, 'reader_version':version('fmsave'),
                  'player_ids':ids, 'snapshots':[], 'note':'Team slots are raw reader values; first-team/U21/U18 meanings are not automatically inferred.'}
        for index, path in enumerate(paths, 1):
            print(f'[{index}/{len(paths)}] {path.name} 읽는 중...', flush=True)
            try:
                snapshot = read_snapshot(path, ids)
                for row in snapshot['players']:
                    print(f"  {row['id']} {row['name']} | team_id={row['team_id']} | slot={row['team_slot']}", flush=True)
            except Exception as exc:
                snapshot = {'file':path.name, 'error':str(exc)}
                print('  읽기 실패: ' + str(exc), flush=True)
            report['snapshots'].append(snapshot)
        report['comparison'] = compare(report['snapshots'], ids)
        write_atomic(output, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
        print('\n저장 완료: ' + str(output.resolve()), flush=True)
        print('이 JSON 파일을 대화에 첨부하세요. 세이브·페이스팩은 변경하지 않았으며 AI를 호출하지 않았습니다.', flush=True)
        return 1 if any('error' in item for item in report['snapshots']) else 0
    except Exception as exc:
        print('진단 오류: ' + str(exc), flush=True)
        return 1
    finally:
        if root is not None:
            root.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
