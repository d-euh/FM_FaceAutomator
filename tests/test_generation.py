import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from generation import GenerationCancelled, run_codex


class GenerationProcessTests(unittest.TestCase):
    def run_process(self, code, **kwargs):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            return run_codex([sys.executable, '-c', code], input='reference data', stdout=out,
                             stderr=err, timeout=3, heartbeat_interval=.05, **kwargs)

    def test_heartbeat_runs_while_child_is_still_generating(self):
        ticks = []
        result = self.run_process('import time; time.sleep(.35)', heartbeat=lambda: ticks.append(1))
        self.assertEqual(result.returncode, 0)
        self.assertGreaterEqual(len(ticks), 2)

    def test_cancel_terminates_process_and_does_not_report_success(self):
        cancel = threading.Event()
        actual_start, processes = subprocess.Popen, []
        def start(*args, **kwargs):
            process = actual_start(*args, **kwargs)
            processes.append(process)
            return process
        timer = threading.Timer(.25, cancel.set)
        timer.start()
        try:
            with patch('generation.subprocess.Popen', side_effect=start):
                with self.assertRaises(GenerationCancelled):
                    self.run_process('import time; time.sleep(20)', cancel_event=cancel)
            self.assertIsNotNone(processes[0].poll())
        finally:
            timer.cancel()

    def test_already_cancelled_request_never_launches(self):
        cancel = threading.Event()
        cancel.set()
        with patch('generation.subprocess.Popen') as launch:
            with self.assertRaises(GenerationCancelled):
                self.run_process('pass', cancel_event=cancel)
        launch.assert_not_called()

    def test_timeout_and_heartbeat_errors_reap_the_child(self):
        actual_start, processes = subprocess.Popen, []
        def start(*args, **kwargs):
            process = actual_start(*args, **kwargs)
            processes.append(process)
            return process
        def error():
            raise ValueError('save changed to an older timeline')
        with patch('generation.subprocess.Popen', side_effect=start):
            with self.assertRaisesRegex(ValueError, 'timeline'):
                self.run_process('import time; time.sleep(20)', heartbeat=error)
            with tempfile.TemporaryFile() as out:
                with self.assertRaises(subprocess.TimeoutExpired):
                    run_codex([sys.executable,'-c','import time; time.sleep(20)'], input='', stdout=out, stderr=out, timeout=.15)
        self.assertTrue(all(process.poll() is not None for process in processes))
