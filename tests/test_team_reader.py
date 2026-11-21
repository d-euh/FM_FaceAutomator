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
