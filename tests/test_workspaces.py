import copy
import json
from pathlib import Path
import tempfile
import unittest

from engine import DEFAULTS, Engine, PastSaveError, load_config, normalise
from workspaces import select_workspace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c = copy.deepcopy(DEFAULTS) | {"source": str(self.root / "career-a.fm"), "state_dir": str(self.root / "old-state"), "automatic_workspaces": True}

    def baseline(self, date):
        return normalise({"game_date": date, "players": [{"id": "1", "name": "Player", "club_id": "20"}]})

    def test_different_saves_auto_separate_and_return_to_existing_records(self):
        first = select_workspace(self.c, self.root)
        e = Engine(first)
        e.ingest(self.baseline("2027-07-01"))
        e.close()
        second = select_workspace(first | {"source": str(self.root / "career-b.fm")}, self.root)
        self.assertNotEqual(first["state_dir"], second["state_dir"])
        e = Engine(second)
        self.assertIsNone(e.meta("baseline"))
        e.close()
        returned = select_workspace(second | {"source": self.c["source"]}, self.root)
        self.assertEqual(returned["state_dir"], first["state_dir"])
        e = Engine(returned)
        self.assertEqual(e.meta("game_date"), "2027-07-01")
        e.close()

    def test_existing_work_folder_is_adopted_without_losing_baseline(self):
        e = Engine(self.c)
        e.ingest(self.baseline("2027-07-01"))
        e.close()
        path = self.root / "config.json"
        path.write_text(json.dumps(self.c))
        loaded = load_config(path)
        self.assertEqual(loaded["state_dir"], self.c["state_dir"])
        e = Engine(loaded)
        self.assertEqual(e.meta("game_date"), "2027-07-01")
        e.close()

    def test_past_save_forks_records_and_preserves_original_history(self):
        c = select_workspace(self.c, self.root)
        e = Engine(c)
        e.ingest(self.baseline("2028-07-01"))
        with self.assertRaises(PastSaveError):
            e.ingest(self.baseline("2027-07-01"))
        e.close()
        fresh = select_workspace(c, self.root, fresh=True)
        self.assertNotEqual(fresh["state_dir"], c["state_dir"])
        e = Engine(fresh)
        self.assertEqual(e.ingest(self.baseline("2027-07-01")), 0)
        e.close()
        old = Engine(c)
        self.assertEqual(old.meta("game_date"), "2028-07-01")
        old.close()
