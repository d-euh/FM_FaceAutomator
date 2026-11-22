"""Check startup settings visibility using real Tk windows."""
import json
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
from engine import DEFAULTS


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'A graphical display is required')
class FirstLaunchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'config.json'
        self.root = tk.Tk()
        self.addCleanup(lambda: self.root.destroy())
        for name in ('auto_paths', 'codex_path_changed', 'drain'):
            patched = patch.object(App, name)
            patched.start()
            self.addCleanup(patched.stop)
        self.addCleanup(self.cancel_callbacks)

    def cancel_callbacks(self):
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)

    def discovery_result(self, app, updates=None, notes=None):
        return dict(path_scan=app.path_scan,
                    snapshot={key: app.vars[key].get() for key in ('source', 'portraits_dir', 'kits_dir', 'pack_dir', 'graphics_root', 'codex')},
                    updates=updates or {}, notes=notes or [])

    def test_first_launch_opens_settings_once_and_next_launch_starts_at_home(self):
        app = App(self.root, self.path)
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')
        source = str(self.path.parent / 'career.fm')
        result = self.discovery_result(app, {'source': source})
        app.path_scan += 1
        app.accept_paths(result)
        self.assertEqual(app.settings_window.state(), 'withdrawn')
        result['path_scan'] = app.path_scan
        app.accept_paths(result)
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'normal')
        self.assertEqual(app.vars['source'].get(), source)
        self.assertTrue(app.path_status.get().startswith('경로 확인 완료'))
        self.assertTrue(self.path.is_file())
        app.settings_window.withdraw()
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')
        app.accept_paths(self.discovery_result(app))
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')
        self.cancel_callbacks()
        self.root.destroy()
        self.root = tk.Tk()
        next_app = App(self.root, self.path)
        self.root.update()
        self.assertEqual(next_app.settings_window.state(), 'withdrawn')
        self.assertEqual(next_app.tabs.select(), str(next_app.home_tab))

    def test_existing_configuration_is_preserved_and_settings_stay_closed(self):
        saved = json.dumps(DEFAULTS | {'additional_instructions': '기존 지시 유지', 'custom_key': 'preserve'})
        self.path.write_text(saved, encoding='utf-8')
        app = App(self.root, self.path)
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')
        self.assertEqual(app.tabs.select(), str(app.home_tab))
        self.assertEqual(self.path.read_text(encoding='utf-8'), saved)
        app.accept_paths(self.discovery_result(app))
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')

    def test_failed_search_still_opens_first_launch_settings_for_manual_selection(self):
        app = App(self.root, self.path)
        app.accept_paths(self.discovery_result(app, notes=['검색 실패']))
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'normal')
        self.assertIn('검색 경고 1건', app.path_status.get())

    def test_manual_open_and_close_during_search_is_not_reopened_on_completion(self):
        app = App(self.root, self.path)
        app.open_settings()
        self.root.update()
        app.settings_window.withdraw()
        app.accept_paths(self.discovery_result(app))
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'withdrawn')
