"""Squad categories come from native relationships, never age or save-slot guesses."""
from __future__ import annotations

KINDS = {'first':'1군', 'reserve':'리저브', 'youth':'유소년'}
WAIT = '팀 구분 확인 대기'


def restricted(config):
    return set((config.get('scope_rules') or {}).get('squad_types', KINDS)) != set(KINDS)


def decision(row, rules, sides):
    allowed = set(rules.get('squad_types', KINDS))
    if allowed == set(KINDS) or row.get('manual_request'):
        return 'allow'
    if not allowed:
        return 'deny'
    evidence = row.get('squad_evidence') or {}
    unknown = False
    for side in sides:
        kind = evidence.get(side, {}).get('kind', 'unknown')
        if kind in allowed:
            return 'allow'
        if kind not in KINDS:
            unknown = True
    return 'unknown' if unknown else 'deny'


def native_role(result, expected_club):
    """Validate native membership and classify using the game's own references."""
    unknown = {'kind':'unknown'}
    if not isinstance(result,dict) or result.get('error') or result.get('cleanup_error'):
        return unknown | {'reason':'팀 조회 또는 정리 실패'}
    index, values = result.get('native_team_index'), result.get('values',{})
    if not isinstance(values,dict): return unknown | {'reason':'팀 조회 데이터 형식 확인 불가'}
    def scalar(name):
        item = values.get(name) or {}
        if not isinstance(item,dict): return None
        return None if item.get('error') or item.get('is_null') else item.get('scalar')
    club, uid, first = scalar('Club.UniqueId'), scalar('UniqueId'), scalar('IsFirstTeam')
    if type(index) is not int or index < 0 or type(club) is not int or type(uid) is not int or uid <= 0:
        return unknown | {'reason':'팀/구단 고유 ID 확인 불가'}
    if str(club) != str(expected_club):
        return unknown | {'reason':'세이브와 실행 중인 게임의 등록 구단 ID 불일치'}
    base = {'native_team_index':index, 'team_unique_id':uid, 'club_id':str(club),
            'team_type':scalar('TeamType'), 'label':(values.get('TeamTypeStringDefault') or {}).get('display_text')}
    def refers(name):
        value = values.get(name) or {}
        return isinstance(value,dict) and not value.get('error') and not value.get('is_null') and value.get('record_table') == 'Team' and type(value.get('record_index')) is int and value.get('record_index') == index
    if first is True:
        return base | {'kind':'first'}
    if first is not False:
        return base | unknown | {'reason':'1군 여부 확인 불가'}
    if refers('Club.ReservesTeam'):
        return base | {'kind':'reserve'}
    if any(refers(name) for name in ('Club.YouthTeam','Club.YouthTeam3','Club.YouthTeam4','Club.YouthTeam5',
                                    'TeamContainer.HighestLevelYouthTeam','TeamContainer.SecondHighestLevelYouthTeam')):
        return base | {'kind':'youth'}
    return base | unknown | {'reason':'검증된 리저브/유소년 참조에 없는 팀'}
