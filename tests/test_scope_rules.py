import copy
from types import SimpleNamespace as NS
import unittest

from engine import DEFAULTS, in_scope
from league_catalog import read_catalog
from scope_rules import BIG6, DEFAULT_SCOPE, LEAGUES, migrate_scope, validate_scope


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(DEFAULTS)
        self.c["scope_rules"] = copy.deepcopy(DEFAULT_SCOPE)
        self.row = {"id": "29178504", "club_id": "602", "from_club_id": "680", "age": 26,
                    "league_ids": ["11"], "from_league_ids": ["11"]}

    def custom(self, direction):
        self.c["scope_rules"].update(preset="custom", clubs={"680": direction})

    def test_outgoing_matches_source_even_if_destination_not_selected(self):
        self.custom("outgoing")
        self.assertTrue(in_scope(self.row, self.c, []))
        self.assertFalse(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, []))

    def test_incoming_matches_destination_only(self):
        self.custom("incoming")
        self.assertFalse(in_scope(self.row, self.c, []))
        self.assertTrue(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, []))

    def test_both_matches_either_side(self):
        self.custom("both")
        self.assertTrue(in_scope(self.row, self.c, []))
        self.assertTrue(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, []))

    def test_explicit_club_direction_wins_over_include_managed(self):
        self.custom("outgoing")
        self.c["scope_rules"].update(direction="both", include_managed=True)
        self.assertFalse(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, ["680"]))
        self.assertTrue(in_scope(self.row, self.c, ["680"]))

    def test_each_custom_club_has_independent_direction(self):
        self.c["scope_rules"].update(preset="custom", clubs={"680": "outgoing", "602": "incoming"})
        self.assertTrue(in_scope(self.row, self.c, []))
        self.assertFalse(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, []))

    def test_managed_default_covers_arrivals_and_departures(self):
        self.assertTrue(in_scope(self.row, self.c, ["680"]))
        self.assertTrue(in_scope(self.row | {"club_id": "680", "from_club_id": "602"}, self.c, ["680"]))
        self.assertFalse(in_scope(self.row | {"club_id": "999", "from_club_id": "888"}, self.c, ["680"]))

    def test_exclusions_age_and_free_agent_still_apply(self):
        self.custom("outgoing")
        self.c["max_age"] = 20
        self.assertFalse(in_scope(self.row, self.c, []))
        self.c["max_age"] = 0
        self.c["exclude_player_ids"] = ["29178504"]
        self.assertFalse(in_scope(self.row, self.c, []))
        self.c["exclude_player_ids"] = []
        self.assertFalse(in_scope(self.row | {"club_id": ""}, self.c, []))

    def test_all_and_each_league_preset(self):
        self.c["scope_rules"]["preset"] = "all"
        self.assertTrue(in_scope(self.row | {"league_ids": [], "from_league_ids": []}, self.c, []))
        for key, cid in LEAGUES.items():
            with self.subTest(key=key):
                self.c["scope_rules"].update(preset=key, direction="incoming")
                self.assertTrue(in_scope(self.row | {"league_ids": [cid]}, self.c, []))
                self.assertFalse(in_scope(self.row | {"league_ids": [], "from_league_ids": [cid]}, self.c, []))
                self.c["scope_rules"]["direction"] = "outgoing"
                self.assertTrue(in_scope(self.row | {"league_ids": [], "from_league_ids": [cid]}, self.c, []))
        self.c["scope_rules"].update(preset="top5", direction="both")
        self.assertTrue(in_scope(self.row | {"league_ids": ["22"]}, self.c, []))
        self.assertFalse(in_scope(self.row | {"league_ids": [], "from_league_ids": []}, self.c, []))

    def test_big6_uses_six_clubs_not_current_league_position(self):
        self.assertEqual(len(BIG6), 6)
        self.c["scope_rules"]["preset"] = "big6"
        self.assertTrue(in_scope(self.row | {"club_id": "9999"}, self.c, []))
        self.assertFalse(in_scope(self.row | {"club_id": "9999", "from_club_id": "8888"}, self.c, []))

    def test_legacy_config_preserves_incoming_and_combined_club_selection(self):
        rules = migrate_scope(self.c | {"scope_rules": None, "club_ids": ["680"], "my_club_only": True})
        self.assertEqual(rules["clubs"], {"680": "incoming"})
        self.assertTrue(rules["include_managed"])
        self.assertEqual(rules["direction"], "incoming")

    def test_invalid_direction_cannot_be_saved(self):
        with self.assertRaises(ValueError):
            validate_scope({"clubs": {"680": "invalid"}})

    def test_type_filter_applies_to_selected_players_and_outgoing_unselected_destinations(self):
        self.custom('outgoing')
        self.c['scope_rules']['transfer_types'] = ['permanent','loan_return']
        self.c['player_ids'] = [self.row['id']]
        for kind, allowed in [('permanent',True), ('loan',False), ('loan_return',True), ('unknown',False)]:
            with self.subTest(kind=kind):
                self.assertEqual(in_scope(self.row | {'transfer_type':kind}, self.c, []), allowed)

    def test_all_presets_obey_types_and_current_player_generation_is_unfiltered(self):
        for preset in ('all','managed','big6','premier_league','top5'):
            self.c['scope_rules'].update(preset=preset,transfer_types=[])
            with self.subTest(preset=preset):
                self.assertFalse(in_scope(self.row | {'transfer_type':'loan'}, self.c, ['602']))
                current = {key:value for key,value in self.row.items() if key != 'from_club_id'}
                self.assertTrue(in_scope(current, self.c, ['602']))


