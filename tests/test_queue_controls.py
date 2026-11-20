import copy
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from engine import DEFAULTS, Engine, SAVE_BUSY_NOTES, SaveBusyError, normalise, process_lock, read_source, write_atomic
from gunzo import bundled_font_path
from player_catalog import find_players


class QueueControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = copy.deepcopy(DEFAULTS) | {key: str(self.root / key) for key in ('state_dir','pack_dir','portraits_dir','kits_dir')}
        self.c.update(source=str(self.root / 'career.json'), all_players=True, my_club_only=False,
                      name_font_path=str(bundled_font_path('koverwatch.ttf')), codex=shutil.which('python3') or shutil.which('python'))
        self.engine = Engine(self.c)
        self.addCleanup(lambda: self.engine.close())
        def snapshot(club):
            return normalise({'players': [dict(id=str(i), uid=i, name=name, english_name=english,
                    club_id=club, club_name='아스날' if club == '20' else '맨체스터 유나이티드')
                for i, name, english in ((1, '제드 스펜스', 'Djed Spence'), (2, 'Bruno Fernandes', 'Bruno Fernandes'), (3, '알바로', 'Álvaro'))]})
        self.engine.ingest(snapshot('10'))
        write_atomic(self.c['source'], json.dumps(snapshot('20'), ensure_ascii=False).encode())
        self.engine.ingest(read_source(self.c))
        for key, files in (('portraits_dir', ['1.png','2.png','3.png']), ('kits_dir',['20.png'])):
            Path(self.c[key]).mkdir()
            for file in files:
                Image.new('RGB', (512,512), 'gray').save(Path(self.c[key]) / file)
        self.calls = []

    def runner(self, cmd, **kwargs):
        folder = Path(cmd[cmd.index('--cd') + 1])
        self.calls.append(int(folder.name.split('-')[0]))
        Image.new('RGB', (512,512), 'gray').save(folder / 'portrait.png')
        (folder / 'reply.json').write_text(json.dumps({'status':'generated','reason':'ok','english_name':'Djed Spence'}))
        return SimpleNamespace(returncode=0)

    def test_reordering_changes_actual_next_job_and_survives_restart(self):
        e = self.engine
        self.assertTrue(e.reorder_job(3, 'first'))
        self.assertEqual([j['id'] for j in e.jobs()], [3,1,2])
        self.assertEqual(e.next_job(time.time())['id'], 3)
        self.assertTrue(e.reorder_job(3, 'down'))
        self.assertEqual(e.next_job(time.time())['id'], 1)
        self.assertTrue(e.reorder_job(2, 'up'))
        self.assertEqual([j['id'] for j in e.jobs()], [1,2,3])
        other = Engine(self.c)
        try:
            self.assertEqual([j['id'] for j in other.jobs()], [1,2,3])
        finally:
            other.close()

    def test_priority_change_during_preflight_prevents_charging_the_old_candidate(self):
        e = self.engine
        original = e.kit_reference
        def reorder(club, row):
            other = Engine(self.c)
            try:
                other.reorder_job(3, 'first')
            finally:
                other.close()
            return original(club, row)
        with patch.object(e, 'kit_reference', side_effect=reorder):
            self.assertFalse(e.run_one(self.runner))
        self.assertEqual(self.calls, [])
        e.run_one(self.runner)
        self.assertEqual(self.calls, [3])

    def test_removal_preserves_saved_pack_and_attempt_accounting(self):
        e = self.engine
        e.run_one(self.runner, job_id=1)
        xml = Path(self.c['pack_dir']) / 'config.xml'
        portrait = xml.with_name('1.png')
        before = (xml.read_bytes(), portrait.read_bytes())
        self.assertTrue(e.remove_job(1))
        self.assertNotIn(1, [j['id'] for j in e.jobs()])
        self.assertEqual((xml.read_bytes(),portrait.read_bytes()), before)
        self.assertEqual(e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)
        self.assertFalse(e.retry(1))
        self.assertFalse(e.reorder_job(1, 'first'))
        self.assertFalse(e.remove_job(1))

    def test_deleting_pending_candidate_never_calls_ai_or_reuses_its_id(self):
        e = self.engine
        self.assertTrue(e.remove_job(1))
        self.assertFalse(e.run_one(self.runner, job_id=1))
        self.assertEqual(self.calls, [])
        self.assertEqual(e.enqueue_current(), 1)
        self.assertEqual(e.db.execute('SELECT max(id) FROM jobs').fetchone()[0], 4)

    def test_running_and_editing_jobs_are_protected_from_controls(self):
        e = self.engine
        e.update(1, 'running')
        with self.assertRaises(ValueError):
            e.remove_job(1)
        self.assertFalse(e.retry(1))
        self.assertFalse(e.reorder_job(1, 'first'))
        e.update(2, 'failed')
        e.begin_job_edit(2)
        with self.assertRaises(ValueError):
            e.remove_job(2)
        self.assertFalse(e.retry(2))
        self.assertNotIn(2, e.retry_all())

    def test_failed_application_cannot_be_deleted_while_worker_owns_it(self):
        e = self.engine
        e.update(1, 'apply_failed')
        with process_lock(Path(self.c['state_dir'])):
            with self.assertRaisesRegex(ValueError, '멈춘 뒤'):
                e.remove_job(1)
        self.assertTrue(e.remove_job(1))

    def test_selected_retry_does_not_run_other_pending_or_failed_jobs(self):
        e = self.engine
        e.update(1, 'failed')
        e.update(3, 'failed')
        self.assertTrue(e.retry(3))
        e.run_one(self.runner, job_id=3)
        self.assertEqual(self.calls, [3])
        statuses = {row['id']: row['status'] for row in e.jobs()}
        self.assertEqual(statuses, {1:'failed',2:'pending',3:'applied'})

    def test_retry_all_skips_successes_and_reuses_rendered_images(self):
        e = self.engine
        e.run_one(self.runner, job_id=3)
        with patch.object(e, 'apply', side_effect=OSError('disk busy')):
            e.run_one(self.runner, job_id=2)
        e.update(1, 'failed')
        self.assertEqual(e.retry_all(), [1,2])
        e.run_one(lambda *a, **k: self.fail('Disk retries must not purchase another image'), job_id=2)
        self.assertEqual(self.calls, [3,2])
        self.assertEqual(e.db.execute('SELECT status FROM jobs WHERE id=3').fetchone()[0], 'applied')

    def test_retry_after_startup_recovery_applies_without_another_ai_call(self):
        e = self.engine
        with patch.object(e, 'apply', side_effect=SaveBusyError(SAVE_BUSY_NOTES[0])):
            e.run_one(self.runner, job_id=2)
        e.update(2, 'failed', SAVE_BUSY_NOTES[0])
        e.recover()
        self.assertEqual(e.db.execute('SELECT status FROM jobs WHERE id=2').fetchone()[0], 'generated')
        self.assertTrue(e.retry(2))
        self.assertIn(2, e.retry_all())
        e.run_one(lambda *a, **k: self.fail('Recovered results must not purchase another image'), job_id=2)
        self.assertEqual(self.calls, [2])
        self.assertEqual(e.db.execute('SELECT status FROM jobs WHERE id=2').fetchone()[0], 'applied')

    def test_existing_database_adds_priority_storage_without_resetting_jobs(self):
        e = self.engine
        with e.db:
            e.db.execute('DROP TABLE job_order')
        other = Engine(self.c)
        try:
            self.assertEqual([row['id'] for row in other.jobs()], [1,2,3])
            self.assertEqual(other.db.execute('SELECT count(*) FROM people').fetchone()[0], 3)
        finally:
            other.close()

    def test_searches_korean_english_accents_clubs_and_quoted_queries_without_writes(self):
        database = Path(self.c['state_dir']) / 'queue.sqlite'
        before = database.read_bytes()
        for query, ids in (('스펜스', {'1'}), ('FERNANDES', {'2'}), ('ÁLVARO', {'3'}), ('아스날', {'1','2','3'}), ('1', {'1'}), ("' OR 1=1 --", set())):
            rows, chosen = find_players(database, query, ['2','999'])
            self.assertEqual({row['id'] for row in rows}, ids)
            self.assertEqual([row['id'] for row in chosen], ['2'])
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(find_players(self.root / 'missing.sqlite'), ([],[]))
