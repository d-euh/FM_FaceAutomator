"""Build-gated FM27 save team records and verified club-reference reconstruction."""
from __future__ import annotations

import re
import struct


BUILD = '27.1.0+2505117'
VERSION = 'save-squads-v1'
_U32 = struct.Struct('<I')
_FOOTER = struct.Struct('<III')
_TABLE_LEAD = re.compile(b'\x00[\x0a\x0b]')


def _require(data, position, size):
    if position < 0 or size < 0 or position + size > len(data):
        raise ValueError('Truncated team record')


def _record(data, start, ordinal):
    _require(data, start, 55)
    kind = data[start]
    if kind == 10:
        count_at = start + 34
    elif kind == 11:
        count_at = start + 88 + 10 * data[start + 54]
    else:
        raise ValueError('Unknown team record variant')
    _require(data, count_at, 2)
    roster_count = struct.unpack_from('<H', data, count_at)[0]
    tail = count_at + 2 + 4 * roster_count
    _require(data, tail, 28)
    raw_type, raw_national, raw_flag, raw_age = data[tail + 18:tail + 22]
    if raw_national != (kind == 11):
        raise ValueError('Team record variant disagrees with national marker')
    owner = _U32.unpack_from(data, tail + 24)[0]
    position = tail + 28
    names = []
    for _ in range(2):
        _require(data, position, 4)
        length = _U32.unpack_from(data, position)[0]
        position += 4
        # shortcut: names are limited to 16 KiB; revisit on a verified longer name.
        if length > 16_384:
            raise ValueError('Unrecognised team name length')
        _require(data, position, length + 1)
        name = data[position:position + length]
        position += length
        if data[position] != 0 or b'\x00' in name:
            raise ValueError('Invalid team name framing')
        names.append(name.decode('utf-8'))
        position += 1
    _require(data, position, _FOOTER.size)
    stored, uid, secondary_uid = _FOOTER.unpack_from(data, position)
    if stored != ordinal or uid in (0, 0xffffffff) or secondary_uid in (0, 0xffffffff):
        raise ValueError('Invalid team footer identity')
    return {'team_id': stored, 'unique_id': uid, 'secondary_id': secondary_uid,
            'start': start, 'footer': position, 'end': position + _FOOTER.size,
            'record_kind': kind, 'roster_count': roster_count, 'owner_index': owner,
            'raw_type': raw_type, 'raw_national': raw_national, 'raw_flag': raw_flag,
            'raw_age': raw_age, 'raw_flags': data[start + 1] if kind == 10 else None,
            'names': tuple(names)}


def _walk(data, header, count):
    position = header + 5
    rows, unique_ids = [], set()
    for ordinal in range(count):
        row = _record(data, position, ordinal)
        if row['unique_id'] in unique_ids:
            raise ValueError('Duplicate team unique ID')
        unique_ids.add(row['unique_id'])
        rows.append(row)
        position = row['end']
    return rows


def read_team_table(data, build, owners):
    """Find one complete counted table agreeing with every supplied club-team owner.

    ``owners`` maps save-local team IDs to native club indexes, supplied by the
    separately parsed club index. Index zero is valid. No slots or role guesses.
    """
    if build != BUILD:
        raise ValueError('Unverified team-table build')
    if not owners or any(type(t) is not int or type(c) is not int or t < 0 or c < 0
                         for t, c in owners.items()):
        raise ValueError('Nonempty club-team ownership evidence is required')
    minimum_count = max(owners) + 1
    found = None
    for match in _TABLE_LEAD.finditer(data):
        header = match.start() - 4
        if header < 0:
            continue
        count = _U32.unpack_from(data, header)[0]
        if not minimum_count <= count <= (len(data) - header - 5) // 86:
            continue
        try:
            # Reject unrelated byte hits before allocating the complete table.
            _record(data, header + 5, 0)
            rows = _walk(data, header, count)
            if any(rows[team]['owner_index'] != owner or rows[team]['raw_national']
                   for team, owner in owners.items()):
                continue
        except ValueError:
            continue
        if found is not None:
            raise ValueError('Ambiguous team tables')
        found = {'header': header, 'end': rows[-1]['end'], 'records': rows}
    if found is None:
        raise ValueError('No complete team table matches club ownership evidence')
    return found


