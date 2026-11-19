import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import live_refresh


class LiveRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bridge = self.root / "bridge"
        self.pack = self.root / "pack"
        self.pack.mkdir()
        (self.pack / "config.xml").write_text('<record from="1" to="graphics/pictures/person/1/portrait"/>')
        self.session = "a" * 32
        self.directory = self.bridge / "sessions" / f"12-{self.session}"
        self.status = {"protocol": 1, "profile": live_refresh.PROFILE, "pid": 12, "session": self.session,
                       "heartbeat": 1000, "available": True, "stage": "idle", "reason": "idle", "plugin_version": "0.2.2"}
        self.pending = {"pack_dir": str(self.pack), "revision": "revision"}
        self.connect()

    def connect(self, **updates):
        self.status.update(updates)
        live_refresh.write_json(self.directory / "status.json", self.status)

    def test_request_is_session_bound_and_completion_requires_matching_reply(self):
        pending, message = live_refresh.pump(self.pending, self.bridge, 1000)
        request_file = self.bridge / "requests" / self.session / (pending["request_id"] + ".json")
        request = json.loads(request_file.read_text())
        self.assertEqual(request["session"], self.session)
        self.assertEqual(request["config_sha256"], hashlib.sha256((self.pack / "config.xml").read_bytes()).hexdigest())
        waiting, message = live_refresh.pump(pending, self.bridge, 1001)
        self.assertIsNotNone(waiting)
        self.assertNotIn("처리 완료", message)
        reply = self.directory / "responses" / request_file.name
        response = {"protocol": 1, "profile": live_refresh.PROFILE, "session": self.session,
                    "id": pending["request_id"], "status": "refreshed",
                    "execution": {"started": True, "rescan_attempts": 1, "completion_callbacks": 1, "cache_and_panel_attempts": 1}}
        live_refresh.write_json(reply, response | {"session": "b" * 32})
        self.assertIsNotNone(live_refresh.pump(pending, self.bridge, 1001)[0])
        live_refresh.write_json(reply, response)
        self.assertIsNone(live_refresh.pump(pending, self.bridge, 1001)[0])
        self.assertIn("처리 완료", live_refresh.pump(pending, self.bridge, 1001)[1])

    def test_stale_wrong_profile_and_ambiguous_sessions_do_not_receive_requests(self):
        for update in ({"heartbeat": 980}, {"profile": "fm26"}):
            self.connect(**update)
            pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
            self.assertNotIn("request_id", pending)
        self.connect(heartbeat=1000, profile=live_refresh.PROFILE)
        other = self.bridge / "sessions" / ("13-" + "b" * 32) / "status.json"
        live_refresh.write_json(other, self.status | {"session": "b" * 32, "pid": 13})
        pending, message = live_refresh.pump(self.pending, self.bridge, 1000)
        self.assertNotIn("request_id", pending)
        self.assertIn("여러 개", message)
        self.assertFalse((self.bridge / "requests").exists())

    def test_faulted_bridge_still_delivers_failure_and_never_resubmits(self):
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
        self.connect(available=False, reason="scan_timeout_restart_required")
        live_refresh.write_json(self.directory / "responses" / (pending["request_id"] + ".json"),
            {"protocol": 1, "profile": live_refresh.PROFILE, "session": self.session, "id": pending["request_id"], "status": "failed", "reason": "scan_timeout"})
        next_pending, message = live_refresh.pump(pending, self.bridge, 1001)
        self.assertIsNone(next_pending)
        self.assertIn("파일 저장 상태와 별개", message)
        self.assertEqual(len(list((self.bridge / "requests").rglob("*.json"))), 1)
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1001)
        self.assertNotIn("request_id", pending)

    def test_new_process_and_response_timeout_are_not_silently_replayed(self):
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
        self.connect(heartbeat=1261)
        self.assertIsNone(live_refresh.pump(pending, self.bridge, 1261)[0])
        self.assertEqual(len(list((self.bridge / "requests").rglob("*.json"))), 1)
        self.directory.joinpath("status.json").unlink()
        other = self.bridge / "sessions" / ("13-" + "b" * 32) / "status.json"
        live_refresh.write_json(other, self.status | {"session": "b" * 32, "pid": 13})
        self.assertIsNone(live_refresh.pump(pending, self.bridge, 1261)[0])

    def test_no_pending_work_never_invokes_game_refresh(self):
        self.assertIsNone(live_refresh.pump(None, self.bridge, 1000)[0])
        self.assertFalse((self.bridge / "requests").exists())

    def test_old_plugin_cannot_receive_new_requests_after_the_idle_bug_fix(self):
        for version in ("0.2.0", "0.2.1", "", "unknown"):
            self.connect(plugin_version=version)
            pending, message = live_refresh.pump(self.pending, self.bridge, 1000)
            self.assertNotIn("request_id", pending)
            self.assertIn("업데이트 필요", message)
            self.assertFalse((self.bridge / "requests").exists())

    def test_pre_execution_expiry_is_not_reported_as_executed_or_file_save_success(self):
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
        live_refresh.write_json(self.directory / "responses" / (pending["request_id"] + ".json"),
            {"protocol": 1, "profile": live_refresh.PROFILE, "session": self.session, "id": pending["request_id"],
             "status": "failed", "reason": "idle_wait_timeout:game_busy", "execution": {"started": False, "rescan_attempts": 0}})
        result, message = live_refresh.pump(pending, self.bridge, 1001)
        self.assertIsNone(result)
        self.assertIn("실행 안 됨", message)
        self.assertNotIn("파일 저장은 완료", message)
        self.assertIn("별개", message)

    def test_original_report_failure_reason_is_explained_without_claiming_a_refresh(self):
        message = live_refresh.failure_description({"reason": "invalid_or_expired_request"})
        self.assertIn("실행 안 됨", message)
        self.assertIn("실행 전에", message)
        self.assertNotIn("처리 완료", message)

    def test_waiting_shows_scan_progress_instead_of_the_same_generic_message(self):
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
        self.connect(stage="scanning")
        self.assertIn("경로 재검색", live_refresh.pump(pending, self.bridge, 1001)[1])
        self.connect(stage="reloading")
        self.assertIn("게임 화면 갱신", live_refresh.pump(pending, self.bridge, 1001)[1])

    def test_complete_label_requires_actual_execution_and_callback_evidence(self):
        pending, _ = live_refresh.pump(self.pending, self.bridge, 1000)
        for evidence in ({}, {"started": False, "rescan_attempts": 0, "completion_callbacks": 0, "cache_and_panel_attempts": 0},
                         {"started": True, "rescan_attempts": 1, "completion_callbacks": 0, "cache_and_panel_attempts": 1}):
            live_refresh.write_json(self.directory / "responses" / (pending["request_id"] + ".json"),
                {"protocol": 1, "profile": live_refresh.PROFILE, "session": self.session, "id": pending["request_id"],
                 "status": "refreshed", "execution": evidence})
            result, message = live_refresh.pump(pending, self.bridge, 1001)
            self.assertIsNone(result)
            self.assertNotIn("처리 완료", message)
            self.assertIn("실행 기록", message)


if __name__ == "__main__":
    unittest.main()
