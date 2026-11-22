import copy
import json
import unittest
from PIL import Image
from engine import normalise
from scope_rules import DEFAULT_SCOPE
import test_queue_controls as fixtures


class QueueWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QueueControlTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.e = self.fixture.engine
        self.e.c['scope_rules'] = copy.deepcopy(DEFAULT_SCOPE) | {'preset': 'all', 'direction': 'both'}

    def test_managed_arrivals_and_departures_only_lead_their_new_batch(self):
        self.e.reorder_job(3, 'first')
        players = [json.loads(record[0]) for record in self.e.db.execute('SELECT data FROM people ORDER BY id')]
        for pid, club in ((4, '10'), (5, '10'), (6, '20'), (7, '10')):
            players.append(dict(id=str(pid), uid=pid, name=str(pid), club_id=club, club_name=club))
        before = normalise(dict(players=players, managed_club_ids=['20'], game_date='2027-07-03'))
        self.e.ingest(before)
        after = copy.deepcopy(before)
        for row, club in zip(after['players'][3:], ('30', '20', '40', '50')):
            row['club_id'] = club
        self.assertEqual(self.e.ingest(after), 4)
        self.assertEqual([job['player_id'] for job in self.e.jobs()], ['3', '1', '2', '5', '6', '4', '7'])
        with self.e.db:
            self.e.db.execute("INSERT INTO people VALUES ('8',?)", (json.dumps(dict(after['players'][3], id='8', uid=8, identity='8:8:')),))
        later = copy.deepcopy(after)
        later['players'].append(dict(id='8', uid=8, identity='8:8:', name='8', club_id='20', club_name='20'))
        self.e.ingest(later)
        self.assertEqual(self.e.jobs()[-1]['player_id'], '8')
        self.assertEqual(self.e.next_job(9999999999)['player_id'], '3')

    def test_completion_hides_only_when_new_jobs_are_added_and_preserves_receipts(self):
        artifact = self.fixture.root / 'retained.png'
        Image.new('RGB', (350, 350), 'gray').save(artifact)
        self.e.update(1, 'applied', artifact=str(artifact))
        with self.e.db:
            self.e.db.execute("INSERT INTO attempts VALUES (1,1)")
            self.e.db.execute("INSERT INTO applied VALUES ('1',1,'1')")
            self.e.db.execute("INSERT INTO paid_results VALUES (1,'retained-folder','{}')")
        same = normalise(dict(players=[json.loads(r[0]) for r in self.e.db.execute('SELECT data FROM people')]))
        self.assertEqual(self.e.ingest(same), 0)
        self.assertIn(1, [job['id'] for job in self.e.jobs()])
        self.e.enqueue_manual('2')
        self.assertNotIn(1, [job['id'] for job in self.e.jobs()])
        self.assertEqual(self.e.db.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'applied')
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM paid_results').fetchone()[0], 1)
        self.assertEqual(self.e.recent_results()[0]['id'], 1)
        self.assertTrue(artifact.is_file())

    def test_progress_between_rendering_and_save_preserves_paid_result_and_resumes_without_ai(self):
        from pathlib import Path
        from unittest.mock import patch
        from team_reader import GameWait
        with patch.object(self.e, 'apply', side_effect=GameWait('게임 진행 중')):
            self.assertTrue(self.e.run_one(self.fixture.runner, job_id=1))
        job = next(job for job in self.e.jobs() if job['id'] == 1)
        self.assertEqual(job['status'], 'generated')
        self.assertTrue(json.loads(job['data'])['game_wait'])
        self.assertTrue(Path(job['artifact']).is_file())
        receipt = self.e.db.execute('SELECT folder FROM paid_results WHERE job_id=1').fetchone()[0]
        self.assertTrue((Path(receipt) / 'portrait.png').is_file())
        self.assertTrue(self.e.run_one(lambda *args, **kwargs: self.fail('No second AI request'), job_id=1))
        self.assertEqual(self.e.db.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'applied')
        self.assertEqual(self.fixture.calls, [1])
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)

    def test_legacy_scope_also_prioritizes_managed_departures_within_new_batch(self):
        self.e.c['scope_rules'] = None
        people = [json.loads(row[0]) for row in self.e.db.execute('SELECT data FROM people ORDER BY id')]
        other = dict(id='4', uid=4, name='Other', club_id='10', club_name='10')
        before = normalise(dict(players=[other] + people, managed_club_ids=['20']))
        self.e.ingest(before)
        after = copy.deepcopy(before)
        after['players'][0]['club_id'] = '50'
        after['players'][1]['club_id'] = '60'
        self.assertEqual(self.e.ingest(after), 2)
        self.assertEqual([job['player_id'] for job in self.e.jobs() if job['status'] == 'pending'], ['2', '3', '1', '4'])
