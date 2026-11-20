import contextlib
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

from squad_diagnostics import compare, extract, read_snapshot


class SquadDiagnosticsTests(unittest.TestCase):
    def save(self, team_id=100, slot=0, players=True):
        player = NS(unique_id=2000256110,name='Shea Lacey',team_id=team_id,team_slot=slot,
                    club_uid=7,club_name='Manchester United',team_club_uid=None,team_club_name=None,on_loan=False,
                    contract=NS(team_id=100,club_uid=7,club_name='Manchester United',kind=NS(raw=3,label_text='youth'),squad_status=None))
        club = NS(uid=7,unique_id=680,name='Manchester United',teams=tuple(NS(team_id=value,slot=index,club_uid=7,is_affiliate=False)
                          for index,value in enumerate((100,101,102))))
        return NS(info=NS(game='FM27',build='27.1.0+2505117',known_build=False,game_date='2028-06-09'),
                  clubs=lambda:[club],players=lambda:[player] if players else [])

    def test_comparison_keeps_club_identity_separate_from_changed_team_slots(self):
        snapshots = [extract(self.save(team,slot),('2000256110',)) | {'file':name}
                     for team,slot,name in ((100,0,'first.fm'),(101,1,'reserve.fm'),(102,2,'youth.fm'))]
        result=compare(snapshots,('2000256110',))[0]
        self.assertTrue(result['complete'])
        self.assertEqual(result['changed_fields'],['team_id','team_slot'])
        self.assertTrue(all(row['club_id']==680 for row in result['values_by_save']))
        self.assertEqual(snapshots[0]['clubs'][0]['teams'][2]['team_id'],102)

    def test_reading_opens_a_strict_temporary_copy_and_leaves_original_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'first.fm'
            original=b'original save contents'
            source.write_bytes(original)
            opened=[]
            @contextlib.contextmanager
            def opener(path,strict):
                self.assertTrue(strict)
                self.assertNotEqual(path,source)
                self.assertEqual(path.read_bytes(),original)
                opened.append(path)
                yield self.save()
            result=read_snapshot(source,('2000256110',),opener)
            self.assertEqual(result['players'][0]['team_slot'],0)
            self.assertEqual(source.read_bytes(),original)
            self.assertFalse(opened[0].exists())

    def test_missing_or_failed_snapshot_cannot_claim_a_complete_comparison(self):
        snapshots=[extract(self.save(players=False),('2000256110',)) | {'file':'empty.fm'},
                   extract(self.save(),('2000256110',)) | {'file':'first.fm'},
                   {'file':'failed.fm','error':'read failed'}]
        result=compare(snapshots,('2000256110',))[0]
        self.assertFalse(result['complete'])
        self.assertEqual(result['changed_fields'],[])
        self.assertEqual(snapshots[0]['missing_player_ids'],['2000256110'])
