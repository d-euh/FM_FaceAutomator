"""One-time save/native comparison using the existing read-only team service."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from engine import check_save_reader, write_atomic
from scripts.probe_save_teams import BUILD, candidate_references, read_team_table
from squad_diagnostics import initial_directory, stamp
from team_reader import GameWait, PROFILE, TeamReader


ROOT = Path(__file__).resolve().parents[1]
# Include the clubs already observed in-game; these IDs select samples, never roles.
CONTROL_CLUBS = {680, 1708}
REFERENCES = ('Club.ReservesTeam', 'Club.YouthTeam', 'Club.YouthTeam3',
              'Club.YouthTeam4', 'Club.YouthTeam5', 'TeamContainer.HighestLevelYouthTeam',
              'TeamContainer.SecondHighestLevelYouthTeam')


def samples(clubs, records, managed, holdout=False):
    """Cover observed raw-type/name-flag/control-link combinations, without labelling them."""
    preferred = CONTROL_CLUBS | set(managed)
    selected = {uid for uid, c in clubs.items() if c['id'] in preferred}
    seen = set()
    for uid, club in clubs.items():
        for team in club['teams']:
            row = records[team['team_id']]
            key = (row['raw_type'], row['raw_flag'], team['is_affiliate'])
            if key not in seen:
                selected.add(uid)
                seen.add(key)
    if holdout:
        baseline = selected
        baseline_teams = {t['team_id'] for uid in baseline for t in clubs[uid]['teams']}
        selected = {uid for uid, c in clubs.items() if c['id'] in preferred}
        seen = set()
        for uid, club in clubs.items():
            if uid in baseline or any(t['team_id'] in baseline_teams for t in club['teams']):
                continue
            for team in club['teams']:
                row = records[team['team_id']]
                key = (row['raw_type'], row['raw_flag'], team['is_affiliate'])
                if key not in seen:
                    selected.add(uid)
                    seen.add(key)
    result = []
    for uid, club in clubs.items():
        if uid not in selected:
            continue
        anchors = [t['team_id'] for t in club['teams']
                   if t['club_uid'] == uid and records[t['team_id']]['unique_id'] == club['id']]
        if len(anchors) != 1:
            raise ValueError('구단의 고유 ID와 일치하는 기준 팀을 확정할 수 없습니다.')
        teams = []
        for team in club['teams']:
            row = records[team['team_id']]
            owner = clubs[team['club_uid']]['id']
            teams.append({**row, 'owner_club_id': owner, 'is_affiliate': team['is_affiliate']})
        result.append({'club_id': club['id'], 'name': club['name'],
                       'anchor_team_id': anchors[0], 'teams': teams})
    result.sort(key=lambda c: c['club_id'] not in preferred)
    return result


def read_save(source, holdout=False):
    import fmsave
    check_save_reader()
    source = Path(source).resolve()
    before = stamp(source)
    with tempfile.TemporaryDirectory(prefix='fm-team-role-check-') as folder:
        copy = Path(folder) / 'snapshot.fm'
        shutil.copyfile(source, copy)
        if stamp(source) != before:
            raise ValueError('세이브 저장이 끝난 뒤 다시 실행하세요.')
        with fmsave.open(copy, strict=True) as save:
            if save.info.game != 'FM27' or save.info.build != BUILD:
                raise ValueError('검증 대상 FM27 세이브 빌드가 아닙니다.')
            with save._context.section('game_db') as data:
                club_rows = save.clubs()
                index = save._context.club_index()
                native_by_uid = {uid: idx for idx, uid in index.uid_by_club_index.items()}
                owners = {tid: native_by_uid[uid] for tid, (uid, _) in index.team_to_club.items()}
                table = read_team_table(data, save.info.build, owners)
                clubs = {c.uid: {'id': c.unique_id, 'name': c.name,
                         'teams': [{'team_id': t.team_id, 'club_uid': t.club_uid,
                                    'is_affiliate': t.is_affiliate} for t in c.teams]}
                         for c in club_rows}
                managed = [clubs[m.club_uid]['id'] for m in save.managed_clubs()
                           if m.club_uid in clubs and type(clubs[m.club_uid]['id']) is int]
                if not managed:
                    raise ValueError('담당 구단을 확인할 수 있는 세이브가 필요합니다.')
                plan = samples(clubs, table['records'], managed, holdout)
                build, date = save.info.build, str(save.info.game_date or '')
        with copy.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if stamp(source) != before:
            raise ValueError('분석 도중 세이브가 변경됐습니다. 저장이 끝난 뒤 다시 실행하세요.')
    return {'file': source.name, 'sha256': digest, 'build': build, 'game_date': date,
            'managed_club_ids': managed, 'sample_mode': 'holdout' if holdout else 'calibration',
            'samples': plan}


def scalar(row, key):
    values = row.get('values')
    item = values.get(key) if isinstance(values, dict) else None
    if not isinstance(item, dict):
        return None
    return None if item.get('error') or item.get('is_null') else item.get('scalar')


def compare_native(plan, reader):
    targets = {t['team_id']: t for c in plan['samples'] for t in c['teams']}
    if not plan['managed_club_ids'] or not 0 < len(targets) <= 256:
        raise ValueError('담당 구단 확인과 최대 256개 팀의 검증 범위가 필요합니다.')
    rows = reader.resolve(list(targets), plan['managed_club_ids'], plan['sha256'])
    for tid, saved in targets.items():
        row = rows.get(tid, {})
        if (type(row.get('native_team_index')) is not int or row['native_team_index'] != tid
                or row.get('error') or row.get('cleanup_error')
                or type(scalar(row, 'UniqueId')) is not int
                or scalar(row, 'UniqueId') != saved['unique_id']
                or type(scalar(row, 'Club.UniqueId')) is not int
                or scalar(row, 'Club.UniqueId') != saved['owner_club_id']):
            raise ValueError(f'팀 {tid}: 세이브와 게임의 팀 ID/구단이 다르거나 조회가 실패했습니다.')
    compared = []
    for club in plan['samples']:
        anchor = rows[club['anchor_team_id']]
        if scalar(anchor, 'IsFirstTeam') is not True:
            raise ValueError('구단 기준 팀의 실제 IsFirstTeam을 확인하지 못했습니다.')
        teams = []
        for saved in club['teams']:
            matches = []
            for key in REFERENCES:
                ref = anchor.get('values', {}).get(key) or {}
                if (isinstance(ref, dict) and not ref.get('error') and not ref.get('is_null') and ref.get('record_table') == 'Team'
                        and type(ref.get('record_index')) is int and ref['record_index'] == saved['team_id']):
                    matches.append(key)
            native = rows[saved['team_id']]
            raw_type = scalar(native, 'TeamType')
            teams.append({'saved': saved, 'native': native, 'parent_reference_matches': matches,
                          'type_matches': type(raw_type) is int and raw_type == saved['raw_type']})
        comparison = {**club, 'teams': teams}
        try:
            predicted = candidate_references(club)
            comparison['candidate_references'] = predicted
            comparison['reference_comparison'] = {}
            for key, expected in predicted.items():
                ref = anchor.get('values', {}).get(key)
                valid = isinstance(ref, dict) and not ref.get('error') and (
                    (ref.get('is_null') is True and ref.get('record_index') is None)
                    or (not ref.get('is_null') and ref.get('record_table') == 'Team'
                    and type(ref.get('record_index')) is int))
                actual = ref.get('record_index') if valid and not ref.get('is_null') else None
                comparison['reference_comparison'][key] = {
                    'predicted': expected, 'native': actual, 'matches': bool(valid and actual == expected)}
        except ValueError as exc:
            comparison['candidate_error'] = str(exc)
        compared.append(comparison)
    return {'context': reader.last_context, 'clubs': compared}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('save', nargs='?', type=Path)
    parser.add_argument('--holdout', action='store_true', help='Compare new representative clubs, retaining control clubs.')
    parser.add_argument('--output', type=Path, default=ROOT / 'diagnostics' / 'save-team-roles.json')
    args = parser.parse_args()
    window = None
    try:
        if os.name != 'nt':
            raise ValueError('기존 팀 조회 DLL이 실행 중인 Windows FM27에서 사용하세요.')
        if args.save is None:
            import tkinter as tk
            from tkinter import filedialog
            window = tk.Tk()
            window.withdraw()
            chosen = filedialog.askopenfilename(parent=window, title='게임에 불러온 팀 검증 세이브 선택',
                         initialdir=initial_directory(), filetypes=[('FM 세이브', '*.fm')])
            if not chosen:
                return 0
            args.save = Path(chosen)
        if args.save.suffix.lower() != '.fm' or args.output.suffix.lower() != '.json':
            raise ValueError('입력은 .fm, 출력은 별도의 .json 파일이어야 합니다.')
        print('세이브 복사본의 팀 구조를 읽는 중...', flush=True)
        plan = read_save(args.save, args.holdout)
        count = len({t['team_id'] for c in plan['samples'] for t in c['teams']})
        print(f"{len(plan['samples'])}개 구단 · {count}개 팀 조회 중 · 게임 시간을 진행하지 마세요.", flush=True)
        report = {'kind': 'fm_save_native_team_comparison', 'schema_version': 1, 'profile': PROFILE,
                  'loaded_save_file_verified': False, 'source': plan, 'native': None,
                  'note': 'Team identities and managed club are checked; the loaded save filename is not exposed by the service.'}
        reader = TeamReader()
        try:
            started, next_notice = reader.clock(), 0
            while True:
                try:
                    report['native'] = compare_native(plan, reader)
                    break
                except GameWait:
                    now = reader.clock()
                    if now - started >= 120:
                        raise ValueError('게임 연결 대기 시간이 초과됐습니다. FM27 화면을 확인하고 다시 실행하세요.')
                    if now >= next_notice:
                        print('게임 연결 대기 중 · 도구를 유지하고 FM27 화면을 확인하세요.', flush=True)
                        next_notice = now + 5
                    reader.sleep(min(2, 120 - (now - started)))
        except Exception as exc:
            report['error'] = str(exc)
            # Keep failed/partial observations for diagnosis, never as verified comparisons.
            report['unverified_native_results'] = [
                {'session': key[0], 'epoch': key[1], 'snapshot': key[2], 'result': row}
                for key, row in reader.cache.items()]
        write_atomic(args.output, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))
        print('진단 저장: ' + str(args.output.resolve()), flush=True)
        if report.get('error'):
            raise ValueError(report['error'])
        print('완료 · 이 JSON 파일을 대화에 첨부하세요. AI·이미지 저장은 실행하지 않았습니다.', flush=True)
        return 0
    except Exception as exc:
        print('검증 중단: ' + str(exc), flush=True)
        return 1
    finally:
        if window is not None:
            window.destroy()


if __name__ == '__main__':
    raise SystemExit(main())