def club_references(club):
    """Reconstruct club references; role labels are decided by the shared validator.

    Production callers additionally require VERIFIED_STATES. In particular,
    container/YouthTeam3 names do not establish that their targets are youth teams.
    """
    observed = {0, 1, 3, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22, 36, 37}
    for row in club['teams']:
        if (type(row.get('raw_type')) is not int or row['raw_type'] not in observed
                or row.get('raw_national') != 0 or type(row.get('raw_flags')) is not int
                or not 0 <= row['raw_flags'] <= 255):
            raise ValueError('Unverified candidate team shape')
    eligible = [row for row in club['teams']
                if row['team_id'] != club['anchor_team_id'] and not row['raw_flags'] & 1]
    def first(types):
        return next((row['team_id'] for row in eligible if row['raw_type'] in types), None)
    result = {'Club.ReservesTeam': first({1, 9, 10, 16, 21}),
              'Club.YouthTeam': first({11, 12, 18, 36, 37})}
    for index, name in enumerate(('TeamContainer.HighestLevelYouthTeam',
                                  'TeamContainer.SecondHighestLevelYouthTeam',
                                  'Club.YouthTeam3', 'Club.YouthTeam4', 'Club.YouthTeam5')):
        result[name] = eligible[index]['team_id'] if index < len(eligible) else None
    return result


# Actual native observations across calibration and separate-club cohorts.
VERIFIED_STATES = {(0, 0), (1, 0), (1, 16), (1, 21), (3, 0), (3, 1),
                   (9, 0), (9, 1), (10, 0), (10, 16), (10, 128),
                   (11, 16), (11, 21), (11, 23), (11, 128), (12, 0), (12, 16),
                   (12, 128), (13, 0), (14, 0), (14, 16), (15, 0), (15, 1),
                   (16, 0), (16, 1), (17, 0), (18, 16), (21, 128), (22, 1),
                   (36, 16), (37, 16)}


def roles_from_table(clubs, records):
    """Reuse the existing role validator with explicitly save-derived evidence."""
    from squad_types import native_role
    result = {}
    for uid, club in clubs.items():
        own = [t for t in club['teams'] if t['club_uid'] == uid and not t['is_affiliate']]
        anchors = [t['team_id'] for t in own if records[t['team_id']]['unique_id'] == club['id']]
        all_rows = [records[t['team_id']] for t in club['teams']]
        valid = len(anchors) == 1 and all((r['raw_type'], r['raw_flags']) in VERIFIED_STATES
                                       for r in all_rows)
        if valid:
            # Only up to three participating subteams were observed in native reports.
            valid = sum(r['team_id'] != anchors[0] and not r['raw_flags'] & 1 for r in all_rows) <= 3
        refs = club_references({'anchor_team_id': anchors[0], 'teams': all_rows}) if valid else None
        for team in own:
            index = team['team_id']
            row = records[index]
            evidence = {'kind': 'unknown', 'reason': '미검증 세이브 팀 유형·상태 또는 구단 참조'}
            first = (len(anchors) == 1 and index == anchors[0] and row['raw_type'] == 0
                     and (row['raw_type'], row['raw_flags']) in VERIFIED_STATES)
            if first or refs is not None:
                values = {key: {'scalar': value} for key, value in {
                    'UniqueId': row['unique_id'], 'Club.UniqueId': club['id'],
                    'IsFirstTeam': row['raw_type'] == 0, 'TeamType': row['raw_type']}.items()}
                values.update({key: {'record_table': 'Team', 'record_index': target,
                                    'is_null': target is None} for key, target in (refs or {}).items()})
                # This shape only shares validation; it is not a native query result.
                evidence = native_role({'native_team_index': index, 'values': values}, str(club['id']))
            result[str(index)] = evidence | {'source': 'save', 'build': BUILD,
                'registered_team_id': index, 'club_id': str(club['id']), 'team_unique_id': row['unique_id']}
    return result


def read_roles(save, clubs):
    """Decode once per save; no game process or native bridge is accessed."""
    if save.info.build != BUILD:
        return {}, {'mode': 'save', 'version': VERSION, 'build': save.info.build,
                    'error': '세이브 팀 구분 미지원 빌드: ' + str(save.info.build)}
    status = {'mode': 'save', 'version': VERSION, 'build': BUILD}
    try:
        with save._context.section('game_db') as data:
            index = save._context.club_index()
            native_by_uid = {uid: idx for idx, uid in index.uid_by_club_index.items()}
            owners = {tid: native_by_uid[uid] for tid, (uid, _) in index.team_to_club.items()}
            table = read_team_table(data, BUILD, owners)
        catalog = {uid: {'id': c.unique_id, 'teams': [
            {'team_id': t.team_id, 'club_uid': t.club_uid, 'is_affiliate': t.is_affiliate}
            for t in c.teams]} for uid, c in clubs.items() if c.unique_id is not None}
        roles = roles_from_table(catalog, table['records'])
        status['unknown_teams'] = sum(r['kind'] == 'unknown' for r in roles.values())
        return roles, status
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        # A supported-build decode failure must not silently fall back to live queries.
        return {}, status | {'error': '세이브 팀 구분 해석 보류: ' + str(exc)[:240]}
