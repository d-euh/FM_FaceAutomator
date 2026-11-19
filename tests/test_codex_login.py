from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from codex_login import browser_login, login_status, resolve_codex


class CodexLoginTests(unittest.TestCase):
    def test_status_recognizes_chatgpt_and_never_exposes_other_credentials(self):
        for code, output, expected in ((0, "Logged in using ChatGPT", "chatgpt"),
                                       (0, "API key configured - sk-secret-content", "other"),
                                       (0, "Logged in using access token", "other"),
                                       (1, "Not logged in", "signed_out"),
                                       (1, "Error loading ChatGPT auth: sk-secret-content", "unknown")):
            with self.subTest(expected=expected, code=code), patch("codex_login.subprocess.run", return_value=SimpleNamespace(returncode=code, stdout="", stderr=output)) as run:
                result = login_status("C:/CLI path/codex.exe", "C:/App path")
                self.assertEqual(result, expected)
                self.assertNotIn("secret", result)
                self.assertEqual(run.call_args.args[0], ["C:/CLI path/codex.exe", "login", "status"])
                self.assertFalse(run.call_args.kwargs["shell"])

    def test_unavailable_or_slow_status_does_not_start_login(self):
        for error in (OSError("missing"), subprocess.TimeoutExpired("codex", 15)):
            with patch("codex_login.subprocess.run", side_effect=error), patch("codex_login.subprocess.Popen") as start:
                self.assertEqual(login_status("codex", "."), "unknown")
                start.assert_not_called()

    def test_windows_login_uses_visible_console_and_checks_actual_chatgpt_status(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        with patch("codex_login.os", SimpleNamespace(name="nt")), patch("codex_login.subprocess.CREATE_NEW_CONSOLE", 16, create=True), patch("codex_login.subprocess.Popen", return_value=process) as start, patch("codex_login.login_status", return_value="chatgpt") as status:
            self.assertEqual(browser_login("C:/CLI & path/codex.exe", "C:/App path", threading.Event()), "complete")
            self.assertEqual(start.call_args.args[0], ["C:/CLI & path/codex.exe", "login"])
            self.assertEqual(start.call_args.kwargs["creationflags"], 16)
            self.assertFalse(start.call_args.kwargs["shell"])
            self.assertNotIn("stdout", start.call_args.kwargs)
            status.assert_called_once_with("C:/CLI & path/codex.exe", "C:/App path")

    def test_successful_exit_without_chatgpt_auth_is_not_reported_as_connected(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        with patch("codex_login.subprocess.Popen", return_value=process), patch("codex_login.login_status", return_value="other"):
            self.assertEqual(browser_login("codex", ".", threading.Event()), "unconfirmed")
        process.returncode = 1
        process.poll.return_value = 1
        with patch("codex_login.subprocess.Popen", return_value=process), patch("codex_login.login_status") as status:
            self.assertEqual(browser_login("codex", ".", threading.Event()), "incomplete")
            status.assert_not_called()

    def test_close_cancels_only_our_login_process_without_logout(self):
        cancel = threading.Event()
        with patch("codex_login.subprocess.Popen") as start:
            cancel.set()
            self.assertEqual(browser_login("codex", ".", cancel), "cancelled")
            start.assert_not_called()
        cancel.clear()
        process = Mock()
        process.poll.side_effect = lambda: cancel.set()
        with patch("codex_login.subprocess.Popen", return_value=process), patch("codex_login.login_status") as status:
            self.assertEqual(browser_login("codex", ".", cancel), "cancelled")
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=5)
            status.assert_not_called()

    def test_resolver_uses_detected_exe_and_preserves_quoted_paths_with_spaces(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            exe = base / "CLI path" / "codex.exe"
            exe.parent.mkdir()
            exe.touch()
            exe.chmod(0o755)
            with patch("codex_login.find_codex", return_value=str(exe)):
                self.assertEqual(resolve_codex("codex", base), str(exe.resolve()))
            self.assertEqual(resolve_codex('"CLI path/codex.exe"', base), str(exe.resolve()))
            wrapper = base / "codex.cmd"
            wrapper.touch()
            wrapper.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "codex.exe"):
                resolve_codex(str(wrapper), base)
            with self.assertRaisesRegex(ValueError, "찾지 못"):
                resolve_codex(str(base / "missing.exe"), base)
