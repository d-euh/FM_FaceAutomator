"""Research-only FM27 team-table reader; raw fields never assign squad roles.

Not imported by the app. Observed on controlled saves from one career/build;
complete framing and ownership checks do not establish field semantics.
"""
from __future__ import annotations

import re
import struct


BUILD = '27.1.0+2505117'
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
        # shortcut: research names are limited to 16 KiB; revisit on a verified longer name.
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
            'raw_age': raw_age, 'names': tuple(names)}


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
