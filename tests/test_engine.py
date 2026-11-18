import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image
from engine import DEFAULTS, Engine, LEGACY_STYLE, build_prompt, in_scope, load_config, normalise, process_lock, read_source, request_options, validate_png, write_atomic
from gunzo import LAYOUT, render_gunzo


def snapshot(club="10", player="900001", identity=100, date="2027-07-01"):
    return normalise({"game_date": date, "managed_club_ids": ["20"], "players": [
        {"id": player, "uid": identity, "birth_date": "2006-01-01", "name": "Player $(no shell)",
         "age": 21, "club_id": club, "club_name": "Club " + str(club)}]})


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update({key: str(self.root / key) for key in ("state_dir", "portraits_dir", "kits_dir", "pack_dir")})
        self.c.update(source=str(self.root / "career.json"), all_players=True,
                      settle_seconds=0, cooldown_hours=0, codex=shutil.which("python3") or shutil.which("python"))
        self.e = Engine(self.c)

    def tearDown(self):
        self.e.close()
        self.temp.cleanup()

    def source(self, data):
        write_atomic(self.c["source"], json.dumps(data).encode())

    def transfer(self, club="20"):
        self.e.ingest(snapshot())
        after = snapshot(club, date="2027-07-02")
        self.source(after)
        self.e.ingest(read_source(self.c))
        return self.e.jobs()[0]["id"]

    def refs(self):
        for key, name in (("portraits_dir", "900001.png"), ("kits_dir", "20.png")):
            path = Path(self.c[key]) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (256, 256), "gray").save(path)

    def good_runner(self, cmd, **kwargs):
        self.assertFalse(kwargs["shell"])
        self.assertEqual(cmd[-1], "-")
        self.assertNotIn("$(no shell)", " ".join(cmd))
        directory = Path(cmd[cmd.index("--cd") + 1])
        Image.new("RGB", (512, 512), "gray").save(directory / "portrait.png")
        (directory / "reply.json").write_text(json.dumps({"status": "generated", "reason": "ok"}))
        return SimpleNamespace(returncode=0)

    def test_first_read_is_baseline(self):
        self.assertEqual(self.e.ingest(snapshot()), 0)
        self.assertEqual(self.e.jobs(), [])

    def test_transfer_is_deduplicated(self):
        self.transfer()
        self.e.ingest(snapshot("20", date="2027-07-02"))
        self.assertEqual(len(self.e.jobs()), 1)

    def test_latest_transfer_supersedes_old(self):
        self.transfer()
        self.e.ingest(snapshot("30", date="2027-07-03"))
        self.assertEqual([j["status"] for j in self.e.jobs()], ["pending", "superseded"])
        self.assertEqual(json.loads(self.e.next_job(time.time())["data"])["club_id"], "30")

    def test_scope_union_and_exclusion(self):
        c = copy.deepcopy(DEFAULTS)
        row = snapshot("20")["players"][0]
        self.assertTrue(in_scope(row, c, ["20"]))
        self.assertFalse(in_scope(row, c, []))
        c["player_ids"] = ["900001"]
        self.assertTrue(in_scope(row, c, []))
        c["exclude_player_ids"] = ["900001"]
        self.assertFalse(in_scope(row, c, ["20"]))
        c["exclude_player_ids"] = []
        c["max_age"] = 20
        self.assertFalse(in_scope(row, c, ["20"]))

    def test_free_agent_supersedes_pending(self):
        self.transfer()
        self.e.ingest(snapshot(None, date="2027-07-03"))
        self.assertEqual(self.e.jobs()[0]["status"], "superseded")
        self.assertIsNone(self.e.next_job(time.time()))

    def test_zero_club_is_valid(self):
        data = snapshot(0)
        self.assertEqual(data["players"][0]["club_id"], "0")
        self.assertTrue(in_scope(data["players"][0], self.c, []))

    def test_reused_id_supersedes_old_person(self):
        self.transfer()
        self.e.ingest(snapshot("20", identity=200, date="2027-07-03"))
        self.assertEqual(self.e.jobs()[1]["status"], "superseded")

    def test_past_save_is_rejected(self):
        self.transfer()
        with self.assertRaisesRegex(ValueError, "과거"):
            self.e.ingest(snapshot(date="2026-01-01"))

    def test_scope_change_stops_pending(self):
        self.transfer()
        self.c["all_players"] = False
        self.c["my_club_only"] = False
        self.assertIsNone(self.e.next_job(time.time()))

    def test_settle_and_cooldown_and_budget(self):
        self.transfer()
        now = time.time()
        self.c["settle_seconds"] = 30
        self.assertIsNone(self.e.next_job(now))
        self.c["settle_seconds"] = 0
        self.assertIsNotNone(self.e.next_job(now))
        with self.e.db:
            self.e.db.execute("INSERT INTO jobs(player_id,data,status,created,started) VALUES (?,?,'applied',?,?)", ("900001", "{}", now-5, now-5))
        self.c["cooldown_hours"] = 1
        self.assertIsNone(self.e.next_job(now))
        self.c["cooldown_hours"] = 0
        self.c["daily_limit"] = 1
        with self.e.db:
            self.e.db.execute("INSERT INTO attempts VALUES (?,1)", (now-2,))
        self.assertIsNone(self.e.next_job(now))
        self.assertIsNotNone(self.e.next_job(now+86401))

    def test_missing_refs_are_blocked_without_call(self):
        self.transfer()
        def forbidden(*args, **kwargs):
            self.fail("missing refs must never invoke Codex")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_generation_apply_backup_restore(self):
        jid = self.transfer()
        self.refs()
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        with Image.open(self.e.jobs()[0]["artifact"]) as image:
            self.assertEqual(image.size, (350, 350))
            self.assertEqual(image.info["PlayerName"], "PLAYER $(NO SHELL)")
        pack = Path(self.c["pack_dir"])
        maps = ET.parse(pack / "config.xml").findall("./list/record")
        self.assertEqual(maps[0].attrib["to"], "graphics/pictures/person/900001/portrait")
        self.assertTrue((pack / (maps[0].attrib["from"] + ".png")).is_file())
        backup = next((pack / "backups").glob("*.xml"))
        self.e.restore(backup)
        self.assertEqual(ET.parse(pack / "config.xml").findall("./list/record"), [])

    def test_transfer_during_generation_never_applied(self):
        self.transfer()
        self.refs()
        self.c["auto_apply"] = True
        def moved(cmd, **kwargs):
            result = self.good_runner(cmd, **kwargs)
            self.source(snapshot("30", date="2027-07-03"))
            return result
        self.e.run_one(moved)
        statuses = [j["status"] for j in self.e.jobs()]
        self.assertIn("superseded", statuses)
        self.assertFalse((Path(self.c["pack_dir"]) / "config.xml").exists())

    def test_unavailable_tool_never_falls_back(self):
        self.transfer()
        self.refs()
        def unavailable(cmd, **kwargs):
            folder = Path(cmd[cmd.index("--cd")+1])
            (folder / "reply.json").write_text('{"status":"unavailable","reason":"no image tool"}')
            return SimpleNamespace(returncode=0)
        self.e.run_one(unavailable)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertIsNone(self.e.jobs()[0]["artifact"])

    def test_timeout_is_failed_without_auto_retry(self):
        self.transfer()
        self.refs()
        def timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 1)
        self.e.run_one(timeout)
        self.assertEqual(self.e.jobs()[0]["status"], "failed")
        self.assertFalse(self.e.run_one(timeout))

    def test_existing_pack_is_not_overwritten(self):
        jid = self.transfer()
        self.refs()
        pack = Path(self.c["pack_dir"])
        pack.mkdir()
        (pack / "config.xml").write_text("user file")
        def forbidden(*args, **kwargs):
            self.fail("Do not invoke Codex when saving would overwrite an existing pack")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertEqual((pack / "config.xml").read_text(), "user file")

    def test_explicit_regen_mapping(self):
        jid = self.transfer()
        self.refs()
        self.c["regen_player_ids"] = ["900001"]
        self.e.run_one(self.good_runner)
        target = ET.parse(Path(self.c["pack_dir"]) / "config.xml").find("./list/record").get("to")
        self.assertEqual(target, "graphics/pictures/person/r-900001/portrait")

    def test_interrupted_run_requires_explicit_retry(self):
        jid = self.transfer()
        self.e.update(jid, "running")
        with process_lock(self.c["state_dir"]):
            self.e.recover()
        self.assertEqual(self.e.jobs()[0]["status"], "interrupted")
        self.assertIsNone(self.e.next_job(time.time()))
        self.e.retry(jid)
        self.assertEqual(self.e.next_job(time.time())["id"], jid)

    def test_empty_and_duplicate_input_rejected(self):
        with self.assertRaises(ValueError):
            normalise({"players": []})
        data = snapshot()
        data["players"].append(data["players"][0])
        with self.assertRaises(ValueError):
            normalise(data)

    def test_os_lock_blocks_second_worker(self):
        with process_lock(self.c["state_dir"]):
            with self.assertRaises(OSError):
                with process_lock(self.c["state_dir"]):
                    pass

    def test_real_fmsave_api_adapter_with_mock_records(self):
        self.c["source"] = str(self.root / "adapter.fm")
        Path(self.c["source"]).write_bytes(b"mock save, not an actual FM fixture")
        fake = SimpleNamespace(
            info=SimpleNamespace(game="FM27", known_build=True, build="27.0.0+2486695", game_date="2027-01-01"),
            clubs=lambda: [SimpleNamespace(uid=0, unique_id=20)],
            managed_clubs=lambda: [SimpleNamespace(club_uid=0)],
            players=lambda: [SimpleNamespace(unique_id=900001, uid=100, name="Player", birth_date="2006-01-01", age=21, club_uid=0, club_name="Club")])
        with patch("fmsave.open") as opened:
            opened.return_value.__enter__.return_value = fake
            data = read_source(self.c)
            self.assertEqual(data["players"][0]["club_id"], "20")
            self.assertEqual(data["managed_club_ids"], ["20"])
            self.assertNotEqual(Path(opened.call_args.args[0]), Path(self.c["source"]))
            self.assertTrue(opened.call_args.kwargs["strict"])

    def test_reported_fm27_271_build_reads_even_when_known_build_is_false(self):
        self.c["source"] = str(self.root / "fm27-271.fm")
        Path(self.c["source"]).write_bytes(b"mock FM27 27.1 save")
        fake = SimpleNamespace(
            info=SimpleNamespace(game="FM27", known_build=False, build="27.1.0+2505117", game_date="2027-01-01"),
            clubs=lambda: [SimpleNamespace(uid=0, unique_id=20)],
            managed_clubs=lambda: [SimpleNamespace(club_uid=0)],
            players=lambda: [SimpleNamespace(unique_id=900001, uid=100, name="Player", birth_date="2006-01-01", age=21, club_uid=0, club_name="Club")])
        with patch("fmsave.open") as opened:
            opened.return_value.__enter__.return_value = fake
            data = read_source(self.c)
            self.assertEqual(data["build"], "27.1.0+2505117")
            self.assertEqual(data["reader_mode"], "compatible")
            self.assertEqual(data["players"][0]["club_id"], "20")
            self.assertTrue(opened.call_args.kwargs["strict"])

    def test_unrecognised_future_build_is_still_rejected(self):
        self.c["source"] = str(self.root / "future.fm")
        Path(self.c["source"]).write_bytes(b"mock future save")
        with patch("fmsave.open") as opened:
            fake = opened.return_value.__enter__.return_value
            fake.info = SimpleNamespace(game="FM27", known_build=False, build="27.9.0+9999999")
            with self.assertRaisesRegex(ValueError, "검증 대상 외 게임 빌드"):
                read_source(self.c)
            fake.clubs.assert_not_called()

    def test_old_save_reader_gives_upgrade_instructions_before_parsing(self):
        self.c["source"] = str(self.root / "old-reader.fm")
        Path(self.c["source"]).write_bytes(b"mock save")
        with patch("engine.package_version", return_value="0.12.5"), patch("fmsave.open") as opened:
            with self.assertRaisesRegex(ValueError, "setup_windows.bat"):
                read_source(self.c)
            opened.assert_not_called()

    def test_compatible_build_does_not_suppress_reader_integrity_errors(self):
        self.c["source"] = str(self.root / "inconsistent.fm")
        Path(self.c["source"]).write_bytes(b"mock inconsistent save")
        with patch("fmsave.open") as opened:
            fake = opened.return_value.__enter__.return_value
            fake.info = SimpleNamespace(game="FM27", known_build=False, build="27.1.0+2505117")
            fake.clubs.side_effect = ValueError("club integrity check failed")
            with self.assertRaisesRegex(ValueError, "club integrity check failed"):
                read_source(self.c)
            self.assertTrue(opened.call_args.kwargs["strict"])
            self.assertEqual(self.e.jobs(), [])

    def test_invalid_image_rejected(self):
        path = self.root / "bad.png"
        path.write_text("not an image")
        with self.assertRaises(Exception):
            validate_png(path)
        Image.new("RGB", (256, 128)).save(path)
        with self.assertRaises(ValueError):
            validate_png(path)

    def test_no_directions_preserve_hair_expression_pose(self):
        prompt = build_prompt(self.c, snapshot()["players"][0])
        self.assertIn("Preserve the original hair, expression and pose", prompt)
        self.assertIn("portrait.png", prompt)
        self.assertIn("EXACT 350x350", prompt)
        self.assertIn("Do not draw any name", prompt)

    def test_common_directions_remove_pose_preservation(self):
        self.c["additional_instructions"] = "골을 넣고 활짝 웃으며 오른팔을 들어주세요."
        prompt = build_prompt(self.c, snapshot()["players"][0])
        self.assertNotIn("Preserve the original hair, expression and pose", prompt)
        self.assertIn(self.c["additional_instructions"], prompt)
        self.assertIn("preserve facial identity", prompt)

    def test_player_directions_and_caption_override(self):
        row = snapshot()["players"][0]
        self.c["additional_instructions"] = "Calm expression"
        self.c["player_overrides"] = {row["id"]: {"identity": row["identity"], "display_name": "Lisandro Martínez", "additional_instructions": "Laughing, arms raised"}}
        options = request_options(self.c, row)
        self.assertEqual(options["display_name"], "Lisandro Martínez")
        prompt = build_prompt(self.c, row)
        self.assertIn("take priority over the common", prompt)
        self.assertIn("Laughing, arms raised", prompt)
        self.assertNotIn("Preserve the original hair, expression and pose", prompt)
        self.c["player_overrides"][row["id"]]["identity"] = "old person"
        self.assertEqual(request_options(self.c, row)["personal"], "")

    def test_old_config_migrates_style_and_mandatory_apply(self):
        path = self.root / "config.json"
        path.write_text(json.dumps({"style": LEGACY_STYLE, "auto_apply": False}), encoding="utf-8")
        config = load_config(path)
        self.assertEqual(config["style"], DEFAULTS["style"])
        self.assertNotIn("auto_apply", config)
        self.assertEqual(config["additional_instructions"], "")

    def test_gunzo_renders_exact_size_unicode_name_and_visible_letters(self):
        source = self.root / "portrait.png"
        Image.new("RGB", (1024, 1024), (70, 90, 120)).save(source)
        final = self.root / "card.png"
        write_atomic(final, render_gunzo(source, "홍길동 MARTÍNEZ"))
        validate_png(final)
        with Image.open(final) as card:
            self.assertEqual(card.size, (350, 350))
            self.assertEqual(card.info["PlayerName"], "홍길동 MARTÍNEZ")
            self.assertEqual(card.info["Layout"], LAYOUT)
            self.assertEqual(card.getpixel((0, 0))[3], 0)
            # White glyphs really are painted into the pixels, not just metadata.
            self.assertGreater(card.crop((16, 290, 334, 335)).getextrema()[0][1], 245)

    def test_final_size_is_strict_and_caption_processing_is_required(self):
        path = self.root / "plain.png"
        Image.new("RGB", (350, 350)).save(path)
        with self.assertRaisesRegex(ValueError, "선수 이름"):
            validate_png(path)
        Image.new("RGB", (349, 349)).save(path)
        with self.assertRaisesRegex(ValueError, "350"):
            validate_png(path)

    def test_auto_xml_update_is_mandatory_even_for_old_false_setting(self):
        self.transfer()
        self.refs()
        self.c["auto_apply"] = False
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertTrue((Path(self.c["pack_dir"]) / "config.xml").exists())

    def test_xml_write_failure_keeps_render_and_retry_does_not_call_ai(self):
        jid = self.transfer()
        self.refs()
        def fail_xml(path, data):
            if Path(path).name == "config.xml":
                raise OSError("disk unavailable")
            return write_atomic(path, data)
        with patch("engine.write_atomic", side_effect=fail_xml):
            self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "apply_failed")
        self.assertTrue(Path(self.e.jobs()[0]["artifact"]).is_file())
        self.assertEqual(self.e.enqueue_current(), 0)
        self.e.apply(jid)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 1)

    def test_second_completed_player_extends_xml_without_losing_first(self):
        self.transfer()
        self.refs()
        self.e.run_one(self.good_runner)
        both = snapshot("20", date="2027-07-03")
        both["players"].append(snapshot("10", player="900002", identity=200)["players"][0])
        self.source(both)
        self.e.ingest(read_source(self.c))
        both["players"][1]["club_id"] = "20"
        both["game_date"] = "2027-07-04"
        self.source(both)
        self.e.ingest(read_source(self.c))
        shutil.copyfile(Path(self.c["portraits_dir"])/"900001.png", Path(self.c["portraits_dir"])/"900002.png")
        self.e.run_one(self.good_runner)
        targets = {r.get("to") for r in ET.parse(Path(self.c["pack_dir"])/"config.xml").findall("./list/record")}
        self.assertEqual(targets, {"graphics/pictures/person/900001/portrait", "graphics/pictures/person/900002/portrait"})
        self.assertEqual([j["status"] for j in self.e.jobs()], ["applied", "applied"])

    def test_invalid_template_blocks_before_codex_call(self):
        self.transfer()
        self.refs()
        template = self.root / "template.png"
        Image.new("RGBA", (256, 256)).save(template)
        self.c["frame_template"] = str(template)
        def forbidden(*args, **kwargs):
            self.fail("invalid template must be rejected before image generation")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_bad_ai_image_does_not_create_config(self):
        self.transfer()
        self.refs()
        def wrong_size(cmd, **kwargs):
            result = self.good_runner(cmd, **kwargs)
            Image.new("RGB", (256, 256)).save(Path(cmd[cmd.index("--cd")+1])/"portrait.png")
            return result
        self.e.run_one(wrong_size)
        self.assertEqual(self.e.jobs()[0]["status"], "failed")
        self.assertFalse((Path(self.c["pack_dir"])/"config.xml").exists())

    def test_rendered_job_resumes_mapping_without_another_ai_request(self):
        jid = self.transfer()
        portrait = self.root / "raw.png"
        Image.new("RGB", (512, 512)).save(portrait)
        output = self.root / "finished.png"
        write_atomic(output, render_gunzo(portrait, "Already rendered"))
        self.e.update(jid, "generated", artifact=str(output))
        def forbidden(*args, **kwargs):
            self.fail("completed artwork must be resumed without another Codex request")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")

    def test_existing_xml_packs_are_used_and_regen_target_is_preserved(self):
        self.transfer()
        self.refs()
        faces, kits = Path(self.c["portraits_dir"]), Path(self.c["kits_dir"])
        (faces / "900001.png").rename(faces / "named-face.jpg.png")
        (kits / "20.png").rename(kits / "club-shirt.png")
        (faces / "config.xml").write_text('<record><list id="maps"><record from="named-face.jpg" to="graphics/pictures/person/r-900001/portrait"/></list></record>')
        (kits / "config.xml").write_text('<record><list id="maps"><record from="club-shirt" to="graphics/pictures/team/20/kits/home"/></list></record>')
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        target = ET.parse(Path(self.c["pack_dir"])/"config.xml").find("./list/record").get("to")
        self.assertEqual(target, "graphics/pictures/person/r-900001/portrait")


if __name__ == "__main__":
    unittest.main()
