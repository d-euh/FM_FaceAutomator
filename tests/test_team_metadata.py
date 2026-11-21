import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from team_metadata import HELPER, export_metadata, find_games, helper_path, interop_folder


class TeamMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game=self.root/'Steam Library'/'Football Manager 27'
        self.interop=self.game/'BepInEx'/'interop'
        self.interop.mkdir(parents=True)
        for path in (self.game/'fm.exe',self.game/'GameAssembly.dll',self.interop/'FM.Data.dll'):
            path.write_bytes(b'MZ fixture')
        self.bundle=self.root/'bundle'
        self.bundle.mkdir()
        self.helper=self.bundle/HELPER
        self.helper.write_bytes(b'MZ diagnostic executable fixture')
        self.manifest=self.bundle/'SHA256SUMS'
        self.manifest.write_text(hashlib.sha256(self.helper.read_bytes()).hexdigest()+'  '+HELPER)
        self.output=self.root/'diagnostics'/'team-metadata.json'
        self.report={'kind':'fm_team_metadata','schema_version':1,'mode':'metadata_only',
                     'game_methods_invoked':False,'tool_version':'0.2.0','focus_types':['SI.Core.DynamicNumber'],'scanned_assemblies':1,'assemblies':[],'errors':[]}

    def run_export(self, runner):
        return export_metadata(self.interop,self.output,'26620374',bundle=self.bundle,runner=runner)

    def test_reuses_saved_install_path_and_deduplicates_steam_discovery(self):
        (self.root/'.refresh-diagnostics.json').write_text(json.dumps({'game':str(self.game)}))
        with patch('team_metadata.find_steam_games',return_value=[self.game]):
            self.assertEqual(find_games(self.root),[self.game])
        self.assertEqual(interop_folder(self.game/'fm.exe'),(self.game,self.interop))
        (self.interop/'FM.Data.dll').unlink()
        with self.assertRaisesRegex(ValueError,'interop'):
            interop_folder(self.game)

    def test_tampered_bundle_is_rejected_before_any_execution(self):
        self.helper.write_bytes(b'MZ changed')
        with self.assertRaisesRegex(ValueError,'해시'):
            self.run_export(lambda *a,**k:self.fail('Must not run a tampered helper'))

    def test_export_uses_exact_arguments_and_validates_before_atomic_replacement(self):
        original=(self.interop/'FM.Data.dll').read_bytes()
        self.output.parent.mkdir()
        self.output.write_text('previous report')
        def runner(command,**kwargs):
            self.assertFalse(kwargs['shell'])
            self.assertEqual(command[0],str(self.helper))
            self.assertEqual(command[1],str(self.interop))
            self.assertEqual(command[3],'26620374')
            self.assertNotEqual(Path(command[2]),self.output)
            self.assertEqual(self.output.read_text(),'previous report')
            Path(command[2]).write_text(json.dumps(self.report))
            return NS(returncode=0)
        path,report=self.run_export(runner)
        self.assertEqual(path,self.output)
        self.assertEqual(report,self.report)
        self.assertEqual(json.loads(self.output.read_text()),self.report)
        self.assertEqual((self.interop/'FM.Data.dll').read_bytes(),original)

    def test_failed_empty_or_invalid_export_cannot_reuse_or_destroy_old_report(self):
        self.output.parent.mkdir()
        self.output.write_text('previous report')
        def runner(command,**kwargs):
            Path(command[2]).write_text(json.dumps(self.report | {'game_methods_invoked':True}))
            return NS(returncode=0)
        with self.assertRaises(ValueError):
            self.run_export(runner)
        with self.assertRaises(ValueError):
            self.run_export(lambda *a,**k:NS(returncode=1))
        with self.assertRaises(FileNotFoundError):
            self.run_export(lambda *a,**k:NS(returncode=0))
        self.assertEqual(self.output.read_text(),'previous report')

    def test_cannot_write_report_inside_game_dll_folder_or_over_a_dll(self):
        for path in (self.interop/'report.json',self.root/'FM.Data.dll'):
            with self.subTest(path=path),self.assertRaises(ValueError):
                export_metadata(self.interop,path,bundle=self.bundle,runner=lambda *a,**k:self.fail('Invalid destination'))

    def test_previous_metadata_helper_cannot_be_mistaken_for_focused_api_export(self):
        previous = self.report | {'tool_version':'0.1.0'}
        def runner(command, **kwargs):
            Path(command[2]).write_text(json.dumps(previous))
            return NS(returncode=0)
        with self.assertRaisesRegex(ValueError, '기존'):
            self.run_export(runner)
