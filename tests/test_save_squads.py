import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from PIL import Image, PngImagePlugin

from engine import DEFAULTS, Engine, detection_messages, file_stamp, normalise
from save_teams import BUILD, SUPPORTED_BUILDS, VERSION, read_roles, roles_from_table
from scope_rules import DEFAULT_SCOPE
from gunzo import LAYOUT


def role(index, club, kind, build=BUILD):
    return dict(source='save', build=build, registered_team_id=index, club_id=str(club),
                team_unique_id=800 + index, kind=kind)


class SaveRoleDecoderTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(team_id=i, unique_id=uid, raw_type=typ, raw_flags=flags, raw_national=0)
                for i, uid, typ, flags in ((0, 500, 0, 0), (1, 801, 10, 16),
                                           (2, 802, 12, 16), (3, 501, 0, 0))]
        clubs = {40: dict(id=500, teams=[
            dict(team_id=i, club_uid=40 if i < 3 else 41, is_affiliate=i == 3) for i in range(4)]),
                 41: dict(id=501, teams=[dict(team_id=3, club_uid=41, is_affiliate=False)])}
        return clubs, rows

    def test_same_validated_relations_classify_own_teams_and_keep_controlled_owner(self):
        clubs, rows = self.fixture()
        result = roles_from_table(clubs, rows)
        self.assertEqual([result[str(i)]['kind'] for i in range(4)], ['first', 'reserve', 'youth', 'first'])
        self.assertEqual(result['3']['club_id'], '501')
        self.assertTrue(all(r['source'] == 'save' for r in result.values()))

    def test_both_supported_builds_use_same_rules_and_preserve_actual_build(self):
        clubs, rows = self.fixture()
        for build in SUPPORTED_BUILDS:
            with self.subTest(build=build):
                result = roles_from_table(clubs, rows, build)
                self.assertEqual([result[str(i)]['kind'] for i in range(4)],
                                 ['first', 'reserve', 'youth', 'first'])
                self.assertTrue(all(r['build'] == build for r in result.values()))
                _, status = read_roles(NS(info=NS(build=build)), {})
                self.assertEqual(status['build'], build)
                self.assertIn('error', status)
        with self.assertRaises(ValueError):
            roles_from_table(clubs, rows, '27.1.2+9999999')

    def test_unknown_sibling_holds_reference_based_roles_but_does_not_erase_verified_first_team(self):
        for change in ({'raw_type': 255}, {'raw_flags': 64}, {'unique_id': 999}):
            clubs, rows = self.fixture()
            index = 0 if 'unique_id' in change else 1
            rows[index].update(change)
            result = roles_from_table(clubs, rows)
            self.assertTrue(all(result[str(i)]['kind'] == 'unknown' for i in (1, 2)))
            self.assertEqual(result['0']['kind'], 'unknown' if 'unique_id' in change else 'first')
            self.assertEqual(result['3']['kind'], 'first')

    def test_supported_decode_failure_is_held_without_native_fallback(self):
        source = NS(info=NS(build=BUILD))
        roles, status = read_roles(source, {})
        self.assertEqual(roles, {})
        self.assertEqual(status['mode'], 'save')
        self.assertIn('error', status)
        source.info.build = '27.0.0+2486695'
        roles, status = read_roles(source, {})
        self.assertEqual(status['mode'], 'save')
        self.assertIn('미지원', status['error'])

    def test_unverified_fourth_participating_subteam_does_not_gain_a_youth_label(self):
        clubs, rows = self.fixture()
        rows.append(dict(team_id=4, unique_id=804, raw_type=11, raw_flags=16, raw_national=0))
        clubs[40]['teams'].append(dict(team_id=4, club_uid=40, is_affiliate=False))
        result = roles_from_table(clubs, rows)
        self.assertEqual(result['0']['kind'], 'first')
        self.assertEqual(result['1']['kind'], 'unknown')
        self.assertEqual(result['4']['kind'], 'unknown')


class SaveSquadEngineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update(source=str(self.root / 'career.fm'), state_dir=str(self.root / 'state'))
        self.c['scope_rules'] = copy.deepcopy(DEFAULT_SCOPE)
        self.c['scope_rules'].update(preset='custom', clubs={'500': 'outgoing'}, squad_types=['reserve'])
        self.engine = Engine(self.c)
        self.addCleanup(self.engine.db.close)
        self.engine.refresh = lambda: 0
        self.counter = 0

    def ingest(self, club, team, old_kind='reserve', *, error=None, build=BUILD):
        self.counter += 1
        Path(self.c['source']).write_bytes(b'fixture' * self.counter)
        status = dict(mode='save', build=build, version=VERSION)
        if error:
            status['error'] = error
        payload = normalise({'players': [dict(id=1, uid=10, name='Alex Example', club_id=club,
            registered_club_id=str(club) if club else '', registered_team_id=team)],
            'managed_club_ids': ['500'], 'source_stamp': list(file_stamp(self.c['source'])),
            'squad_status': status, 'save_squads': {} if error else {
                '1': role(1, 500, old_kind, build), '3': role(3, 501, 'first', build)}})
        return self.engine.ingest(payload, now=self.counter)

    def job(self):
        return self.engine.db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id DESC LIMIT 1").fetchone()

    def test_departure_preserves_previous_snapshot_role_when_current_refs_change(self):
        self.ingest(500, 1)
        self.ingest(501, 3, old_kind='youth')
        row = self.engine.enrich_squads(self.job())
        self.assertEqual(row['squad_evidence']['outgoing']['kind'], 'reserve')
        self.assertEqual(self.engine.saved_squad(1, '500')['kind'], 'youth')

    def test_free_agent_gap_preserves_old_role_and_new_arrival_uses_destination(self):
        self.ingest(500, 1)
        self.ingest(None, None, old_kind='youth')
        self.ingest(None, None, old_kind='first')
        self.ingest(501, 3, old_kind='youth')
        row = self.engine.enrich_squads(self.job())
        self.assertEqual(row['from_team_id'], 1)
        self.assertEqual(row['squad_evidence']['outgoing']['kind'], 'reserve')
        self.c['scope_rules'].update(clubs={'501': 'incoming'}, squad_types=['first'])
        row = self.engine.enrich_squads(self.job())
        self.assertEqual(row['squad_evidence']['incoming']['kind'], 'first')

    def test_patch_upgrade_keeps_old_departure_evidence_and_new_snapshot_build(self):
        self.ingest(500, 1, build=BUILD)
        self.ingest(501, 3, build='27.1.1+2511875')
        self.assertTrue(self.engine.save_squad_backend())
        self.assertEqual(self.engine.saved_squad(3, '501')['build'], '27.1.1+2511875')
        row = self.engine.enrich_squads(self.job())
        self.assertEqual(row['squad_evidence']['outgoing']['kind'], 'reserve')
        self.assertEqual(row['squad_evidence']['outgoing']['build'], BUILD)
        self.assertIsNotNone(self.engine.next_job(1000))
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)
        reopened = Engine(self.c)
        self.addCleanup(reopened.close)
        self.assertTrue(reopened.save_squad_backend())
        self.assertEqual(reopened.enrich_squads(self.job(), reuse=True)['squad_evidence']['outgoing']['build'], BUILD)

    def test_unknown_save_structure_blocks_ai_and_does_not_use_dll(self):
        self.ingest(500, 1, error='unsupported team structure')
        self.ingest(501, 3, error='unsupported team structure')
        runner = Mock()
        self.assertFalse(self.engine.run_one(runner))
        runner.assert_not_called()
        self.assertEqual(self.engine.jobs()[0]['status'], 'blocked')

    def test_unsupported_save_blocks_without_connection_wait_or_ai(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        self.engine.setmeta('squad_status', json.dumps(dict(mode='save', version=VERSION,
            build='27.0.0+2486695', error='세이브 팀 구분 미지원 빌드')))
        runner = Mock()
        self.assertFalse(self.engine.run_one(runner))
        runner.assert_not_called()
        self.assertFalse(self.engine.waiting_for_game)
        self.assertEqual(self.engine.jobs()[0]['status'], 'blocked')
        self.assertIn('미지원', self.engine.jobs()[0]['note'])
        self.assertFalse(hasattr(self.engine, '_team_reader'))

    def test_save_proof_reuses_without_game_or_second_team_lookup_and_survives_restart(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        self.engine.enrich_squads(self.job())
        reopened = Engine(self.c)
        self.addCleanup(reopened.db.close)
        reopened.saved_squad = Mock(side_effect=AssertionError('Saved proof should be reused'))
        row = reopened.enrich_squads(self.job(), reuse=True)
        self.assertEqual(row['squad_evidence']['outgoing']['kind'], 'reserve')

    def test_scope_and_registration_changes_invalidate_saved_proof(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        self.c['scope_rules'].update(clubs={'501': 'incoming'}, squad_types=['first'])
        row = self.engine.enrich_squads(self.job())
        self.assertTrue(self.engine.reuse_squad_proof(row))
        self.c['scope_rules']['squad_types'] = ['youth']
        self.assertFalse(self.engine.reuse_squad_proof(row))
        self.c['scope_rules']['squad_types'] = ['first']
        person = json.loads(self.engine.db.execute('SELECT data FROM people').fetchone()[0])
        person['registered_team_id'] = 1
        self.engine.db.execute('UPDATE people SET data=?', (json.dumps(person),))
        changed = self.engine.enrich_squads(self.job(), reuse=True)
        self.assertEqual(changed['squad_evidence']['incoming']['kind'], 'unknown')
        self.assertNotIn('squad_proof', changed)

    def test_old_native_context_cannot_authorize_reusing_evidence(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        row = self.engine.enrich_squads(self.job())
        row['squad_proof']['context'] = {'session': 'a' * 32, 'generation': 1}
        self.engine.db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(row), self.job()['id']))
        self.assertFalse(self.engine.reuse_squad_proof(row))
        self.assertEqual(self.engine.enrich_squads(self.job(), reuse=True)['squad_proof']['context'],
                         {'source': 'save', 'version': VERSION})

    def test_save_change_holds_before_ai_instead_of_accepting_old_proof(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        self.engine.enrich_squads(self.job())
        Path(self.c['source']).write_bytes(b'new save still being written')
        runner = Mock()
        self.assertFalse(self.engine.run_one(runner))
        runner.assert_not_called()
        self.assertTrue(self.engine.waiting_for_game)

    def test_existing_generated_image_applies_without_game_or_paid_recall_and_keeps_other_mappings(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        job = self.job()
        self.engine.enrich_squads(job)
        artifact = self.root / 'already-rendered.png'
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Layout', LAYOUT)
        metadata.add_text('PlayerName', 'Alex Example')
        Image.new('RGBA', (350, 350), 'purple').save(artifact, pnginfo=metadata)
        pack = self.root / 'pack'
        pack.mkdir()
        (pack / '77.png').write_bytes(b'unrelated original image')
        (pack / 'config.xml').write_bytes(self.engine.mapping_xml({'77': '77'}))
        self.c['pack_dir'] = str(pack)
        self.engine.update(job['id'], 'generated', artifact=str(artifact))
        self.engine.render_paid_result = Mock(side_effect=AssertionError('Reuse rendered artifact'))
        self.c['live_refresh_enabled'] = True
        with patch('live_refresh.bridge_root', return_value=self.root / 'closed-game-bridge'):
            self.engine.apply(job['id'])
        self.assertFalse(self.engine.waiting_for_game)
        self.assertIn('연결 대기', self.engine.meta('live_refresh_status'))
        self.assertEqual((pack / '1.png').read_bytes(), artifact.read_bytes())
        self.assertEqual((pack / '77.png').read_bytes(), b'unrelated original image')
        self.assertEqual(self.engine.pack_mapping((pack / 'config.xml').read_bytes()), {'1': '1', '77': '77'})
        self.assertEqual(self.engine.jobs()[0]['status'], 'applied')
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_controlled_team_owner_mismatch_does_not_become_parent_first_team(self):
        self.ingest(500, 1)
        self.ingest(501, 1)
        self.c['scope_rules'].update(clubs={'501': 'incoming'}, squad_types=['first'])
        row = self.engine.enrich_squads(self.job())
        self.assertEqual(row['squad_evidence']['incoming']['kind'], 'unknown')

    def test_wrong_frozen_owner_version_or_index_cannot_authorize_generation(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        original = json.loads(self.job()['data'])
        for change in ({'club_id': '501'}, {'reader_version': 'unverified'},
                       {'registered_team_id': True}, {'kind': ['first']},
                       {'build': '27.1.2+9999999'}, {'build': ['invalid']}):
            with self.subTest(change=change):
                data = copy.deepcopy(original)
                data['from_squad_role'].update(change)
                self.engine.db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), self.job()['id']))
                row = self.engine.enrich_squads(self.job())
                self.assertEqual(row['squad_evidence']['outgoing']['kind'], 'unknown')

    def test_existing_game_wait_resumes_after_save_backend_migration_without_game_query(self):
        self.ingest(500, 1)
        self.ingest(501, 3)
        snapshot = normalise({'players': [dict(id=1, uid=10, name='Alex Example', club_id=501,
            registered_club_id='501', registered_team_id=3)], 'managed_club_ids': ['500'],
            'source_stamp': list(file_stamp(self.c['source'])), 'squad_status': dict(mode='save', build=BUILD, version=VERSION),
            'save_squads': {'1': role(1, 500, 'reserve'), '3': role(3, 501, 'first')}})
        self.engine.setmeta('squad_status', json.dumps(dict(mode='native', version=VERSION,
            build=BUILD, source_stamp=list(file_stamp(self.c['source'])))))
        self.engine.wait_for_game(self.job()['id'], 'pending', '기존 DLL 게임 진행 대기')
        self.assertTrue(json.loads(self.job()['data'])['game_wait'])
        before = len(self.engine.jobs())
        with patch('engine.read_source', return_value=snapshot) as read:
            Engine.refresh(self.engine)
            Engine.refresh(self.engine)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(len(self.engine.jobs()), before)
        resumed = self.engine.next_job(1000)
        self.assertIsNotNone(resumed)
        self.assertNotIn('game_wait', json.loads(resumed['data']))

    def test_malformed_optional_status_does_not_break_legacy_snapshot_ingestion(self):
        Path(self.c['source']).write_bytes(b'fixture')
        snapshot = normalise({'players': [dict(id=1, club_id=500)],
                              'source_stamp': list(file_stamp(self.c['source'])), 'squad_status': 'invalid'})
        self.engine.ingest(snapshot)
        self.assertEqual(json.loads(self.engine.meta('squad_status')), {})
        self.assertTrue(detection_messages(json.loads(self.engine.meta('detection_summary'))))

    def test_team_table_stamp_must_match_baseline_even_if_an_older_writer_updated_it(self):
        self.ingest(500, 1)
        Path(self.c['source']).write_bytes(b'changed by an older application')
        new_stamp = list(file_stamp(self.c['source']))
        self.engine.setmeta('source_stamp', json.dumps(new_stamp))
        self.assertEqual(self.engine.saved_squad(1, '500')['kind'], 'unknown')
        fresh = normalise({'players': [dict(id=1, uid=10, club_id=500,
                           registered_club_id='500', registered_team_id=1)],
            'source_stamp': new_stamp, 'squad_status': dict(mode='save', version=VERSION, build=BUILD),
            'save_squads': {'1': role(1, 500, 'reserve')}})
        with patch('engine.read_source', return_value=fresh) as read:
            Engine.refresh(self.engine)
        read.assert_called_once()
        self.assertEqual(self.engine.saved_squad(1, '500')['kind'], 'reserve')


if __name__ == '__main__':
    unittest.main()
