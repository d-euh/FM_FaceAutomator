from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from PIL import Image
import app


class AppIconTests(unittest.TestCase):
    def test_png_and_multi_size_windows_icon_decode(self):
        icons = Path(app.__file__).resolve().parent / 'icons'
        with Image.open(icons / 'ffa.png') as image:
            self.assertEqual(image.size, (256, 256))
            image.verify()
        with Image.open(icons / 'ffa.ico') as icon:
            sizes = {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)}
            self.assertEqual(icon.ico.sizes(), sizes)
            for size in sizes:
                self.assertEqual(icon.ico.getimage(size).size, size)

    def test_frozen_resource_location_is_independent_of_executable_and_config(self):
        resource = Path(app.__file__).resolve().parent / 'test-bundle' / '_internal' / 'app.py'
        window = Mock()
        with patch.object(app, '__file__', str(resource)), patch.object(app, 'os', SimpleNamespace(name='nt')), patch.object(app.sys, 'frozen', True, create=True):
            app.set_app_icon(window)
        icon_path = str(resource.parent / 'icons' / 'ffa.ico')
        self.assertEqual(window.iconbitmap.call_args_list, [
            call(default=icon_path),
            call(icon_path),
        ])

    def test_windows_taskbar_identity_is_set_before_creating_window(self):
        events = Mock()
        events.attach_mock(Mock(), 'identity')
        events.attach_mock(Mock(), 'window')
        shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=events.identity)
        with patch.object(app, 'os', SimpleNamespace(name='nt')), patch('ctypes.windll', SimpleNamespace(shell32=shell), create=True), patch.object(app.tk, 'Tk', events.window), patch.object(app, 'App'), patch.object(app.argparse.ArgumentParser, 'parse_args', return_value=SimpleNamespace(scan=False, config='unused.json')):
            app.main()
        self.assertEqual(events.mock_calls[0].args, ('d_euh.FMFaceAutomator',))
        self.assertEqual(events.mock_calls[0][0], 'identity')
        self.assertEqual(events.mock_calls[1][0], 'window')

    def test_windows_build_embeds_and_packages_icons(self):
        script = (Path(app.__file__).resolve().parent / 'build_windows.bat').read_text()
        self.assertIn('--icon "icons\\ffa.ico"', script)
        self.assertIn('--add-data "icons;icons"', script)
