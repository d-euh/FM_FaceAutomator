import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import gemini_cli
from engine import DEFAULTS, load_config, validate_png, write_atomic
from tests import test_engine as fixtures


class GeminiBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EngineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.c, self.e, self.root = self.fixture.c, self.fixture.e, self.fixture.root
        self.c.update(image_provider='gemini', gemini=shutil.which('python3') or shutil.which('python'))
        self.calls = []

    def runner(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs['input']))
        self.assertFalse(kwargs['shell'])
        self.assertNotIn('--api-key', cmd)
        if cmd[1] == 'generate':
            json.dump({'status': 'completed', 'steps': [{'type': 'model_output', 'content': [
                {'type': 'text', 'text': 'Djed Spence'}]}]}, kwargs['stdout'])
        else:
            self.assertEqual(cmd[1], 'image')
            self.assertEqual(cmd.count('-i'), 2)
            for i, token in enumerate(cmd):
                if token == '-i':
                    self.assertTrue(Path(cmd[i + 1]).is_file())
            Image.new('RGB', (1024, 1024), 'green').save(cmd[cmd.index('--out') + 1])
        return SimpleNamespace(returncode=0)

    def job(self, english='Djed Spence'):
        jid = self.fixture.transfer()
        self.fixture.refs()
        with self.e.db:
            row = json.loads(self.e.db.execute('SELECT data FROM people').fetchone()[0])
            row['english_name'] = english
            if not english:
                row['name'] = '제드 스펜스'
            self.e.db.execute('UPDATE people SET data=?', (json.dumps(row),))
        return jid

    def test_two_references_and_custom_directions_produce_id_png_xml_and_english_caption(self):
        jid = self.job()
        self.c['additional_instructions'] = 'Keep the rain.'
        self.e.begin_job_edit(jid)
        self.e.finish_job_edit(jid, {'additional_instructions': 'Smile.'})
        self.e.run_one(self.runner)
        job = self.e.jobs()[0]
        self.assertEqual(job['status'], 'applied', job['note'])
        self.assertEqual(len(self.calls), 1)
        cmd, prompt = self.calls[0]
        self.assertIn('Keep the rain.', prompt)
        self.assertIn('Smile.', prompt)
        self.assertNotIn('built-in image generation tool', prompt)
        self.assertNotIn('Return english_name in your JSON', prompt)
        self.assertEqual(cmd[cmd.index('--model') + 1], gemini_cli.DEFAULT_MODEL)
        target = Path(self.c['pack_dir']) / '900001.png'
        validate_png(target)
        with Image.open(target) as image:
            self.assertEqual(image.info['PlayerName'], 'DJED SPENCE')
        self.assertIn('person/900001/portrait', (target.parent / 'config.xml').read_text())
        self.assertEqual(json.loads(job['data'])['image_provider'], 'gemini')

    def test_missing_latin_name_is_romanized_before_image_request(self):
        self.job(english='')
        self.e.run_one(self.runner)
        self.assertEqual([cmd[1] for cmd, _ in self.calls], ['generate', 'image'])
        self.assertEqual(self.e.jobs()[0]['status'], 'applied')
        self.assertEqual(json.loads((Path(self.e.jobs()[0]['artifact']).parent / 'request.json').read_text())['name_source'], 'gemini_romanized')

    def test_bad_name_reply_never_buys_an_image(self):
        self.job(english='')
        def bad(cmd, **kwargs):
            self.assertEqual(cmd[1], 'generate')
            kwargs['stdout'].write('{"name":"Djed Spence"}')
            return SimpleNamespace(returncode=0)
        self.e.run_one(bad)
        self.assertEqual(self.e.jobs()[0]['status'], 'failed')
        self.assertFalse(list(Path(self.c['state_dir']).glob('jobs/*/portrait.png')))

    def test_missing_local_references_block_before_paid_calls_without_codex_fallback(self):
        jid = self.job()
        for missing in ('portraits_dir', 'kits_dir'):
            with self.subTest(missing=missing):
                self.fixture.refs()
                self.e.retry(jid)
                shutil.rmtree(self.c[missing])
                self.e.run_one(lambda *a, **k: self.fail('Missing references must not call any provider'))
                job = self.e.jobs()[0]
                self.assertEqual(job['status'], 'blocked')
                self.assertIn('Gemini', job['note'])
                self.assertEqual(self.e.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_saved_image_recovery_after_interrupt_reuses_paid_result(self):
        jid = self.job()
        def interrupted(cmd, **kwargs):
            self.runner(cmd, **kwargs)
            from generation import GenerationCancelled
            raise GenerationCancelled()
        self.e.run_one(interrupted)
        self.assertEqual(self.e.jobs()[0]['status'], 'interrupted')
        self.assertTrue(self.e.recover_busy_result(jid))
        self.e.run_one(lambda *a, **k: self.fail('Must reuse paid image'))
        self.assertEqual(self.e.jobs()[0]['status'], 'applied')
        self.assertEqual(len(self.calls), 1)

    def test_save_failure_retries_locally_without_another_api_call(self):
        self.job()
        with patch('engine.facepack.apply', side_effect=OSError('disk busy')):
            self.e.run_one(self.runner)
        self.assertEqual(self.e.jobs()[0]['status'], 'apply_failed')
        self.e.retry(self.e.jobs()[0]['id'])
        self.e.run_one(lambda *a, **k: self.fail('Must reuse paid image'))
        self.assertEqual(self.e.jobs()[0]['status'], 'applied')
        self.assertEqual(len(self.calls), 1)

    def test_cli_failure_and_non_png_output_cannot_modify_facepack(self):
        jid = self.job()
        self.e.run_one(lambda *a, **k: SimpleNamespace(returncode=3))
        self.assertEqual(self.e.jobs()[0]['status'], 'failed')
        self.assertIn('Gemini API CLI 종료 코드 3', self.e.jobs()[0]['note'])
        self.assertFalse((Path(self.c['pack_dir']) / 'config.xml').exists())
        self.e.retry(jid)
        def invalid(cmd, **kwargs):
            Image.new('RGB', (1024, 1024)).save(cmd[cmd.index('--out') + 1], format='JPEG')
            return SimpleNamespace(returncode=0)
        self.e.run_one(invalid)
        self.assertEqual(self.e.jobs()[0]['status'], 'failed')
        self.assertIn('PNG', self.e.jobs()[0]['note'])
        self.assertFalse((Path(self.c['pack_dir']) / 'config.xml').exists())

    def test_legacy_config_keeps_codex_and_unknown_provider_is_rejected(self):
        path = self.root / 'config.json'
        write_atomic(path, json.dumps({'source': 'career.json', 'additional_instructions': 'retain me'}).encode())
        migrated = load_config(path)
        self.assertEqual(migrated['image_provider'], 'codex')
        self.assertEqual(migrated['additional_instructions'], 'retain me')
        for changes in ({'image_provider': 'unverified'}, {'gemini_model': '--bad'}, {'gemini_model': ''}):
            with self.subTest(changes=changes):
                write_atomic(path, json.dumps(DEFAULTS | changes).encode())
                with self.assertRaises(ValueError):
                    load_config(path)


class GeminiAuthTests(unittest.TestCase):
    def test_wrong_agent_and_shell_wrappers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            for value in ('gemini', 'gemini.exe', 'gemini.cmd'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    gemini_cli.resolve_executable(value, temp)
            with patch('gemini_cli.shutil.which', return_value='/tmp/gemini-api.cmd'), self.assertRaises(ValueError):
                gemini_cli.resolve_executable('gemini-api', temp)

    def test_status_is_installation_only_and_cannot_leak_credentials(self):
        with patch('gemini_cli.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(gemini_cli.status('gemini-api', '.'), 'gemini_ready')
            self.assertEqual(run.call_args.args[0], ['gemini-api', '--version'])
            self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)
            self.assertFalse(run.call_args.kwargs['shell'])
        with patch('gemini_cli.subprocess.run', side_effect=OSError('SECRET')):
            self.assertEqual(gemini_cli.status('gemini-api', '.'), 'gemini_unknown')

    def test_configure_uses_cli_owned_interactive_credential_storage(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        with patch('gemini_cli.subprocess.Popen', return_value=process) as start:
            self.assertEqual(gemini_cli.configure('gemini-api', '.', threading.Event()), 'gemini_configured')
            self.assertEqual(start.call_args.args[0], ['gemini-api', 'configure', '--interactive'])
            self.assertFalse(start.call_args.kwargs['shell'])
            self.assertNotIn('stdout', start.call_args.kwargs)

    def test_cancelled_setup_does_not_start_a_cli(self):
        cancel = threading.Event()
        cancel.set()
        with patch('gemini_cli.subprocess.Popen') as start:
            self.assertEqual(gemini_cli.configure('gemini-api', '.', cancel), 'cancelled')
            start.assert_not_called()
