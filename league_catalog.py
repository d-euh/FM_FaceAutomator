"""Resolve top-flight participants from this save's current-season fixture calendar."""
from __future__ import annotations

from datetime import date

from scope_rules import LEAGUES


def read_catalog(save, clubs, game_date, include_leagues=False):
    catalog = {str(c.unique_id): {"id": str(c.unique_id), "name": getattr(c, "name", "") or str(c.unique_id),
                               "short_name": getattr(c, "short_name", "") or "", "league_ids": []}
               for c in clubs.values() if c.unique_id is not None}
    status = {"requested": include_leagues, "resolved": [], "error": ""}
    if not include_leagues:
        return list(catalog.values()), status
    # Fixed-size counters locate a failed join without exporting fixture/player
    # lists or retaining another copy of the save's calendar in memory.
    status["game_date"] = str(game_date or "")[:10]
    status["counts"] = {"competitions": 0, "fixtures": 0}
    status["leagues"] = {
        league: {"competitions": 0, "fixtures": 0, "season_fixtures": 0,
                 "unmatched_club_refs": 0, "clubs": 0}
        for league in LEAGUES.values()}
    status["error_code"] = ""
    try:
        current = date.fromisoformat(status["game_date"])
        year = current.year - (current.month < 7)
        start, end = f"{year:04}-07-01", f"{year + 1:04}-07-01"
        status["season"] = f"{year}/{year + 1}"
        status["window"] = {"start": start, "end_exclusive": end}
        competitions = {}
        for competition in save.competitions():
            status["counts"]["competitions"] += 1
            league = str(competition.database_id)
            if league in status["leagues"]:
                competitions[competition.id] = league
                status["leagues"][league]["competitions"] += 1
        members = {cid: set() for cid in LEAGUES.values()}
        for fixture in save.fixtures():
            status["counts"]["fixtures"] += 1
            league = competitions.get(fixture.competition_id)
            if league is None:
                continue
            counters = status["leagues"][league]
            counters["fixtures"] += 1
            played = str(fixture.date or "")[:10]
            if not start <= played < end:
                continue
            counters["season_fixtures"] += 1
            for uid in (fixture.home_club_uid, fixture.away_club_uid):
                club = clubs.get(uid)
                if club is not None and club.unique_id is not None:
                    members[league].add(str(club.unique_id))
                else:
                    counters["unmatched_club_refs"] += 1
        for league, ids in members.items():
            status["leagues"][league]["clubs"] = len(ids)
            if ids:
                status["resolved"].append(league)
                for cid in ids:
                    catalog[cid]["league_ids"].append(league)
        if not status["resolved"]:
            status["error_code"] = (
                "competition_not_found" if not competitions else
                "season_fixtures_not_found" if not any(c["season_fixtures"] for c in status["leagues"].values()) else
                "club_references_not_found")
            status["error"] = ("연결한 세이브에서 현재 시즌의 5대 리그 참가 구단을 확인하지 못했습니다. "
                               "연결할 세이브 파일을 확인하거나 구단 직접 설정을 사용하세요. "
                               "리그 범위를 확인하지 못해 제외된 이적은 자동으로 다시 감지되지 않습니다.")
    except Exception as exc:
        status["error_code"] = "read_failed"
        status["error"] = "리그 참가 구단 읽기 실패: " + str(exc)
    return list(catalog.values()), status
