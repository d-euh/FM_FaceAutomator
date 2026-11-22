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

    def test_first_launch_opens_settings_once_and_next_launch_starts_at_home(self):
        app = App(self.root, self.path)
        self.root.update()
        self.assertEqual(app.settings_window.state(), 'normal')
        self.assertTrue(self.path.is_file())
        app.settings_window.withdraw()
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
