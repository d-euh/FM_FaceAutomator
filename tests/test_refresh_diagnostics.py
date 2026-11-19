import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from refresh_diagnostics import EXPECTED_BUILD, PLUGIN_NAME, REPORT_PARTS, export_report, find_steam_games, install_plugin, validate_game


class RefreshDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / "steamapps" / "common" / "Football Manager 27"
        self.core = self.game / "BepInEx" / "core"
        self.core.mkdir(parents=True)
        for path in (self.game / "fm.exe", self.game / "GameAssembly.dll", self.core / "BepInEx.Core.dll", self.core / "BepInEx.Unity.IL2CPP.dll"):
            path.write_bytes(b"MZ fixture")
        (self.core / "BepInEx.Core.dll").write_bytes(b"MZ fixture 6.0.0-be.793+dbc82f0")
        self.manifest = self.root / "steamapps" / "appmanifest_123.acf"
        self.manifest.write_text(f'"name" "Football Manager 27" "installdir" "Football Manager 27" "buildid" "{EXPECTED_BUILD}"')
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        self.payload = b"MZ diagnostics fixture"
        (self.bundle / PLUGIN_NAME).write_bytes(self.payload)
        (self.bundle / "SHA256SUMS").write_text(hashlib.sha256(self.payload).hexdigest() + "  " + PLUGIN_NAME)

    def test_find_steam_library_and_reject_wrong_build_or_missing_il2cpp_loader(self):
        primary = self.root / "primary"
        (primary / "steamapps").mkdir(parents=True)
        (primary / "steamapps" / "libraryfolders.vdf").write_text('"path" "' + str(self.root) + '"')
        self.assertEqual(find_steam_games([primary]), [self.game])
        self.manifest.write_text(self.manifest.read_text().replace(EXPECTED_BUILD, "11111111"))
        with self.assertRaisesRegex(ValueError, EXPECTED_BUILD):
            validate_game(self.game)
        self.manifest.write_text(self.manifest.read_text().replace("11111111", EXPECTED_BUILD))
        (self.core / "BepInEx.Unity.IL2CPP.dll").unlink()
        with self.assertRaisesRegex(ValueError, "BepInEx 6"):
            validate_game(self.game)

    def test_install_preserves_loader_and_other_plugins_and_backs_up_own_previous_dll(self):
        other = self.game / "BepInEx" / "plugins" / "Other" / "Other.dll"
        other.parent.mkdir(parents=True)
        other.write_bytes(b"another plugin")
        target = install_plugin(self.game, self.bundle)
        self.assertEqual(target.read_bytes(), self.payload)
        target.write_bytes(b"old diagnostic")
        install_plugin(self.game, self.bundle)
        self.assertEqual(target.with_suffix(".dll.previous").read_bytes(), b"old diagnostic")
        self.assertEqual(other.read_bytes(), b"another plugin")
        self.assertEqual((self.core / "BepInEx.Core.dll").read_bytes(), b"MZ fixture 6.0.0-be.793+dbc82f0")

    def test_old_or_unidentified_loader_is_not_silently_accepted(self):
        loader = self.core / "BepInEx.Core.dll"
        for version in (b"6.0.0-pre.2", b"6.0.0-be.755", b"unidentified"):
            loader.write_bytes(b"MZ " + version)
            with self.assertRaisesRegex(ValueError, "be.793"):
                install_plugin(self.game, self.bundle)
        self.assertFalse((self.game / "BepInEx" / "plugins").exists())

    def test_tampered_dll_is_rejected_before_existing_plugin_is_changed(self):
        target = install_plugin(self.game, self.bundle)
        (self.bundle / PLUGIN_NAME).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "손상"):
            install_plugin(self.game, self.bundle)
        self.assertEqual(target.read_bytes(), self.payload)

    def test_export_keeps_read_only_status_and_rejects_missing_or_wrong_report(self):
        destination = self.root / "export" / "refresh-diagnostic.json"
        with self.assertRaisesRegex(ValueError, "아직"):
            export_report(self.game, destination)
        report_path = self.game.joinpath(*REPORT_PARTS)
        report_path.parent.mkdir(parents=True)
        report = {"schema_version": 1, "mode": "metadata_only", "refresh_available": False, "detected_steam_build": EXPECTED_BUILD}
        report_path.write_text(json.dumps(report))
        self.assertEqual(json.loads(export_report(self.game, destination).read_text()), report)
        report_path.write_text(json.dumps(report | {"refresh_available": True}))
        with self.assertRaisesRegex(ValueError, "이 버전"):
            export_report(self.game, destination)


if __name__ == "__main__":
    unittest.main()
