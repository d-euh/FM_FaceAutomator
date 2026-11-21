"""Transfer-event scope: match arrivals against destination, departures against source."""
from __future__ import annotations

import copy

import squad_types
from transfer_types import TRANSFER_TYPES, exclusion_reason


PRESETS = {
    "managed": "내가 맡은 구단만", "all": "모든 이적", "top5": "5대 리그만",
    "premier_league": "프리미어리그만", "big6": "프리미어리그 빅6만",
    "serie_a": "세리에 A만", "la_liga": "라리가만", "ligue_1": "리그앙만",
    "bundesliga": "분데스리가만", "custom": "직접 설정",
}
DIRECTIONS = {"both": "방출·영입 모두", "incoming": "영입된 선수만", "outgoing": "방출된 선수만"}
# Stable editor database IDs, not fmsave's save-local competition IDs.
# Sources: sortitoutsi.net/football-manager-data-update/competition/{id}
LEAGUES = {"premier_league": "11", "serie_a": "32", "la_liga": "67", "ligue_1": "16", "bundesliga": "22"}
BIG6 = {"602", "630", "676", "679", "680", "728"}
DEFAULT_SCOPE = {"preset": "managed", "direction": "both", "clubs": {}, "include_managed": False,
                 'transfer_types': list(TRANSFER_TYPES), 'squad_types':list(squad_types.KINDS)}


def migrate_scope(config):
    if config.get("scope_rules") is not None:
        return validate_scope(config["scope_rules"])
    clubs = {str(cid): "incoming" for cid in config.get("club_ids", [])}
    preset = "all" if config.get("all_players") else "custom" if clubs else "managed" if config.get("my_club_only", True) else "custom"
    return validate_scope({"preset": preset, "direction": "incoming", "clubs": clubs,
                           "include_managed": bool(clubs and config.get("my_club_only"))})


def validate_scope(value):
    if not isinstance(value, dict):
        raise ValueError("생성 범위 설정 형식이 올바르지 않습니다.")
    value = copy.deepcopy(DEFAULT_SCOPE | value)
    if not isinstance(value["preset"], str) or not isinstance(value["direction"], str) or value["preset"] not in PRESETS or value["direction"] not in DIRECTIONS:
        raise ValueError("생성 범위 또는 영입·방출 방향을 확인하세요.")
    if not isinstance(value["clubs"], dict) or any(not str(key).isdigit() or not isinstance(direction, str) or direction not in DIRECTIONS for key, direction in value["clubs"].items()):
        raise ValueError("구단별 생성 범위는 구단 ID와 영입·방출 방향으로 지정하세요.")
    value["clubs"] = {str(key): direction for key, direction in value["clubs"].items()}
    if not isinstance(value["include_managed"], bool):
        raise ValueError("내 구단 포함 설정이 올바르지 않습니다.")
    kinds = value['transfer_types']
    if not isinstance(kinds, list) or any(not isinstance(kind, str) or kind not in TRANSFER_TYPES for kind in kinds):
        raise ValueError('이적 유형 설정을 확인하세요.')
    value['transfer_types'] = [kind for kind in TRANSFER_TYPES if kind in kinds]
    groups = value['squad_types']
    if not isinstance(groups, list) or any(not isinstance(kind,str) or kind not in squad_types.KINDS for kind in groups):
        raise ValueError('선수단 구분 설정을 확인하세요.')
    value['squad_types'] = [kind for kind in squad_types.KINDS if kind in groups]
    return value


def needs_leagues(config):
    return (config.get("scope_rules") or {}).get("preset") in ("top5", *LEAGUES)


def direction_match(direction, arrival, departure):
    return (direction in ("incoming", "both") and arrival) or (direction in ("outgoing", "both") and departure)


def matching_sides(row, config, managed):
    rules = config['scope_rules']
    cid, old = row['club_id'], row.get('from_club_id','')
    transfer = bool(old and old != cid)
    preset, direction = rules['preset'], rules['direction']
    def side_selected(side):
        source = side == 'outgoing'
        if source and not transfer:
            return False
        club = old if source else cid
        if preset == 'all':
            return direction in ('both', side)
        if preset == 'custom':
            if club in rules['clubs']:
                return rules['clubs'][club] in ('both', side)
            return rules.get('include_managed') and club in managed and direction in ('both',side)
        if direction not in ('both',side):
            return False
        if preset in ('managed','big6'):
            return club in (managed if preset == 'managed' else BIG6)
        ids = set(LEAGUES.values()) if preset == 'top5' else {LEAGUES[preset]}
        return bool(ids.intersection(row.get('from_league_ids' if source else 'league_ids', [])))
    sides = [side for side in ('incoming','outgoing') if side_selected(side)]
    if row['id'] in config['player_ids'] and 'incoming' not in sides:
        sides.insert(0,'incoming')
    return sides


def selected(row, config, managed):
    return bool(matching_sides(row, config, managed))


def reason(row, config, managed):
    if row["id"] in config["exclude_player_ids"]:
        return "제외 선수 ID"
    if not row["club_id"]:
        return "무소속 또는 소속 미확인"
    if not selected(row, config, managed):
        return "선택한 구단·선수 범위 또는 영입·방출 방향 밖"
    excluded = exclusion_reason(row, config['scope_rules'])
    if excluded:
        return excluded
    if config["max_age"] and (row.get("age") is None or int(row["age"]) > config["max_age"]):
        return "나이 제한"
    squad_result = squad_types.decision(row, config['scope_rules'], matching_sides(row, config, managed))
    if squad_result == 'unknown':
        return squad_types.WAIT
    if squad_result == 'deny':
        return '선수단 구분 범위 밖'
    return "대상"


def describe(config):
    rules = config.get("scope_rules") or migrate_scope(config)
    label = PRESETS[rules["preset"]]
    if rules["preset"] == "custom":
        label += f' · {len(rules["clubs"])}개 구단'
        counts = {direction: list(rules["clubs"].values()).count(direction) for direction in DIRECTIONS}
        choices = [f'{title} {counts[key]}' for key, title in (("outgoing", "방출"), ("incoming", "영입"), ("both", "모두")) if counts[key]]
        if choices:
            label += " · " + ", ".join(choices)
        if rules.get("include_managed"):
            label += " · 내 구단 포함"
    else:
        label += " · " + DIRECTIONS[rules["direction"]]
    if config.get("player_ids"):
        label += f' · 선택 선수 {len(config["player_ids"])}명 추가'
    kinds = rules.get('transfer_types', list(TRANSFER_TYPES))
    if set(kinds) != set(TRANSFER_TYPES):
        label += ' · ' + ('/'.join(TRANSFER_TYPES[kind] for kind in kinds) + ' 포함' if kinds else '이적 유형 모두 제외')
    groups = rules.get('squad_types',list(squad_types.KINDS))
    if set(groups) != set(squad_types.KINDS):
        label += ' · ' + ('/'.join(squad_types.KINDS[k] for k in groups) if groups else '선수단 모두 제외')
    return label