class LeagueCatalogTests(unittest.TestCase):
    def clubs(self):
        return {i: NS(unique_id=100 + i, name=f"Club {i}", short_name=f"C{i}") for i in range(1, 5)}

    def test_current_save_season_and_database_competition_ids_drive_membership(self):
        save = NS(competitions=lambda: [NS(id=9000, database_id=11), NS(id=9001, database_id=1300)],
                  fixtures=lambda: [NS(competition_id=9000, date="2026-08-01", home_club_uid=1, away_club_uid=2),
                                    NS(competition_id=9000, date="2027-08-01", home_club_uid=3, away_club_uid=4),
                                    NS(competition_id=9001, date="2027-08-01", home_club_uid=1, away_club_uid=2)])
        catalog, status = read_catalog(save, self.clubs(), "2027-08-02", True)
        index = {c["id"]: c for c in catalog}
        self.assertEqual(index["101"]["league_ids"], [])
        self.assertEqual(index["103"]["league_ids"], ["11"])
        self.assertEqual(status["season"], "2027/2028")
        self.assertEqual(status["window"], {"start": "2027-07-01", "end_exclusive": "2028-07-01"})
        self.assertEqual(status["counts"], {"competitions": 2, "fixtures": 3})
        self.assertEqual(status["leagues"]["11"], {
            "competitions": 1, "fixtures": 2, "season_fixtures": 1, "unmatched_club_refs": 0, "clubs": 2})
        self.assertEqual(status["error_code"], "")

    def test_diagnostics_distinguish_empty_competition_calendar_and_club_joins(self):
        fixture = NS(competition_id=9000, date="2027-08-01", home_club_uid=1, away_club_uid=2)
        competition = NS(id=9000, database_id=11)
        cases = (
            ([], [fixture], self.clubs(), "competition_not_found"),
            ([competition], [NS(**(vars(fixture) | {"date": "2026-08-01"}))], self.clubs(), "season_fixtures_not_found"),
            ([competition], [fixture], {}, "club_references_not_found"),
        )
        for competitions, fixtures, clubs, code in cases:
            with self.subTest(code=code):
                save = NS(competitions=lambda: iter(competitions), fixtures=lambda: iter(fixtures))
                catalog, status = read_catalog(save, clubs, "2027-08-02", True)
                self.assertEqual(status["error_code"], code)
                self.assertEqual(status["resolved"], [])
                self.assertNotIn("일정 생성 후", status["error"])
                self.assertIn("자동으로 다시 감지되지 않습니다", status["error"])
                self.assertTrue(all(not club["league_ids"] for club in catalog))
                self.assertEqual(status["leagues"]["11"]["unmatched_club_refs"], 2 if not clubs else 0)

    def test_season_boundaries_are_reported_and_applied_without_guessing_membership(self):
        save = NS(competitions=lambda: [NS(id=9000, database_id=11)],
                  fixtures=lambda: [NS(competition_id=9000, date="2027-06-30", home_club_uid=1, away_club_uid=2),
                                    NS(competition_id=9000, date="2027-07-01", home_club_uid=3, away_club_uid=4)])
        for game_date, season, ids in (("2027-06-30", "2026/2027", {"101", "102"}),
                                      ("2027-07-01", "2027/2028", {"103", "104"})):
            with self.subTest(game_date=game_date):
                catalog, status = read_catalog(save, self.clubs(), game_date, True)
                self.assertEqual(status["season"], season)
                self.assertEqual({c["id"] for c in catalog if c["league_ids"]}, ids)

    def test_partial_calendar_failure_records_progress_without_publishing_partial_members(self):
        def fixtures():
            yield NS(competition_id=9000, date="2027-08-01", home_club_uid=1, away_club_uid=2)
            raise ValueError("broken calendar")
        save = NS(competitions=lambda: [NS(id=9000, database_id=11)], fixtures=fixtures)
        catalog, status = read_catalog(save, self.clubs(), "2027-08-02", True)
        self.assertEqual(status["error_code"], "read_failed")
        self.assertIn("broken calendar", status["error"])
        self.assertEqual(status["counts"]["fixtures"], 1)
        self.assertEqual(status["leagues"]["11"]["season_fixtures"], 1)
        self.assertEqual(status["resolved"], [])
        self.assertTrue(all(not club["league_ids"] for club in catalog))

    def test_invalid_game_date_is_reported_before_reading_calendar(self):
        _, status = read_catalog(NS(), self.clubs(), "2027-99-01", True)
        self.assertEqual(status["error_code"], "read_failed")
        self.assertEqual(status["counts"], {"competitions": 0, "fixtures": 0})

    def test_missing_league_reader_never_invents_real_world_members(self):
        catalog, status = read_catalog(NS(), self.clubs(), "2027-08-02", True)
        self.assertEqual(len(catalog), 4)
        self.assertTrue(status["error"])
        self.assertTrue(all(not club["league_ids"] for club in catalog))

    def test_default_managed_scope_does_not_require_fixture_reader(self):
        _, status = read_catalog(NS(), self.clubs(), "2027-08-02", False)
        self.assertFalse(status["requested"])
        self.assertEqual(status["error"], "")
        self.assertNotIn("counts", status)
