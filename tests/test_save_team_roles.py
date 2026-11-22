from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import verify_save_team_roles as probe
from scripts.verify_save_team_roles import compare_native, samples
from team_reader import GameWait


class SaveTeamRoleTests(unittest.TestCase):
    def setUp(self):
        self.records = [dict(team_id=0, unique_id=500, raw_type=0, raw_flag=0),
                        dict(team_id=1, unique_id=501, raw_type=0, raw_flag=0),
                        dict(team_id=2, unique_id=800, raw_type=11, raw_flag=1)]
        self.clubs = {40: dict(id=500, name='Northbridge', teams=[
                        dict(team_id=0, club_uid=40, is_affiliate=False),
                        dict(team_id=1, club_uid=41, is_affiliate=True),
                        dict(team_id=2, club_uid=40, is_affiliate=False)]),
                      41: dict(id=501, name='Southbridge', teams=[
                        dict(team_id=1, club_uid=41, is_affiliate=False)])}
        self.plan = dict(sha256='a' * 64, managed_club_ids=[500],
                         samples=samples(self.clubs, self.records, [500]))
        self.rows = {}
        for r in self.records:
            tid = r['team_id']
            self.rows[tid] = {'native_team_index': tid, 'values': {
                'UniqueId': {'scalar': r['unique_id']},
                'Club.UniqueId': {'scalar': 501 if tid == 1 else 500},
                'IsFirstTeam': {'scalar': tid != 2}, 'TeamType': {'scalar': r['raw_type']}}}
        self.rows[0]['values']['Club.ReservesTeam'] = self.ref(1)
        self.rows[0]['values']['Club.YouthTeam'] = self.ref(2)
        self.calls = []

    @staticmethod
    def ref(index):
        return dict(record_table='Team', record_index=index)

    def reader(self):
        def resolve(targets, managed, snapshot):
            self.calls.append((targets, managed, snapshot))
            return self.rows
        return SimpleNamespace(resolve=resolve, last_context={'session': 'test', 'generation': 1})

    def test_controlled_team_keeps_child_identity_and_parent_reserve_reference(self):
        result = compare_native(self.plan, self.reader())
        parent = next(c for c in result['clubs'] if c['club_id'] == 500)
        child = next(t for t in parent['teams'] if t['saved']['team_id'] == 1)
        self.assertEqual(child['saved']['owner_club_id'], 501)
        self.assertIs(child['native']['values']['IsFirstTeam']['scalar'], True)
        self.assertEqual(child['parent_reference_matches'], ['Club.ReservesTeam'])
        youth = next(t for t in parent['teams'] if t['saved']['team_id'] == 2)
        self.assertEqual(youth['parent_reference_matches'], ['Club.YouthTeam'])
        self.assertEqual(self.calls, [([0, 1, 2], [500], 'a' * 64)])
        self.assertFalse(any('kind' in t for t in parent['teams']))

    def test_same_raw_type_can_be_sampled_as_own_team_and_controlled_youth(self):
        clubs = deepcopy(self.clubs)
        clubs[41]['teams'].append(dict(team_id=2, club_uid=40, is_affiliate=True))
        selected = samples(clubs, self.records, [])
        self.assertEqual({c['club_id'] for c in selected}, {500, 501})
        for club in selected:
            self.assertIn(club['anchor_team_id'], [0, 1])
        broken = deepcopy(clubs)
        broken[40]['id'] = 999
        with self.assertRaises(ValueError):
            samples(broken, self.records, [999])

    def test_mismatched_ids_owners_cleanup_and_nonboolean_anchor_stop_comparison(self):
        original = deepcopy(self.rows)
        for field, value in (('UniqueId', 999), ('Club.UniqueId', 999),
                             ('UniqueId', True), ('IsFirstTeam', 1)):
            with self.subTest(field=field, value=value):
                self.rows = deepcopy(original)
                self.rows[0]['values'][field] = {'scalar': value}
                with self.assertRaises(ValueError):
                    compare_native(self.plan, self.reader())
        self.rows = deepcopy(original)
        self.rows[1]['cleanup_error'] = 'cleanup failed'
        with self.assertRaises(ValueError):
            compare_native(self.plan, self.reader())
        self.rows = deepcopy(original)
        self.rows[1]['values'] = None
        with self.assertRaises(ValueError):
            compare_native(self.plan, self.reader())

    def test_invalid_refs_never_become_relationship_matches(self):
        invalid = [self.ref(1) | {'error': 'failed'}, self.ref(1) | {'is_null': True},
                   self.ref(True), self.ref(1) | {'record_table': 'Person'}, ['bad shape']]
        for ref in invalid:
            with self.subTest(ref=ref):
                self.rows[0]['values']['Club.ReservesTeam'] = ref
                result = compare_native(self.plan, self.reader())
                parent = next(c for c in result['clubs'] if c['club_id'] == 500)
                child = next(t for t in parent['teams'] if t['saved']['team_id'] == 1)
                self.assertEqual(child['parent_reference_matches'], [])

    def test_busy_game_propagates_and_no_requests_without_manager_proof_or_bound(self):
        def busy(*args):
            raise GameWait('game busy')
        with self.assertRaises(GameWait):
            compare_native(self.plan, SimpleNamespace(resolve=busy))
        for plan in (self.plan | {'managed_club_ids': []},
                     self.plan | {'samples': [dict(teams=[dict(team_id=i) for i in range(257)])]}):
            with self.assertRaises(ValueError):
                compare_native(plan, self.reader())
        self.assertEqual(self.calls, [])

    def test_failed_runtime_writes_error_and_only_unverified_partial_observations(self):
        def busy(*args):
            raise GameWait('game busy')
        reader = SimpleNamespace(resolve=busy, cache={('session', 3, 'a' * 64): self.rows[0]})
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'report.json'
            with (patch.object(probe, 'os', SimpleNamespace(name='nt')),
                  patch.object(probe, 'read_save', return_value=self.plan),
                  patch.object(probe, 'TeamReader', return_value=reader),
                  patch.object(sys, 'argv', ['probe', 'test.fm', '--output', str(destination)]),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(probe.main(), 1)
            report = json.loads(destination.read_text(encoding='utf-8'))
            self.assertIsNone(report['native'])
            self.assertEqual(report['error'], 'game busy')
            self.assertFalse(report['loaded_save_file_verified'])
            self.assertEqual(report['unverified_native_results'][0]['result'], self.rows[0])


if __name__ == '__main__':
    unittest.main()
