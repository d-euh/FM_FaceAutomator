"""Classify observed club moves from explicit current and previous loan evidence."""
from __future__ import annotations


TRANSFER_TYPES = {
    'permanent': '완전 이적', 'loan': '임대 이적',
    'loan_return': '임대 복귀', 'unknown': '유형 미확인',
}


def classify_transfer(before, current):
    if not before or before['identity'] != current['identity'] or not current['club_id']:
        return 'unknown', '이전 인물·소속 정보 또는 새 소속 확인 불가'
    club, contract = current['club_id'], current.get('contract_club_id')
    old_loan, new_loan = before.get('on_loan'), current.get('on_loan')
    parent = before.get('contract_club_id')
    if new_loan is True:
        if contract == club:
            return 'unknown', '임대 상태와 계약 구단 정보가 서로 맞지 않음'
        return 'loan', '새 소속에서 임대 중임을 확인'
    if new_loan is not False:
        return 'unknown', '새 소속의 임대 여부 미확인'
    if contract != club:
        return 'unknown', '새 소속과 현재 계약 구단의 일치 확인 불가'
    if old_loan is True:
        if not parent or parent == before['club_id']:
            return 'unknown', '이전 임대의 원소속 구단 미확인'
        if parent == club:
            return 'loan_return', '이전 임대 종료 후 원소속 구단 복귀 확인'
        return 'permanent', '이전 임대 원소속과 다른 구단의 비임대 계약 확인'
    if old_loan is False or not before['club_id']:
        return 'permanent', '비임대 소속·계약 변경 확인 · 자유계약 영입 포함'
    return 'unknown', '이전 임대 여부 미확인 · 복귀 여부 판정 불가'


def event_type(row):
    """No type filter for explicit current-player generation; old moves are unknown."""
    if row.get('manual_request'):
        return None
    if 'transfer_type' in row:
        return row['transfer_type'] if row['transfer_type'] in TRANSFER_TYPES else 'unknown'
    if row.get('from_club_id') and row['from_club_id'] != row['club_id']:
        return 'unknown'
    return None


def exclusion_reason(row, rules):
    kind = event_type(row)
    if kind and kind not in rules.get('transfer_types', TRANSFER_TYPES):
        return '이적 유형 제외: ' + TRANSFER_TYPES[kind]
    return None
