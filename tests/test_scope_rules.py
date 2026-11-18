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

    def test_missing_league_reader_never_invents_real_world_members(self):
        catalog, status = read_catalog(NS(), self.clubs(), "2027-08-02", True)
        self.assertEqual(len(catalog), 4)
        self.assertTrue(status["error"])
        self.assertTrue(all(not club["league_ids"] for club in catalog))

    def test_default_managed_scope_does_not_require_fixture_reader(self):
        _, status = read_catalog(NS(), self.clubs(), "2027-08-02", False)
        self.assertFalse(status["requested"])
        self.assertEqual(status["error"], "")
