import copy
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageFont
from engine import DEFAULTS, Engine, LEGACY_STYLE, build_prompt, detection_messages, game_english_name, in_scope, latin_name, load_config, normalise, process_lock, read_source, request_options, validate_png, write_atomic
from gunzo import LAYOUT, name_font, render_gunzo
from scope_rules import DEFAULT_SCOPE


def snapshot(club="10", player="900001", identity=100, date="2027-07-01"):
    return normalise({"game_date": date, "managed_club_ids": ["20"], "players": [
        {"id": player, "uid": identity, "birth_date": "2006-01-01", "name": "Player $(no shell)",
         "age": 21, "club_id": club, "club_name": "Club " + str(club)}]})


def membership_snapshot(registered="10", contract="10", on_loan=False, date="2027-07-01"):
    data = snapshot(registered, date=date)
    data["players"][0].update(registered_club_id=registered, registered_club_name="Registered " + registered,
                              contract_club_id=contract, contract_club_name="Contract " + contract,
                              on_loan=on_loan, registered_team_id=999)
    return data


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        # Test rendering with an available real font; the requested default
        # font is supplied by the user and is not bundled with these tests.
        for candidate in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "DejaVuSans-Bold.ttf",
                          str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "malgunbd.ttf")):
            try:
                test_font = ImageFont.truetype(candidate, 20).path
                break
            except OSError:
                continue
        else:
            raise RuntimeError("A font is required for the rendering tests")
        self.test_font = self.root / "test-renderer.ttf"
        shutil.copyfile(test_font, self.test_font)
        font_patch = patch("gunzo.default_font_path", return_value=self.test_font)
        font_patch.start()
        self.addCleanup(font_patch.stop)
        self.c = copy.deepcopy(DEFAULTS)
        self.c.update({key: str(self.root / key) for key in ("state_dir", "portraits_dir", "kits_dir", "pack_dir")})
        self.c.update(source=str(self.root / "career.json"), all_players=True,
                      settle_seconds=0, cooldown_hours=0, name_font_path=str(self.test_font),
                      codex=shutil.which("python3") or shutil.which("python"))
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

    def test_departure_scope_survives_refresh_generation_and_application(self):
        self.c["scope_rules"] = copy.deepcopy(DEFAULT_SCOPE) | {"preset": "custom", "clubs": {"680": "outgoing"}}
        self.refs()
        shutil.copyfile(Path(self.c["kits_dir"]) / "20.png", Path(self.c["kits_dir"]) / "602.png")
        self.e.ingest(snapshot("680"))
        after = snapshot("602", date="2027-07-02")
        self.source(after)
        self.assertEqual(self.e.ingest(read_source(self.c)), 1)
        job = self.e.jobs()[0]
        self.assertEqual(json.loads(job["data"])["from_club_id"], "680")
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        latest = json.loads(self.e.meta("latest_result"))
        self.assertEqual(latest["id"], job["id"])
        self.assertTrue(Path(latest["artifact"]).is_file())

    def test_departure_after_free_agent_gap_remembers_selected_source(self):
        self.c["scope_rules"] = copy.deepcopy(DEFAULT_SCOPE) | {"preset": "custom", "clubs": {"680": "outgoing"}}
        self.e.ingest(snapshot("680"))
        self.assertEqual(self.e.ingest(snapshot(None, date="2027-07-02")), 0)
        self.assertEqual(self.e.ingest(snapshot("602", date="2027-07-03")), 1)
        self.assertEqual(json.loads(self.e.jobs()[0]["data"])["from_club_id"], "680")

    def test_editor_contract_only_transfer_is_detected_and_completes(self):
        self.refs()
        self.e.ingest(membership_snapshot())
        after = membership_snapshot(contract="20", date="2027-07-02")
        self.source(after)
        self.assertEqual(self.e.ingest(read_source(self.c)), 1)
        row = json.loads(self.e.jobs()[0]["data"])
        self.assertEqual((row["club_id"], row["club_basis"]), ("20", "contract_change"))
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertEqual(self.e.ingest(after), 0)
        self.assertEqual(json.loads(self.e.db.execute("SELECT data FROM people").fetchone()[0])["club_id"], "20")

    def test_registered_team_change_beats_unchanged_old_contract(self):
        self.e.ingest(membership_snapshot())
        self.assertEqual(self.e.ingest(membership_snapshot(registered="20", contract="10", date="2027-07-02")), 1)
        row = json.loads(self.e.jobs()[0]["data"])
        self.assertEqual((row["club_id"], row["club_basis"]), ("20", "registered_team"))

    def test_active_loan_never_switches_jersey_to_contract_parent(self):
        self.e.ingest(membership_snapshot(registered="20", contract="10", on_loan=True))
        self.assertEqual(self.e.ingest(membership_snapshot(registered="20", contract="30", on_loan=True, date="2027-07-02")), 0)
        row = json.loads(self.e.db.execute("SELECT data FROM people").fetchone()[0])
        self.assertEqual(row["club_id"], "20")

    def test_baseline_contract_disagreement_is_not_guessed_as_transfer(self):
        self.c["player_ids"] = ["900001"]
        baseline = membership_snapshot(contract="20")
        self.assertEqual(self.e.ingest(baseline), 0)
        self.assertEqual(self.e.ingest(baseline), 0)
        summary = json.loads(self.e.meta("detection_summary"))
        self.assertEqual(summary["tracked"][0]["club_id"], "10")
        self.assertEqual(summary["tracked"][0]["contract_club_id"], "20")

    def test_unknown_loan_status_does_not_guess_contract_as_club(self):
        self.e.ingest(membership_snapshot(on_loan=None))
        self.assertEqual(self.e.ingest(membership_snapshot(contract="20", on_loan=None, date="2027-07-02")), 0)

    def test_upgrade_adds_contract_baseline_without_fabricating_past_change(self):
        self.e.ingest(snapshot())
        self.assertEqual(self.e.ingest(membership_snapshot(contract="20")), 0)
        self.assertEqual(self.e.ingest(membership_snapshot(contract="30", date="2027-07-02")), 1)
        self.assertEqual(json.loads(self.e.jobs()[0]["data"])["club_id"], "30")

    def test_diagnostic_distinguishes_transfer_from_scope_filter(self):
        self.c.update(all_players=False, my_club_only=False, club_ids=["10"])
        self.e.ingest(snapshot())
        self.assertEqual(self.e.ingest(snapshot("20", date="2027-07-02")), 0)
        summary = json.loads(self.e.meta("detection_summary"))
        self.assertEqual((summary["club_changes"], summary["filtered"], summary["queued"]), (1, 1, 0))
        self.assertIn("선택한 구단·선수 범위 밖", " ".join(detection_messages(summary)))
        self.assertEqual(json.loads((Path(self.c["state_dir"]) / "latest_detection.json").read_text())["source"], self.c["source"])

    def test_diagnostic_identifies_wrong_player_id(self):
        self.c["player_ids"] = ["29178504"]
        self.e.ingest(snapshot())
        summary = json.loads(self.e.meta("detection_summary"))
        self.assertEqual(summary["missing_player_ids"], ["29178504"])
        self.assertIn("29178504", " ".join(detection_messages(summary)))

    def test_saved_kit_choice_takes_priority_over_random_candidates(self):
        self.refs()
        duplicate = Path(self.c["kits_dir"]) / "another" / "20.png"
        duplicate.parent.mkdir()
        Image.new("RGB", (256, 256), "red").save(duplicate)
        jid = self.transfer()
        with patch.object(self, "good_runner", wraps=self.good_runner) as runner:
            self.c["kit_overrides"] = {"20:home": str(duplicate)}
            self.e.run_one(runner)
            runner.assert_called_once()
            self.assertEqual(self.e.jobs()[0]["status"], "applied")
            folder = Path(runner.call_args.args[0][runner.call_args.args[0].index("--cd") + 1])
            with Image.open(folder / "kit.png") as image:
                self.assertEqual(image.getpixel((0, 0))[:3], (255, 0, 0))

    def test_missing_saved_kit_choice_blocks_without_fallback_or_charge(self):
        self.refs()
        self.transfer()
        self.c["kit_overrides"] = {"20:home": str(self.root / "missing.png")}
        with patch.object(self, "good_runner") as runner:
            self.e.run_one(runner)
            runner.assert_not_called()
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertIn("선택했던 유니폼 파일이 없습니다", self.e.jobs()[0]["note"])
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_saved_kit_choice_is_scoped_to_club_and_variant(self):
        self.refs()
        selected = self.root / "away.png"
        Image.new("RGB", (256, 256), "blue").save(selected)
        self.c["kit_overrides"] = {"20:away": str(selected), "30:home": str(selected)}
        self.assertEqual(self.e.kit_reference("20"), Path(self.c["kits_dir"]) / "20.png")
        self.c["kit_variant"] = "away"
        self.assertEqual(self.e.kit_reference("20"), selected)

    def test_kit_choices_persist_and_resolve_relative_to_config(self):
        path = self.root / "config.json"
        write_atomic(path, json.dumps({"kit_overrides": {"20:home": "custom/kit.png"}}).encode())
        self.assertEqual(load_config(path)["kit_overrides"], {"20:home": str(self.root / "custom/kit.png")})
        write_atomic(path, b'{}')
        self.assertEqual(load_config(path)["kit_overrides"], {})

    def test_invalid_kit_choices_are_rejected(self):
        path = self.root / "config.json"
        for choices in ([], {"20": "kit.png"}, {"20:home": ""}, {"20:home": 1}):
            with self.subTest(choices=choices):
                write_atomic(path, json.dumps({"kit_overrides": choices}).encode())
                with self.assertRaisesRegex(ValueError, "유니폼 선택 설정"):
                    load_config(path)

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
        self.assertEqual(maps[0].attrib["from"], "900001")
        backup = next((pack / "backups").glob("*.xml"))
        self.e.restore(backup)
        self.assertEqual(ET.parse(pack / "config.xml").findall("./list/record"), [])

    def test_watch_baseline_then_transfer_completes_without_manual_queue_actions(self):
        self.refs()
        self.source(snapshot())
        old = time.time() - 10
        os.utime(self.c["source"], (old, old))
        first = self.e.watch_step(self.good_runner)
        self.assertEqual(self.e.jobs(), [])
        self.assertEqual(first["added"], 0)
        self.source(snapshot("20", date="2027-07-02"))
        os.utime(self.c["source"], (old + 1, old + 1))
        second = self.e.watch_step(self.good_runner)
        self.assertEqual(second["added"], 1)
        self.assertTrue(second["processed"])
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertTrue((Path(self.c["pack_dir"]) / "900001.png").is_file())

    def test_watch_skips_save_that_is_still_being_written(self):
        self.source(snapshot())
        self.assertTrue(self.e.watch_step(self.good_runner)["saving"])
        self.assertIsNone(self.e.meta("baseline"))

    def test_save_cadence_records_transfer_waits_and_survives_restart(self):
        self.c["save_update_interval"] = 2
        self.e.close()
        self.e = Engine(self.c)
        self.refs()
        old = time.time() - 100

        def save(data, tick):
            self.source(data)
            os.utime(self.c["source"], (old + tick, old + tick))
            return self.e.watch_step(self.good_runner)

        baseline = save(snapshot(), 0)
        self.assertEqual(baseline["save_updates_pending"], 0)
        self.assertEqual(self.e.jobs(), [])
        # No movement on the second save: the first save's transfer must survive.
        moved = snapshot("20", date="2027-07-02")
        first = save(moved, 1)
        self.assertEqual(first["added"], 1)
        self.assertFalse(first["processed"])
        self.assertEqual(first["save_updates_pending"], 1)
        self.assertEqual(self.e.jobs()[0]["status"], "pending")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)
        for _ in range(3):
            unchanged = self.e.watch_step(self.good_runner)
            self.assertEqual(unchanged["save_updates_pending"], 1)
            self.assertFalse(unchanged["processed"])
        self.e.close()
        self.e = Engine(self.c)
        self.assertFalse(self.e.watch_step(self.good_runner)["processed"])
        second = save(moved, 2)
        self.assertEqual(second["added"], 0)
        self.assertEqual(second["save_updates_pending"], 0)
        self.assertTrue(second["processed"])
        self.assertEqual(self.e.jobs()[0]["status"], "applied")

    def test_save_cadence_drains_multiple_jobs_without_another_save(self):
        self.c["save_update_interval"] = 2
        self.e.close()
        self.e = Engine(self.c)
        self.refs()
        shutil.copyfile(Path(self.c["portraits_dir"]) / "900001.png", Path(self.c["portraits_dir"]) / "900002.png")
        data = snapshot()
        data["players"].extend(snapshot(player="900002", identity=101)["players"])
        old = time.time() - 100
        for tick, club in enumerate(("10", "20", "20")):
            for player in data["players"]:
                player.update(club_id=club, club_name="Club " + club)
            self.source(data)
            os.utime(self.c["source"], (old + tick, old + tick))
            step = self.e.watch_step(self.good_runner)
            self.assertEqual(step["processed"], tick == 2)
        self.assertTrue(self.e.watch_step(self.good_runner)["processed"])
        self.assertEqual([job["status"] for job in self.e.jobs()], ["applied", "applied"])

    def test_zero_daily_limit_allows_more_than_old_default_budget(self):
        self.transfer()
        now = time.time()
        with self.e.db:
            self.e.db.executemany("INSERT INTO attempts VALUES (?,1)", [(now - 1,)] * 100)
        self.assertEqual(self.c["daily_limit"], 0)
        self.assertIsNotNone(self.e.next_job(now))

    def test_save_during_generation_counts_toward_next_batch_and_stops_stale_apply(self):
        self.c["save_update_interval"] = 2
        self.e.close()
        self.e = Engine(self.c)
        self.refs()
        shutil.copyfile(Path(self.c["kits_dir"]) / "20.png", Path(self.c["kits_dir"]) / "30.png")
        old = time.time() - 100

        def save(club, tick):
            self.source(snapshot(club))
            os.utime(self.c["source"], (old + tick, old + tick))

        def moving_runner(cmd, **kwargs):
            result = self.good_runner(cmd, **kwargs)
            save("30", 3)
            return result

        save("10", 0)
        self.e.watch_step(self.good_runner)
        save("20", 1)
        self.assertFalse(self.e.watch_step(self.good_runner)["processed"])
        save("20", 2)
        result = self.e.watch_step(moving_runner)
        self.assertTrue(result["processed"])
        self.assertEqual(result["save_updates_pending"], 1)
        self.assertEqual([j["status"] for j in self.e.jobs()], ["pending", "superseded"])
        self.assertFalse((Path(self.c["pack_dir"]) / "900001.png").exists())
        self.assertFalse(self.e.watch_step(self.good_runner)["processed"])
        save("30", 4)
        self.assertTrue(self.e.watch_step(self.good_runner)["processed"])
        self.assertEqual(self.e.jobs()[0]["status"], "applied")

    def test_preflight_recovers_automatically_but_ai_failures_do_not(self):
        jid = self.transfer()
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.refs()
        self.e.retry_preflight()
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.e.db.execute("UPDATE jobs SET status='blocked',started=? WHERE id=?", (time.time(), jid))
        self.e.db.commit()
        self.e.retry_preflight()
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")

    def test_watch_retries_only_application_after_disk_recovers(self):
        self.refs(); self.transfer()
        def fail_xml(path, data):
            if Path(path).name == "config.xml":
                raise OSError("temporary disk failure")
            return write_atomic(path, data)
        with patch("engine.write_atomic", side_effect=fail_xml):
            self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "apply_failed")
        old = time.time() - 10
        os.utime(self.c["source"], (old, old))
        with patch.object(self, "good_runner") as forbidden:
            self.e.watch_step(forbidden)
            forbidden.assert_not_called()
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 1)

    def test_legacy_xml_only_backup_can_restore_archived_filename(self):
        self.refs(); self.transfer(); self.e.run_one(self.good_runner)
        pack = Path(self.c["pack_dir"])
        old = (pack / "900001.png").read_bytes()
        write_atomic(pack / "900001_1.png", old)
        write_atomic(pack / "config.xml", self.e.mapping_xml({"900001": "900001_1"}))
        backup = pack / "backups" / "old-format.xml"
        write_atomic(backup, (pack / "config.xml").read_bytes())
        self.e.migrate_pack_filenames()
        self.e.restore(backup)
        self.assertEqual((pack / "900001_1.png").read_bytes(), old)
        self.assertEqual(self.e.pack_mapping((pack / "config.xml").read_bytes()), {"900001": "900001_1"})

    def test_legacy_id_job_filename_migrates_without_ai_and_is_idempotent(self):
        self.transfer(); self.refs(); self.e.run_one(self.good_runner)
        pack = Path(self.c["pack_dir"])
        (pack / "900001.png").rename(pack / "900001_1.png")
        write_atomic(pack / "config.xml", self.e.mapping_xml({"900001": "900001_1"}))
        self.assertEqual(self.e.prepare_watch(), 1)
        self.assertEqual((pack / "900001.png").read_bytes(), (pack / "backups/legacy/900001_1.png").read_bytes())
        self.assertFalse((pack / "900001_1.png").exists())
        self.assertEqual(self.e.pack_mapping((pack / "config.xml").read_bytes()), {"900001": "900001"})
        self.assertEqual(self.e.prepare_watch(), 0)
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 1)

    def test_overwriting_id_file_preserves_previous_image_for_restore(self):
        self.transfer(); self.refs(); self.e.run_one(self.good_runner)
        pack = Path(self.c["pack_dir"])
        previous = (pack / "900001.png").read_bytes()
        self.source(snapshot("30", date="2027-07-03"))
        self.e.ingest(read_source(self.c))
        shutil.copyfile(Path(self.c["kits_dir"]) / "20.png", Path(self.c["kits_dir"]) / "30.png")
        def red_runner(cmd, **kwargs):
            result = self.good_runner(cmd, **kwargs)
            folder = Path(cmd[cmd.index("--cd")+1])
            Image.new("RGB", (512, 512), "red").save(folder / "portrait.png")
            return result
        self.e.run_one(red_runner)
        self.assertNotEqual((pack / "900001.png").read_bytes(), previous)
        backup = next((pack / "backups").glob("config-before-2-*.xml"))
        self.e.restore(backup)
        self.assertEqual((pack / "900001.png").read_bytes(), previous)

    def test_english_name_uses_game_pool_before_localised_display_name(self):
        person = SimpleNamespace(name="제드 스펜스", common_name="제드 스펜스", full_name="Djed Spence")
        self.assertEqual(game_english_name(person), "Djed Spence")
        row = snapshot()["players"][0] | {"name": "제드 스펜스", "english_name": game_english_name(person)}
        self.assertEqual(request_options(self.c, row)["display_name"], "Djed Spence")
        self.assertTrue(latin_name("Lisandro Martínez"))
        self.assertFalse(latin_name("제드 Spence"))

    def test_missing_latin_name_is_resolved_in_same_codex_call(self):
        self.refs(); self.transfer()
        localised = snapshot("20", date="2027-07-02")
        localised["players"][0]["name"] = "제드 스펜스"
        self.source(localised)
        def english_runner(cmd, **kwargs):
            result = self.good_runner(cmd, **kwargs)
            folder = Path(cmd[cmd.index("--cd")+1])
            (folder / "reply.json").write_text(json.dumps({"status":"generated", "reason":"ok", "english_name":"Djed Spence"}))
            return result
        self.e.run_one(english_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        with Image.open(Path(self.c["pack_dir"]) / "900001.png") as image:
            self.assertEqual(image.info["PlayerName"], "DJED SPENCE")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 1)

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

    def test_malformed_existing_pack_is_not_overwritten(self):
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

    def test_existing_mixed_pack_keeps_arbitrary_names_and_unrelated_xml(self):
        self.transfer(); self.refs()
        pack = Path(self.c["pack_dir"]); pack.mkdir()
        (pack / "photos").mkdir()
        Image.new("RGB", (120, 120), "blue").save(pack / "photos/old portrait.jpg")
        Image.new("RGB", (120, 120), "green").save(pack / "unrelated.png")
        original = (pack / "photos/old portrait.jpg").read_bytes()
        unrelated = (pack / "unrelated.png").read_bytes()
        xml = b'''<record custom="preserve"><!--keep comment--><boolean id="custom" value="true"/><list id="maps" custom="list"><record from="photos/old portrait.jpg" to="graphics/pictures/person/900001/portrait" custom="old"/><record from="unrelated" to="graphics/pictures/person/700/portrait"/><record from="shirt_home" to="graphics/pictures/team/680/kits/home"/></list></record>'''
        write_atomic(pack / "config.xml", xml)
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        root = ET.parse(pack / "config.xml").getroot()
        self.assertEqual(root.get("custom"), "preserve")
        self.assertEqual(root.find("./boolean").get("id"), "custom")
        self.assertEqual(root.find("./list").get("custom"), "list")
        records = root.findall("./list/record")
        self.assertEqual([r.get("from") for r in records], ["unrelated", "shirt_home", "900001"])
        self.assertIn(b"keep comment", (pack / "config.xml").read_bytes())
        self.assertEqual((pack / "photos/old portrait.jpg").read_bytes(), original)
        self.assertEqual((pack / "unrelated.png").read_bytes(), unrelated)
        backup = next((pack / "backups").glob("config-before-*.xml"))
        self.assertEqual(backup.read_bytes(), xml)
        self.e.restore(backup)
        self.assertFalse((pack / "900001.png").exists())
        restored = ET.parse(pack / "config.xml").findall("./list/record")
        self.assertEqual(restored[0].get("from"), "photos/old portrait.jpg")
        self.assertEqual(restored[0].get("custom"), "old")

    def test_existing_numeric_image_without_xml_is_backed_up_and_restored(self):
        self.transfer(); self.refs()
        pack = Path(self.c["pack_dir"]); pack.mkdir()
        Image.new("RGB", (128, 160), "orange").save(pack / "900001.png")
        before = (pack / "900001.png").read_bytes()
        (pack / "readme.txt").write_text("existing pack")
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertNotEqual((pack / "900001.png").read_bytes(), before)
        self.e.restore(next((pack / "backups").glob("config-before-*.xml")))
        self.assertEqual((pack / "900001.png").read_bytes(), before)
        self.assertEqual((pack / "readme.txt").read_text(), "existing pack")

    def test_source_and_output_can_be_the_same_existing_pack(self):
        self.transfer(); self.refs()
        self.c["pack_dir"] = self.c["portraits_dir"]
        pack = Path(self.c["pack_dir"])
        before = (pack / "900001.png").read_bytes()
        write_atomic(pack / "config.xml", self.e.mapping_xml({"900001": "900001"}))
        self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "applied")
        self.assertTrue((pack / ".fm-face-shared").exists())
        self.assertEqual(self.e.asset_catalog(str(pack), refresh=True).face("900001")[0], pack / "900001.png")
        backup = next((pack / "backups").glob("config-before-*.xml"))
        self.e.restore(backup)
        self.assertEqual((pack / "900001.png").read_bytes(), before)

    def test_existing_pack_can_be_reused_from_another_state(self):
        self.transfer(); self.refs(); self.e.run_one(self.good_runner)
        second = Engine(self.c | {"state_dir": str(self.root / "second-state")})
        try:
            second.ingest(read_source(self.c)); second.enqueue_current()
            self.assertEqual(second.prepare_watch(), 0)
            second.run_one(self.good_runner)
            self.assertEqual(second.jobs()[0]["status"], "applied")
        finally:
            second.close()

    def test_unrelated_alias_of_destination_blocks_before_ai(self):
        self.transfer(); self.refs()
        pack = Path(self.c["pack_dir"]); pack.mkdir()
        write_atomic(pack / "config.xml", self.e.mapping_xml({"700": "900001"}))
        with patch.object(self, "good_runner") as runner:
            self.e.run_one(runner)
            runner.assert_not_called()
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertIn("다른 매핑", self.e.jobs()[0]["note"])

    def test_xml_failure_rolls_back_existing_image(self):
        self.transfer(); self.refs()
        pack = Path(self.c["pack_dir"]); pack.mkdir()
        Image.new("RGB", (128, 128), "blue").save(pack / "900001.png")
        before = (pack / "900001.png").read_bytes()
        xml = self.e.mapping_xml({"900001": "900001"}); write_atomic(pack / "config.xml", xml)
        def fail_xml(path, data):
            if Path(path) == pack / "config.xml":
                raise OSError("disk failure")
            return write_atomic(path, data)
        with patch("engine.write_atomic", side_effect=fail_xml):
            self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "apply_failed")
        self.assertEqual((pack / "900001.png").read_bytes(), before)
        self.assertEqual((pack / "config.xml").read_bytes(), xml)
        self.e.apply(self.e.jobs()[0]["id"])
        self.assertEqual(self.e.jobs()[0]["status"], "applied")

    def test_restore_one_player_keeps_later_unrelated_player_and_xml(self):
        self.transfer(); self.refs(); self.e.run_one(self.good_runner)
        pack = Path(self.c["pack_dir"])
        backup = next((pack / "backups").glob("config-before-*.xml"))
        xml = ET.parse(pack / "config.xml").getroot()
        ET.SubElement(xml.find("./list"), "record", {"from": "second-photo", "to": "graphics/pictures/person/700/portrait"})
        write_atomic(pack / "config.xml", ET.tostring(xml))
        (pack / "second-photo.png").write_bytes(b"unrelated bytes")
        self.e.restore(backup)
        records = ET.parse(pack / "config.xml").findall("./list/record")
        self.assertEqual([r.get("from") for r in records], ["second-photo"])
        self.assertEqual((pack / "second-photo.png").read_bytes(), b"unrelated bytes")

    def test_shared_pack_lock_blocks_mutation_without_new_ai_call(self):
        self.transfer(); self.refs()
        self.e.run_one(self.good_runner)
        jid = self.e.jobs()[0]["id"]
        self.e.update(jid, "generated")
        pack = Path(self.c["pack_dir"])
        before = (pack / "config.xml").read_bytes()
        with process_lock(pack / ".fm-face-lock"):
            self.e.run_one(self.good_runner)
        self.assertEqual(self.e.jobs()[0]["status"], "apply_failed")
        self.assertEqual((pack / "config.xml").read_bytes(), before)
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 1)

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

    def test_fmsave_adapter_keeps_registered_and_current_contract_clubs(self):
        self.c["source"] = str(self.root / "editor.fm")
        Path(self.c["source"]).write_bytes(b"mock save")
        player = SimpleNamespace(unique_id=29178504, uid=100, name="Djed Spence", birth_date="2000-08-09", age=27,
                                 club_uid=1, club_name="Manchester United", on_loan=False, team_id=44,
                                 contract=SimpleNamespace(club_uid=2, club_name="Arsenal"))
        fake = SimpleNamespace(info=SimpleNamespace(game="FM27", known_build=True, build="27.0.0+2486695", game_date="2027-07-01"),
                               clubs=lambda: [SimpleNamespace(uid=1, unique_id=680, name="Manchester United"),
                                              SimpleNamespace(uid=2, unique_id=602, name="Arsenal")],
                               managed_clubs=lambda: [], players=lambda: [player])
        with patch("fmsave.open") as opened:
            opened.return_value.__enter__.return_value = fake
            row = read_source(self.c)["players"][0]
        self.assertEqual((row["registered_club_id"], row["contract_club_id"], row["on_loan"]), ("680", "602", False))

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

    def test_advanced_defaults_and_legacy_limit_migration(self):
        path = self.root / "config.json"
        path.write_text("{}")
        config = load_config(path)
        self.assertEqual(config["save_update_interval"], 1)
        self.assertFalse(config["initial_generation"])
        for key in ("max_age", "daily_limit", "cooldown_hours", "settle_seconds"):
            self.assertEqual(config[key], 0)
        old = {"daily_limit": 20, "cooldown_hours": 24, "settle_seconds": 30, "poll_seconds": 25}
        path.write_text(json.dumps(old))
        migrated = load_config(path)
        self.assertNotIn("poll_seconds", migrated)
        self.assertEqual(migrated["save_update_interval"], 1)
        self.assertEqual([migrated[k] for k in old if k != "poll_seconds"], [0, 0, 0])
        # A user-customized bundle or a versioned setting is preserved.
        for saved in (old | {"daily_limit": 7}, old | {"advanced_settings_version": 1}):
            path.write_text(json.dumps(saved))
            loaded = load_config(path)
            for key in ("daily_limit", "cooldown_hours", "settle_seconds"):
                self.assertEqual(loaded[key], saved[key])

    def test_koverwatch_default_path_and_previous_system_font_migration(self):
        path = self.root / "config.json"
        for saved in ({}, {"name_font_path": ""}, {"name_font_path": "C:\\Windows\\Fonts\\malgunbd.ttf"},
                      {"name_font_path": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"}):
            with self.subTest(saved=saved):
                path.write_text(json.dumps(saved))
                self.assertEqual(load_config(path)["name_font_path"], str(self.root / "koverwatch.ttf"))
        for saved in ({"name_font_path": str(self.test_font)},
                      {"name_font_path": "malgun.ttf", "font_default_version": 1}):
            path.write_text(json.dumps(saved))
            self.assertEqual(load_config(path)["name_font_path"], str((self.root / saved["name_font_path"]).resolve()))

    def test_missing_koverwatch_blocks_generation_without_system_fallback(self):
        self.c["name_font_path"] = str(self.root / "koverwatch.ttf")
        self.transfer()
        self.refs()
        def forbidden(*args, **kwargs):
            self.fail("Missing koverwatch.ttf must not invoke Codex")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertIn("koverwatch.ttf", self.e.jobs()[0]["note"])
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_blank_font_uses_fixed_default_instead_of_searching_system_fonts(self):
        missing = self.root / "koverwatch.ttf"
        with patch("gunzo.default_font_path", return_value=missing):
            with self.assertRaisesRegex(ValueError, "koverwatch.ttf"):
                name_font()

    def test_save_interval_and_limits_reject_invalid_values(self):
        path = self.root / "config.json"
        for key, values in (("save_update_interval", (0, -1, 1.5, True)), ("daily_limit", (-1, 0.5)), ("max_age", (-1, 0.5))):
            for value in values:
                with self.subTest(key=key, value=value):
                    path.write_text(json.dumps({key: value}))
                    with self.assertRaises(ValueError):
                        load_config(path)

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

    def test_rounded_output_has_smooth_60px_corners_on_all_sides(self):
        source = self.root / "portrait.png"
        Image.new("RGB", (512, 512), "gray").save(source)
        with Image.open(BytesIO(render_gunzo(source, "Djed Spence"))) as card:
            alpha = card.getchannel("A")
            # Points on either side of the 60px arc distinguish it from 15/30px.
            for x, y in ((5, 5), (5, 30), (30, 5)):
                self.assertLessEqual(alpha.getpixel((x, y)), 5)
            for x, y in ((20, 20), (10, 30), (60, 0), (175, 175)):
                self.assertGreaterEqual(alpha.getpixel((x, y)), 250)
            self.assertIsNone(ImageChops.difference(alpha, alpha.transpose(Image.Transpose.FLIP_LEFT_RIGHT)).getbbox())
            self.assertIsNone(ImageChops.difference(alpha, alpha.transpose(Image.Transpose.FLIP_TOP_BOTTOM)).getbbox())
            self.assertTrue(any(0 < v < 255 for v in alpha.tobytes()))

    def test_custom_font_file_changes_actual_name_pixels_in_applied_face(self):
        candidates = ["DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                      str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "consola.ttf")]
        for candidate in candidates:
            try:
                chosen = ImageFont.truetype(candidate, 20).path
                break
            except OSError:
                continue
        else:
            self.skipTest("A second font is needed to compare caption pixels")
        custom = self.root / "my-player-font.ttf"
        shutil.copyfile(chosen, custom)
        self.c["name_font_path"] = str(custom)
        self.transfer()
        self.refs()
        self.e.run_one(self.good_runner)
        job = self.e.jobs()[0]
        self.assertEqual(job["status"], "applied")
        default = render_gunzo(Path(job["artifact"]).parent / "portrait.png", "Player $(no shell)")
        with Image.open(BytesIO(default)) as standard, Image.open(Path(self.c["pack_dir"]) / "900001.png") as actual:
            self.assertEqual(actual.info["NameFont"], custom.name)
            self.assertIsNotNone(ImageChops.difference(standard.convert("RGB"), actual.convert("RGB")).crop((0, 290, 350, 350)).getbbox())
            self.assertIsNone(ImageChops.difference(standard.crop((0, 0, 350, 250)), actual.crop((0, 0, 350, 250))).getbbox())

    def test_invalid_font_is_blocked_before_codex_call(self):
        bad_font = self.root / "broken.ttf"
        bad_font.write_text("not a font")
        self.c["name_font_path"] = str(bad_font)
        self.transfer()
        self.refs()
        def forbidden(*args, **kwargs):
            self.fail("An invalid font must not start a Codex request")
        self.e.run_one(forbidden)
        self.assertEqual(self.e.jobs()[0]["status"], "blocked")
        self.assertEqual(self.e.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

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
