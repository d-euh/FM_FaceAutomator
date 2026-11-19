import json
from pathlib import Path
import tempfile
import unittest

from diagnostics import export_bundle
from engine import DEFAULTS, Engine
from live_refresh import write_json


class DiagnosticBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = DEFAULTS | {"source": str(self.root / "career.fm"), "state_dir": str(self.root / "state"),
                                  "additional_instructions": "SECRET_CUSTOM_DIRECTION", "codex": "SECRET_EXECUTABLE"}
        self.bridge = self.root / "bridge"
        self.output = self.root / "out" / "live-refresh-report.json"

    def export(self):
        export_bundle(self.output, root=self.root, config=self.config, bridge=self.bridge)
        return json.loads(self.output.read_text(encoding="utf-8"))

    def test_bundle_contains_live_execution_and_queue_error_without_prompts_or_images(self):
        session = self.bridge / "sessions" / "12-session"
        write_json(session / "status.json", {"plugin_version": "0.2.2", "reason": "game_busy"})
        write_json(session / "responses" / "id.json", {"reason": "idle_wait_timeout:game_busy", "execution": {"started": False}})
        engine = Engine(self.config)
        try:
            with engine.db:
                engine.db.execute("INSERT INTO jobs(id,player_id,data,status,created,note) VALUES (1,'123','{}','failed',1,?)", ("저장 중인 파일입니다. 다음 점검 때 다시 읽습니다.",))
                engine.db.execute("INSERT INTO job_custom(job_id,options) VALUES (1,?)", ('{"additional_instructions":"SECRET_CUSTOM_DIRECTION"}',))
                engine.setmeta("live_refresh_status", "게임 갱신 실행 안 됨")
                engine.setmeta("live_refresh_pending", '{"request_id":"test-id"}')
        finally:
            engine.close()
        folder = self.root / "state" / "jobs" / "1-abcd1234"
        write_json(folder / "reply.json", {"status": "generated", "reason": "SECRET_REPLY_TEXT"})
        (folder / "portrait.png").write_bytes(b"SECRET_IMAGE_BYTES")
        (folder / "prompt.txt").write_text("SECRET_PROMPT")
        original = (self.root / "state" / "queue.sqlite").read_bytes()
        report = self.export()
        self.assertEqual(report["sessions"][0]["responses"][0]["execution"], {"started": False})
        self.assertEqual(report["jobs"][0]["status"], "failed")
        self.assertTrue(report["jobs"][0]["has_custom"])
        self.assertEqual(report["jobs"][0]["retained_outputs"][0]["reply_status"], "generated")
        self.assertIn("test-id", report["workspace"]["live_refresh_pending"])
        self.assertNotIn("SECRET", self.output.read_text())
        self.assertEqual((self.root / "state" / "queue.sqlite").read_bytes(), original)

    def test_export_still_works_without_plugin_database_or_saved_config(self):
        export_bundle(self.output, root=self.root, bridge=self.bridge)
        report = json.loads(self.output.read_text())
        self.assertEqual(report["sessions"], [])
        self.assertIn("live_plugin_session_not_found", report["errors"])
        self.assertFalse((self.root / "state").exists())

    def test_corrupt_session_does_not_hide_other_responses_or_static_header(self):
        session = self.bridge / "sessions" / "12-session"
        session.mkdir(parents=True)
        (session / "status.json").write_text("{")
        write_json(session / "responses" / "id.json", {"status": "failed"})
        game = self.root / "game"
        write_json(self.root / ".refresh-diagnostics.json", {"game": str(game)})
        write_json(game / "BepInEx/diagnostics/FMFaceRefresh/refresh-diagnostic.json",
                   {"plugin_version": "0.1.0", "mode": "metadata_only", "candidate_assemblies": ["HUGE_METHOD_LIST"]})
        report = self.export()
        self.assertIn("status_error", report["sessions"][0])
        self.assertEqual(report["sessions"][0]["responses"], [{"status": "failed"}])
        self.assertEqual(report["metadata"]["mode"], "metadata_only")
        self.assertNotIn("candidate_assemblies", report["metadata"])
