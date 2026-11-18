"""Resolve top-flight participants from this save's current-season fixture calendar."""
from __future__ import annotations

from scope_rules import LEAGUES


def read_catalog(save, clubs, game_date, include_leagues=False):
    catalog = {str(c.unique_id): {"id": str(c.unique_id), "name": getattr(c, "name", "") or str(c.unique_id),
                               "short_name": getattr(c, "short_name", "") or "", "league_ids": []}
               for c in clubs.values() if c.unique_id is not None}
    status = {"requested": include_leagues, "resolved": [], "error": ""}
    if not include_leagues:
        return list(catalog.values()), status
    try:
        date = str(game_date or "")[:10]
        year = int(date[:4]) - (int(date[5:7]) < 7)
        start, end = f"{year:04}-07-01", f"{year + 1:04}-07-01"
        competitions = {c.id: str(c.database_id) for c in save.competitions() if str(c.database_id) in LEAGUES.values()}
        members = {cid: set() for cid in LEAGUES.values()}
        for fixture in save.fixtures():
            league = competitions.get(fixture.competition_id)
            played = str(fixture.date or "")[:10]
            if league is None or not start <= played < end:
                continue
            for uid in (fixture.home_club_uid, fixture.away_club_uid):
                club = clubs.get(uid)
                if club is not None and club.unique_id is not None:
                    members[league].add(str(club.unique_id))
        for league, ids in members.items():
            if ids:
                status["resolved"].append(league)
                for cid in ids:
                    catalog[cid]["league_ids"].append(league)
        status["season"] = f"{year}/{year + 1}"
        if not status["resolved"]:
            status["error"] = "현재 시즌의 5대 리그 일정을 확인하지 못했습니다. 일정 생성 후 저장하거나 구단 직접 설정을 사용하세요."
    except Exception as exc:
        status["error"] = "리그 참가 구단 읽기 실패: " + str(exc)
    return list(catalog.values()), status
