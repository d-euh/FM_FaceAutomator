import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from team_bindings import DLL, FOLDER, export_report, install


class TeamBindingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root/'game'
        self.dll = self.game/'BepInEx'/'plugins'/FOLDER/DLL
        self.dll.parent.mkdir(parents=True)
        self.dll.write_bytes(b'MZ fixture')
        self.source = self.game/'BepInEx'/'diagnostics'/FOLDER/'team-bindings.json'
        self.source.parent.mkdir(parents=True)
        self.output = self.root/'diagnostics'/'team-bindings.json'
        self.report = dict(kind='fm_team_bindings', schema_version=1, mode='runtime_team_reader_service',
                           detected_steam_build='26620374', game_data_query_attempted=True, gameplay_state_modified=False, save_files_modified=False, probe={'state':'complete','results':[]},
                           tool_version='0.4.2', state='complete', schemas=[], types=[], errors=[],
                           observations={'observed_existing_ui_values_only':True, 'state':'capturing', 'values':[]})
        self.validation = patch('team_bindings.validate_game', return_value=self.game)
        self.validation.start()
        self.addCleanup(self.validation.stop)
        self.write()

    def write(self):
        self.source.write_text(json.dumps(self.report))
        os.utime(self.source, ns=(self.dll.stat().st_mtime_ns+1000000,)*2)

    def test_export_preserves_source_and_writes_only_report(self):
        original = self.source.read_bytes()
        self.assertEqual(export_report(self.game, self.output), self.output)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)

    def test_stale_or_incomplete_report_cannot_replace_previous_export(self):
        self.output.parent.mkdir()
        self.output.write_text('old export')
        os.utime(self.source, ns=(self.dll.stat().st_mtime_ns-1000000,)*2)
        with self.assertRaisesRegex(ValueError, '아직'):
            export_report(self.game, self.output)
        for state in ('waiting_for_main_thread', 'reading_schema'):
            self.report['state'] = state
            self.write()
            with self.assertRaisesRegex(ValueError, '아직'):
                export_report(self.game, self.output)
        self.assertEqual(self.output.read_text(), 'old export')

    def test_rejects_modified_game_flags_build_and_untrusted_paths(self):
        for key, value in [('gameplay_state_modified',True), ('save_files_modified',True), ('game_data_query_attempted',None), ('probe',None),
                           ('detected_steam_build','other'), ('mode','other'), ('types',None), ('observations',None)]:
            with self.subTest(key=key):
                old = self.report[key]
                self.report[key] = value
                self.write()
                with self.assertRaises(ValueError):
                    export_report(self.game, self.output)
                self.report[key] = old
        self.write()
        with self.assertRaisesRegex(ValueError, '설치 폴더 밖'):
            export_report(self.game, self.game/'overwrite.json')

    def test_partial_or_unavailable_reports_remain_exportable_for_diagnosis(self):
        for state in ('complete_with_errors', 'unavailable'):
            self.report.update(state=state, errors=[{'stage':'schema', 'error':'MissingMethodException'}])
            self.write()
            export_report(self.game,self.output)
            self.assertEqual(json.loads(self.output.read_text())['state'],state)

    def test_install_requires_closed_game_and_uses_separate_component(self):
        with patch('team_bindings.game_process_running',return_value=True), patch('team_bindings.install_component') as component:
            with self.assertRaisesRegex(ValueError,'종료'):
                install(self.game)
            component.assert_not_called()
        with patch('team_bindings.game_process_running',return_value=False), patch('team_bindings.install_component') as component:
            install(self.game)
            component.assert_called_once_with(self.game,None,DLL,FOLDER)

    def test_old_tool_version_is_rejected_even_if_file_timestamp_is_recent(self):
        self.report['tool_version'] = '0.1.0'
        self.write()
        with self.assertRaisesRegex(ValueError, '재설치'):
            export_report(self.game, self.output)

    def test_previous_successful_schema_report_requests_reinstallation(self):
        self.report.update(tool_version='0.1.1', mode='runtime_schema_only')
        self.write()
        with self.assertRaisesRegex(ValueError,'재설치'):
            export_report(self.game,self.output)

    def test_empty_passive_observations_are_exported_for_diagnosing_missing_hooks(self):
        self.report['observations']['values'] = []
        self.write()
        export_report(self.game,self.output)
        self.assertEqual(json.loads(self.output.read_text())['observations']['values'],[])

    def test_probe_failure_or_waiting_is_exported_without_claiming_success(self):
        for state in ('failed','unavailable','waiting_for_safe_loaded_game','partial_team_tree'):
            self.report['probe'] = {'state':state, 'results':[]}
            self.write()
            export_report(self.game,self.output)
            self.assertEqual(json.loads(self.output.read_text())['probe']['state'],state)
