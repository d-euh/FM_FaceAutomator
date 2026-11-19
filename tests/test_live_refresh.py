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
                       "heartbeat": 1000, "available": True, "stage": "idle", "reason": "idle"}
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
                    "id": pending["request_id"], "status": "refreshed"}
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
        self.assertIn("파일 저장은 완료", message)
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


if __name__ == "__main__":
    unittest.main()
