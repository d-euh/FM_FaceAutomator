import json
import os
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
import gemini_cli
from engine import load_config, write_atomic
from tests import test_engine as fixtures


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'A graphical display is required')
class GeminiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EngineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.path = self.fixture.root / 'ui-config.json'
        write_atomic(self.path, json.dumps(self.fixture.c).encode())
        self.window = tk.Tk()
        self.addCleanup(self.window.destroy)
        with patch.object(App, 'auto_paths'):
            self.app = App(self.window, self.path)
        self.app.auth_cancel.set()
        self.addCleanup(self.cancel_timers)

    def cancel_timers(self):
        for timer in self.window.tk.call('after', 'info'):
            self.window.after_cancel(timer)

    def test_provider_switch_keeps_both_executables_and_saves_without_api_secrets(self):
        self.app.vars['gemini'].set('C:/Gemini API/gemini-api.exe')
        self.app.vars['image_provider'].set(gemini_cli.PROVIDERS['gemini'])
        self.app.open_settings()
        self.window.update()
        self.assertEqual(self.app.login_button.cget('text'), 'Gemini API 설정')
        self.assertEqual(str(self.app.cli_entry.cget('textvariable')), str(self.app.vars['gemini']))
        self.assertTrue(self.app.gemini_model_row.winfo_ismapped())
        self.assertTrue(self.app.save())
        saved = load_config(self.path)
        self.assertEqual(saved['image_provider'], 'gemini')
        self.assertEqual(saved['gemini'], 'C:/Gemini API/gemini-api.exe')
        self.assertFalse(any('api_key' in key for key in saved))
        self.app.vars['image_provider'].set(gemini_cli.PROVIDERS['codex'])
        self.window.update()
        self.assertEqual(self.app.login_button.cget('text'), 'ChatGPT 로그인')
        self.assertFalse(self.app.gemini_model_row.winfo_ismapped())
        self.assertTrue(self.app.save())
        self.assertEqual(load_config(self.path)['gemini'], saved['gemini'])

    def test_old_provider_auth_response_cannot_report_new_provider_as_logged_in(self):
        self.app.vars['image_provider'].set(gemini_cli.PROVIDERS['gemini'])
        self.app.accept_auth({'login': False, 'provider': 'codex', 'value': self.app.vars['codex'].get(), 'result': 'chatgpt'})
        self.assertNotIn('로그인됨', self.app.auth_status.get())
        self.assertIn('변경됨', self.app.auth_status.get())
