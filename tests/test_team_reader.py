import json
from pathlib import Path
import tempfile
import unittest

from live_refresh import write_json
from team_reader import PROFILE,VERSION,TeamReader,TeamReadPending


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.now=1000.
        self.sid='a'*32;self.dir=self.root/'sessions'/('123-'+self.sid)
        self.status=dict(protocol=1,profile=PROFILE,plugin_version=VERSION,session=self.sid,pid=123,epoch=2,
                         heartbeat=self.now,available=True,idle=True,binding_ready=True,human_team_index=540)
        self.save_status(); self.requests=[]
        self.reader=TeamReader(self.root,clock=lambda:self.now,sleep=self.respond)

    def save_status(self):
        self.status['heartbeat']=self.now
        write_json(self.dir/'status.json',self.status)

    def respond(self, seconds):
        self.now+=seconds;self.save_status()
        for file in (self.root/'requests'/self.sid).glob('*.json'):
            req=json.loads(file.read_text());self.requests.append(req)
            rows=[{'native_team_index':i,'values':{'Club.UniqueId':{'scalar':680}},'error':None,'cleanup_error':None} for i in req['teams']]
            reply={k:req[k] for k in ('protocol','id','session','profile','epoch','snapshot')}
            write_json(self.dir/'responses'/(req['id']+'.json'),reply|{'status':'complete','results':rows})

    def test_request_is_bounded_session_scoped_cached_and_cleaned(self):
        got=self.reader.resolve([28346,28347],['680'],'b'*64)
        self.assertEqual(set(got),{28346,28347})
        self.assertEqual(self.requests[0]['teams'],[540,28346,28347])
        self.reader.resolve([28346],['680'],'b'*64)
        self.assertEqual(len(self.requests),1)
        self.assertFalse(list((self.root/'requests'/self.sid).glob('*.json')))
        self.status['epoch']=3;self.save_status()
        self.reader.resolve([28346],['680'],'b'*64)
        self.assertEqual(len(self.requests),2)

    def test_wrong_loaded_club_or_stale_game_never_returns_roles(self):
        with self.assertRaises(TeamReadPending):self.reader.resolve([540],['602'],'b'*64)
        self.now+=10
        with self.assertRaises(TeamReadPending):self.reader.resolve([540],[],'b'*64)

    def test_mismatched_response_and_cancel_cannot_reuse_previous_result(self):
        def wrong(seconds):
            self.respond(seconds)
            for f in (self.dir/'responses').glob('*.json'):
                r=json.loads(f.read_text());r['snapshot']='c'*64;write_json(f,r)
        self.reader.sleep=wrong
        with self.assertRaises(TeamReadPending):self.reader.resolve([540],[],'b'*64)
        self.assertFalse(self.reader.cache)
        class Cancel:
            def is_set(self):return True
        with self.assertRaises(TeamReadPending):self.reader.resolve([540],[],'b'*64,Cancel())
        self.assertFalse(list((self.root/'requests'/self.sid).glob('*.json')))

    def test_busy_game_is_a_resumable_wait_and_not_a_permanent_connection_error(self):
        from team_reader import GameWait
        self.status['idle'] = False
        self.save_status()
        with self.assertRaises(GameWait):
            self.reader.resolve([540], ['680'], 'b'*64)
        self.assertEqual(self.requests, [])
        self.status['idle'] = True
        self.save_status()
        self.assertIn(540, self.reader.resolve([540], ['680'], 'b'*64))

    def test_partially_completed_batch_cancelled_by_progress_is_resumable(self):
        from team_reader import GameWait
        def busy(seconds):
            self.respond(seconds)
            for path in (self.dir/'responses').glob('*.json'):
                result=json.loads(path.read_text())
                result['status']='unavailable'
                result['results'][-1]['error']='request_expired_cancelled_or_game_changed'
                write_json(path,result)
        self.reader.sleep=busy
        with self.assertRaises(GameWait):
            self.reader.resolve([28346], ['680'], 'b'*64)
        self.assertEqual(self.reader.cache,{})
        self.assertFalse(list((self.root/'requests'/self.sid).glob('*.json')))
        self.reader.sleep=self.respond
        self.assertIn(28346,self.reader.resolve([28346], ['680'], 'b'*64))

    def test_stale_heartbeat_waits_without_authorizing_a_query_or_cached_result(self):
        from team_reader import GameWait
        self.reader.resolve([540], ['680'], 'b'*64)
        requests = len(self.requests)
        self.now += 10
        with self.assertRaises(GameWait):
            self.reader.resolve([540], ['680'], 'b'*64)
        self.assertEqual(len(self.requests), requests)
        self.save_status()
        self.assertIn(540, self.reader.resolve([540], ['680'], 'b'*64))

    def test_completed_classification_context_can_be_checked_while_game_is_busy(self):
        self.status['context_epoch'] = 7
        self.save_status()
        self.reader.resolve([540], ['680'], 'b'*64)
        verified = self.reader.last_context
        requests = len(self.requests)
        self.status.update(idle=False, binding_ready=False, epoch=3, reason='game_processing')
        self.save_status()
        self.assertEqual(self.reader.current_context(), verified)
        self.assertEqual(len(self.requests), requests)
        self.status['context_epoch'] = 8
        self.save_status()
        self.assertNotEqual(self.reader.current_context(), verified)

    def test_old_plugin_context_uses_strict_query_epoch(self):
        self.reader.resolve([540], ['680'], 'b'*64)
        context = self.reader.last_context
        self.status['epoch'] += 1
        self.save_status()
        self.assertNotEqual(self.reader.current_context(), context)
