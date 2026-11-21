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
from team_reader import TeamReadPending


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

    def test_queue_retains_both_event_sides_and_native_filter_runs_before_codex(self):
        job=self.e.db.execute('SELECT * FROM jobs').fetchone()
        self.assertEqual(json.loads(job['data'])['from_team_id'],540)
        self.e._team_reader.resolve=Mock(return_value={540:native(540,'first')})
        self.assertIsNotNone(self.e.next_job(time.time()))
        row=json.loads(self.e.jobs()[0]['data'])
        self.assertEqual(row['squad_evidence']['outgoing']['kind'],'first')
        self.e._team_reader.resolve=Mock(return_value={540:native(540,'youth')})
        self.assertIsNone(self.e.next_job(time.time()))
        self.assertEqual(self.e.jobs()[0]['status'],'superseded')
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)

    def test_unavailable_native_bridge_blocks_and_recovers_without_ai_retry(self):
        self.e._team_reader.resolve=Mock(side_effect=TeamReadPending('연결 대기'))
        runner=Mock()
        self.assertFalse(self.e.run_one(runner))
        runner.assert_not_called()
        self.assertEqual(self.e.jobs()[0]['status'],'blocked')
        self.e.retry_preflight()
        self.e._team_reader.resolve=Mock(return_value={540:native(540,'first')})
        self.assertIsNotNone(self.e.next_job(time.time()))

    def test_unknown_scope_cannot_apply_an_already_paid_image(self):
        job=self.e.jobs()[0]
        self.e.update(job['id'],'generated')
        self.e._team_reader.resolve=Mock(side_effect=TeamReadPending('연결 대기'))
        with self.assertRaises(TeamReadPending): self.e.apply(job['id'])
        self.assertEqual(self.e.jobs()[0]['status'],'generated')

    def test_all_squad_types_never_need_plugin(self):
        self.c['scope_rules']['squad_types']=['first','reserve','youth']
        self.e._team_reader.resolve=Mock(side_effect=AssertionError('No native lookup'))
        self.assertIsNotNone(self.e.next_job(time.time()))
        self.e._team_reader.resolve.assert_not_called()

    def test_contract_only_arrival_is_unknown_and_never_inferred_as_first_team(self):
        self.c['scope_rules']['clubs']={'602':'incoming'}
        person=json.loads(self.e.db.execute('SELECT data FROM people').fetchone()[0])
        person.update(registered_club_id='680',registered_team_id=540,club_basis='contract_change')
        with self.e.db:
            self.e.db.execute('UPDATE people SET data=?',(json.dumps(person),))
        self.e._team_reader.resolve=Mock(side_effect=AssertionError('Cannot query old registration as destination'))
        self.assertIsNone(self.e.next_job(time.time()))
        self.e._team_reader.resolve.assert_not_called()
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
        self.e._team_reader.resolve = Mock(return_value={900: native(900, 'reserve', 602)})
        self.assertEqual(self.e.enrich_squads(job)['squad_evidence']['outgoing']['kind'], 'reserve')

    def test_departure_keeps_most_recent_valid_squad_assignment(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        self.e.ingest(self.snap(602, 901), now=3)
        self.e.ingest(self.snap(602, None), now=4)
        self.e.ingest(self.snap(None, None), now=5)
        self.e.ingest(self.snap(680, 540), now=6)
        event = json.loads(self.e.db.execute('SELECT data FROM jobs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertEqual(event['from_team_id'], 901)

    def test_missing_registration_stays_unknown_without_historical_evidence(self):
        self.c['scope_rules']['clubs'] = {'602': 'outgoing'}
        with self.e.db:
            self.e.db.execute('DELETE FROM people')
        self.e.ingest(self.snap(602, None), now=3)
        self.e.ingest(self.snap(None, None), now=4)
        self.e.ingest(self.snap(680, 540), now=5)
        job = self.e.db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
        self.e._team_reader.resolve = Mock(side_effect=AssertionError('Missing registration'))
        row = self.e.enrich_squads(job)
        self.assertIn('방출 전 선수단 기록 없음', row['squad_evidence']['outgoing']['reason'])
        self.e._team_reader.resolve.assert_not_called()

    def test_free_agent_arrival_waits_for_new_team_then_recovers_existing_job(self):
        self.c['scope_rules']['clubs'] = {'680': 'incoming'}
        self.e.ingest(self.snap(None, None), now=3)
        self.e.ingest(self.snap(680, None), now=4)
        self.e._team_reader.resolve = Mock(return_value={540: native(540, 'first')})
        runner = Mock()
        self.e.run_one(runner)
        runner.assert_not_called()
        job = self.e.jobs()[0]
        self.assertEqual(job['status'], 'blocked')
        self.assertIn('새 구단 선수단 등록 대기', job['note'])
        self.e.ingest(self.snap(680, 540), now=5)
        self.e.retry_preflight()
        self.assertIsNotNone(self.e.next_job(time.time()))
        self.assertEqual(self.e.jobs()[0]['id'], job['id'])
        self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_unrelated_historical_club_cannot_classify_an_unknown_departure(self):
        self.c['scope_rules']['clubs'] = {'700': 'outgoing'}
        self.e.ingest(self.snap(700, None), now=3)
        self.e.ingest(self.snap(None, None), now=4)
        self.e.ingest(self.snap(680, 540), now=5)
        event = json.loads(self.e.db.execute('SELECT data FROM jobs ORDER BY id DESC LIMIT 1').fetchone()[0])
        self.assertIsNone(event['from_team_id'])
        self.assertEqual(event['from_registered_club_id'], '700')

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
