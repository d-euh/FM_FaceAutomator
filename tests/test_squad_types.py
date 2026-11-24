import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from engine import DEFAULTS, Engine, file_stamp, in_scope, normalise
from scope_rules import DEFAULT_SCOPE, matching_sides, reason, validate_scope
from squad_types import WAIT, native_role
from squad_types import TeamReadPending
from save_teams import BUILD, VERSION


def native(index, kind, club=680):
    def scalar(v): return {'scalar':v,'error':None,'is_null':False}
    def ref(i): return {'record_table':'Team','record_index':i,'error':None,'is_null':False}
    return {'native_team_index':index,'error':None,'cleanup_error':None,'values':{
        'UniqueId':scalar(680 if index==540 else 2000000000+index),'Club.UniqueId':scalar(club),
        'IsFirstTeam':scalar(kind=='first'),'TeamType':scalar(0 if kind=='first' else 10),
        'Club.ReservesTeam':ref(index if kind=='reserve' else 900),
        'Club.YouthTeam':ref(index if kind=='youth' else 901),
        'TeamContainer.HighestLevelYouthTeam':ref(index if kind in ('reserve','youth') else 902)}}


class SquadTests(unittest.TestCase):
    def setUp(self):
        self.c=copy.deepcopy(DEFAULTS)
        self.c['scope_rules']=copy.deepcopy(DEFAULT_SCOPE)
        self.c['scope_rules'].update(preset='custom',clubs={'680':'outgoing'},squad_types=['first'])
        self.row={'id':'1','club_id':'602','from_club_id':'680','age':20,
                  'from_team_id':540,'from_registered_club_id':'680',
                  'squad_evidence':{'outgoing':{'kind':'first'},'incoming':{'kind':'youth'}}}

    def test_departure_uses_source_and_arrival_uses_destination(self):
        self.assertEqual(matching_sides(self.row,self.c,[]),['outgoing'])
        self.assertTrue(in_scope(self.row,self.c,[]))
        reverse=self.row|{'squad_evidence':{'outgoing':{'kind':'youth'},'incoming':{'kind':'first'}}}
        self.assertFalse(in_scope(reverse,self.c,[]))
        self.c['scope_rules']['clubs']={'602':'incoming'}
        self.assertFalse(in_scope(self.row,self.c,[]))
        self.assertTrue(in_scope(reverse,self.c,[]))

    def test_selected_player_does_not_erase_selected_club_departure(self):
        self.c['player_ids'] = ['1']
        self.assertEqual(matching_sides(self.row,self.c,[]),['incoming','outgoing'])
        self.assertTrue(in_scope(self.row,self.c,[]))

    def test_both_sides_are_a_union_but_unknown_cannot_authorize_generation(self):
        self.c['scope_rules']['clubs']={'680':'outgoing','602':'incoming'}
        self.assertTrue(in_scope(self.row,self.c,[]))
        self.assertEqual(reason(self.row|{'squad_evidence':{}},self.c,[]),WAIT)
        self.c['scope_rules']['squad_types']=[]
        self.assertFalse(in_scope(self.row,self.c,[]))

    def test_existing_scope_defaults_include_all_without_lookup(self):
        value=validate_scope({'preset':'managed','direction':'both','clubs':{},'include_managed':False})
        self.assertEqual(value['squad_types'],['first','reserve','youth'])
        self.c['scope_rules']['squad_types']=['first','reserve','youth']
        self.assertEqual(reason(self.row|{'squad_evidence':{}},self.c,[]),'대상')
        with self.assertRaises(ValueError): validate_scope({'squad_types':['slot0']})

    def test_native_relationships_beat_age_numeric_codes_and_names(self):
        self.assertEqual(native_role(native(540,'first'),'680')['kind'],'first')
        reserve=native(28346,'reserve')
        self.assertEqual(native_role(reserve,'680')['kind'],'reserve') # also a highest youth reference
        self.assertEqual(native_role(native(28347,'youth'),'680')['kind'],'youth')
        self.assertEqual(native_role(reserve,'602')['kind'],'unknown')
        reserve['values']['Club.ReservesTeam']['record_index']=888
        reserve['values']['TeamContainer.HighestLevelYouthTeam']['record_index']=888
        self.assertEqual(native_role(reserve,'680')['kind'],'unknown') # do not guess type 10/U21 label
        reserve['cleanup_error']='uncertain'
        self.assertEqual(native_role(reserve,'680')['kind'],'unknown')


class EngineSquadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.c=copy.deepcopy(DEFAULTS)
        self.c.update(state_dir=str(root/'state'),source=str(root/'save.fm'),settle_seconds=0,cooldown_hours=0)
        Path(self.c['source']).write_bytes(b'fixture')
        self.c['scope_rules']=copy.deepcopy(DEFAULT_SCOPE)
        self.c['scope_rules'].update(preset='custom',clubs={'680':'outgoing'},squad_types=['first'])
        self.e=Engine(self.c);self.addCleanup(self.e.db.close)
        self.e.refresh=lambda:0
        self.snap=lambda club,team:normalise({'players':[{'id':1,'uid':10,'name':'Test','club_id':club,'club_name':str(club),
            'registered_club_id':str(club) if club is not None else '', 'registered_team_id':team}],
            'managed_club_ids':['680'],'source_stamp':list(file_stamp(self.c['source']))})
        self.e.ingest(self.snap(680,540),now=1)
        self.e.ingest(self.snap(602,900),now=2)
        self.enable_save_backend()

    def enable_save_backend(self):
        self.e.setmeta('squad_status', json.dumps(dict(mode='save', version=VERSION, build=BUILD,
            source_stamp=list(file_stamp(self.c['source'])))))

    def test_queue_retains_both_event_sides_and_saved_filter_runs_before_codex(self):
        job=self.e.db.execute('SELECT * FROM jobs').fetchone()
        self.assertEqual(json.loads(job['data'])['from_team_id'],540)
        self.e.saved_squad=Mock(return_value=native_role(native(540,'first'), '680'))
        self.assertIsNotNone(self.e.next_job(time.time()))
        row=json.loads(self.e.jobs()[0]['data'])
        self.assertEqual(row['squad_evidence']['outgoing']['kind'],'first')
        self.e.saved_squad=Mock(return_value=native_role(native(540,'youth'), '680'))
        self.assertIsNone(self.e.next_job(time.time()))
        self.assertEqual(self.e.jobs()[0]['status'],'superseded')
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)

    def test_unknown_saved_role_blocks_and_recovers_without_ai_retry(self):
        self.e.saved_squad=Mock(return_value={'kind': 'unknown', 'reason': '세이브 팀 구분 확인 불가'})
        runner=Mock()
        self.assertFalse(self.e.run_one(runner))
        runner.assert_not_called()
        self.assertEqual(self.e.jobs()[0]['status'],'blocked')
        self.e.retry_preflight()
        self.e.saved_squad=Mock(return_value=native_role(native(540,'first'), '680'))
        self.assertIsNotNone(self.e.next_job(time.time()))

    def test_unknown_scope_cannot_apply_an_already_paid_image(self):
        job=self.e.jobs()[0]
        self.e.update(job['id'],'generated')
        self.e.saved_squad=Mock(return_value={'kind': 'unknown', 'reason': '세이브 팀 구분 확인 불가'})
        with self.assertRaises(TeamReadPending): self.e.apply(job['id'])
        self.assertEqual(self.e.jobs()[0]['status'],'generated')

    def test_all_squad_types_never_need_plugin(self):
        self.c['scope_rules']['squad_types']=['first','reserve','youth']
        self.e.saved_squad=Mock(side_effect=AssertionError('No native lookup'))
        self.assertIsNotNone(self.e.next_job(time.time()))
        self.e.saved_squad.assert_not_called()

    def test_contract_only_arrival_is_unknown_and_never_inferred_as_first_team(self):
        self.c['scope_rules']['clubs']={'602':'incoming'}
        person=json.loads(self.e.db.execute('SELECT data FROM people').fetchone()[0])
        person.update(registered_club_id='680',registered_team_id=540,club_basis='contract_change')
        with self.e.db:
            self.e.db.execute('UPDATE people SET data=?',(json.dumps(person),))
        self.e.saved_squad=Mock(side_effect=AssertionError('Cannot query old registration as destination'))
        self.assertIsNone(self.e.next_job(time.time()))
        self.e.saved_squad.assert_not_called()
        self.assertEqual(self.e.jobs()[0]['status'],'blocked')

    def test_previous_squad_survives_a_free_agent_gap(self):
        self.c['scope_rules']['clubs']={'602':'outgoing'}
        self.e.ingest(self.snap(None,None),now=3)
        self.e.ingest(self.snap(680,540),now=4)
        event=json.loads(self.e.db.execute('SELECT data FROM jobs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(event['from_club_id'],'602')
        self.assertEqual(event['from_team_id'],900)
        self.assertEqual(event['from_registered_club_id'],'602')

    def test_last_valid_registration_survives_missing_team_before_release(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        self.e.ingest(self.snap(602, None), now=3)
        for now in (4, 5, 6):
            self.e.ingest(self.snap(None, None), now=now)
        self.e.ingest(self.snap(680, 540), now=7)
        job = self.e.db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
        event = json.loads(job['data'])
        self.assertEqual((event['from_team_id'], event['from_registered_club_id']), (900, '602'))
        self.enable_save_backend()
        event.pop('from_squad_role', None)
        self.e.db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(event), job['id']))
        self.e.saved_squad=Mock(return_value=native_role(native(900, 'reserve', 602), '602'))
        self.assertEqual(self.e.enrich_squads(job)['squad_evidence']['outgoing']['kind'], 'reserve')

    def test_departure_keeps_most_recent_valid_squad_assignment(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        self.e.ingest(self.snap(602, 901), now=3)
        self.e.ingest(self.snap(602, None), now=4)
        self.e.ingest(self.snap(None, None), now=5)
        self.e.ingest(self.snap(680, 540), now=6)
        event = json.loads(self.e.db.execute('SELECT data FROM jobs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(event['from_team_id'], 901)

    def test_missing_registration_is_not_queued_or_announced_without_historical_evidence(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        with self.e.db:
            self.e.db.execute('DELETE FROM people')
        self.e.ingest(self.snap(602, None), now=3)
        self.e.ingest(self.snap(None, None), now=4)
        self.e.ingest(self.snap(680, 540), now=5)
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
        self.assertFalse(any(job['status'] in ('pending', 'blocked') for job in self.e.jobs()))
        summary = json.loads(self.e.meta('detection_summary'))
        self.assertEqual((summary['club_changes'], summary['queued'], summary['changes']), (0, 0, []))
        runner = Mock()
        self.e.run_one(runner)
        runner.assert_not_called()

    def test_free_agent_arrival_waits_for_new_team_then_recovers_existing_job(self):
        self.c['scope_rules']['clubs'] = {'680': 'incoming'}
        self.e.ingest(self.snap(None, None), now=3)
        self.e.ingest(self.snap(680, None), now=4)
        self.e.saved_squad = Mock(return_value=native_role(native(540, 'first'), '680'))
        runner = Mock()
        self.e.run_one(runner)
        runner.assert_not_called()
        job = self.e.jobs()[0]
        self.assertEqual(job['status'], 'blocked')
        self.assertIn('새 구단 선수단 등록 대기', job['note'])
        self.e.ingest(self.snap(680, 540), now=5)
        self.enable_save_backend()
        self.e.retry_preflight()
        self.assertIsNotNone(self.e.next_job(time.time()))
        self.assertEqual(self.e.jobs()[0]['id'], job['id'])
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_unrelated_historical_club_cannot_classify_an_unknown_departure(self):
        self.c['scope_rules']['clubs'] = {'700': 'outgoing'}
        self.e.ingest(self.snap(700, None), now=3)
        self.e.ingest(self.snap(None, None), now=4)
        self.e.ingest(self.snap(680, 540), now=5)
        events = [json.loads(job['data']) for job in self.e.jobs()]
        self.assertFalse(any(event['from_club_id'] == '700' for event in events))
        self.assertEqual(json.loads(self.e.meta('detection_summary'))['queued'], 0)

    def test_registration_history_survives_restart_without_carrying_to_reused_identity(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        self.e.ingest(self.snap(602, None), now=3)
        self.e.close()
        self.e = Engine(self.c)
        self.addCleanup(self.e.close)
        self.e.refresh = lambda: 0
        self.e.ingest(self.snap(None, None), now=4)
        self.e.ingest(self.snap(680, 540), now=5)
        event = json.loads(self.e.db.execute('SELECT data FROM jobs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(event['from_team_id'], 900)
        replacement = self.snap(680, None)
        replacement['players'][0]['identity'] = 'different-person'
        self.e.ingest(replacement, now=6)
        person = json.loads(self.e.db.execute('SELECT data FROM people').fetchone()[0])
        self.assertNotIn('last_squad_registration', person)

    def test_existing_unstarted_missing_departure_is_hidden_without_erasing_history(self):
        job = self.e.jobs()[0]
        row = json.loads(job['data'])
        row['from_team_id'] = None
        with self.e.db:
            self.e.db.execute("UPDATE jobs SET data=?,status='blocked' WHERE id=?", (json.dumps(row), job['id']))
        self.e.close()
        self.e = Engine(self.c)
        self.addCleanup(self.e.close)
        self.assertEqual(self.e.jobs(), [])
        saved = self.e.db.execute('SELECT status,data FROM jobs WHERE id=?', (job['id'],)).fetchone()
        self.assertEqual(saved['status'], 'deleted')
        self.assertEqual(json.loads(saved['data']), row)
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_missing_departure_does_not_hide_paid_or_editing_jobs(self):
        job = self.e.jobs()[0]
        row = json.loads(job['data'])
        row['from_team_id'] = None
        with self.e.db:
            self.e.db.execute("UPDATE jobs SET data=?,status='blocked',started=10 WHERE id=?", (json.dumps(row), job['id']))
        self.e.discard_missing_departures()
        self.assertEqual(self.e.jobs()[0]['status'], 'blocked')
        with self.e.db:
            self.e.db.execute('UPDATE jobs SET started=NULL WHERE id=?', (job['id'],))
            self.e.db.execute('INSERT INTO job_custom(job_id,editing) VALUES (?,1)', (job['id'],))
        self.e.discard_missing_departures()
        self.assertEqual(self.e.jobs()[0]['status'], 'blocked')

    def test_selected_incoming_side_can_still_run_without_departure_history(self):
        job = self.e.jobs()[0]
        row = json.loads(job['data'])
        row['from_team_id'] = None
        self.c['scope_rules']['clubs'] = {'680': 'outgoing', '602': 'incoming'}
        with self.e.db:
            self.e.db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(row), job['id']))
        self.e.saved_squad=Mock(return_value=native_role(native(900, 'first', 602), '602'))
        self.e.discard_missing_departures()
        self.assertIsNotNone(self.e.next_job(time.time()))
        self.assertEqual(json.loads(self.e.jobs()[0]['data'])['squad_evidence']['incoming']['kind'], 'first')

    def test_all_squads_include_missing_departures_without_native_queries(self):
        self.c['scope_rules']['squad_types'] = ['first', 'reserve', 'youth']
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        with self.e.db:
            self.e.db.execute('DELETE FROM people')
        self.e.ingest(self.snap(602, None), now=3)
        self.e.ingest(self.snap(None, None), now=4)
        self.assertEqual(self.e.ingest(self.snap(680, 540), now=5), 1)
        self.e.discard_missing_departures()
        self.assertTrue(any(job['status'] == 'pending' for job in self.e.jobs()))

    def test_save_in_progress_does_not_end_an_unstarted_job(self):
        from engine import SaveBusyError
        self.e.refresh = Mock(side_effect=SaveBusyError('세이브 저장 중'))
        runner = Mock()
        self.assertFalse(self.e.run_one(runner))
        self.assertTrue(self.e.waiting_for_game)
        self.assertEqual(self.e.jobs()[0]['status'], 'pending')
        runner.assert_not_called()
