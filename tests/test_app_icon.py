from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from PIL import Image
import app
from scripts.verify_windows_icon import ico_frames, verify_resources


class AppIconTests(unittest.TestCase):
    def test_png_and_multi_size_windows_icon_decode(self):
        icons = Path(app.__file__).resolve().parent / 'icons'
        with Image.open(icons / 'ffa.png') as image:
            self.assertEqual(image.size, (256, 256))
            image.verify()
        with Image.open(icons / 'ffa.ico') as icon:
            sizes = {(size, size) for size in (16, 20, 24, 28, 32, 40, 48, 64, 96, 128, 192, 256)}
            self.assertEqual(icon.ico.sizes(), sizes)
            for size in sizes:
                self.assertEqual(icon.ico.getimage(size).size, size)

    def test_frozen_resource_location_is_independent_of_executable_and_config(self):
        resource = Path(app.__file__).resolve().parent / 'test-bundle' / '_internal' / 'app.py'
        window = Mock()
        with patch.object(app, '__file__', str(resource)), patch.object(app, 'os', SimpleNamespace(name='nt')), patch.object(app.sys, 'frozen', True, create=True), patch.object(app.tk, 'PhotoImage') as photo:
            app.set_app_icon(window)
        photo.assert_called_once_with(master=window, file=str(resource.parent / 'icons' / 'ffa.png'))
        self.assertIs(window.app_icon, photo.return_value)
        self.assertEqual(window.iconphoto.call_args_list, [
            call(True, photo.return_value), call(False, photo.return_value),
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
        self.assertIn('--icon "%~dp0icons\\ffa.ico"', script)
        self.assertIn('--add-data "icons;icons"', script)
        self.assertIn('scripts\\verify_windows_icon.py', script)

    def test_build_verifier_rejects_default_missing_or_corrupt_icon(self):
        expected = ico_frames(Path(app.__file__).resolve().parent / 'icons' / 'ffa.ico')

        def make_pe(frames, missing=False, corrupt=False):
            payloads = {}
            group = struct.pack('<HHH', 0, 1, len(frames))
            icon_items = []
            for index, (header, payload) in enumerate(frames, 1):
                group += struct.pack('<BBBBHHIH', *header, len(payload), index)
                payloads[index] = payload
                if not (missing and index == 1):
                    data = SimpleNamespace(struct=SimpleNamespace(OffsetToData=index, Size=len(payload)))
                    language = SimpleNamespace(id=1033, data=data)
                    icon_items.append(SimpleNamespace(id=index, directory=SimpleNamespace(entries=[language])))
            if corrupt:
                payloads[1] = b'x' * len(payloads[1])
            payloads[0] = group
            group_data = SimpleNamespace(struct=SimpleNamespace(OffsetToData=0, Size=len(group)))
            group_item = SimpleNamespace(id=1, directory=SimpleNamespace(entries=[SimpleNamespace(id=1033, data=group_data)]))
            resources = [
                SimpleNamespace(id=3, directory=SimpleNamespace(entries=icon_items)),
                SimpleNamespace(id=14, directory=SimpleNamespace(entries=[group_item])),
            ]
            return SimpleNamespace(DIRECTORY_ENTRY_RESOURCE=SimpleNamespace(entries=resources), get_data=lambda offset, size: payloads[offset])

        verify_resources(make_pe(expected), expected)
        for pe in (make_pe(expected, missing=True), make_pe(expected, corrupt=True), make_pe(expected[:1])):
            with self.subTest(pe=pe), self.assertRaises(ValueError):
                verify_resources(pe, expected)
