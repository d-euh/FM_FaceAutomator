from pathlib import Path
import queue
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from app import App
from player_catalog import find_players


class PlayerSearchTests(unittest.TestCase):
    def test_slow_search_keeps_only_latest_pending_request(self):
        app = App.__new__(App)
        app.config = {'state_dir': 'unused'}
        app.events = queue.Queue()
        app.manual_search_token = 0
        app.discovery_stop = threading.Event()
        app.search_lock = threading.Lock()
        app.search_requests, app.search_threads, app.search_cancel = {}, {}, {}
        entered, release = threading.Event(), threading.Event()
        calls = []
        def search(database, query, ids, *, cancel):
            calls.append(query)
            if query == 'first':
                entered.set()
                release.wait(3)
                self.assertTrue(cancel.is_set())
            return [{'id': query}], []
        try:
            with patch('app.find_players', side_effect=search):
                app.search_manual_players('first', [])
                self.assertTrue(entered.wait(2))
                for index in range(20):
                    app.search_manual_players(str(index), [])
                with app.search_lock:
                    thread = app.search_threads['manual_players']
                    self.assertEqual(len(app.search_threads), 1)
                    self.assertEqual(len(app.search_requests), 1)
                release.set()
                thread.join(3)
                self.assertFalse(thread.is_alive())
            self.assertEqual(calls, ['first', '19'])
            event = app.events.get_nowait()
            self.assertEqual(event['manual_players'], 21)
            self.assertEqual(event['available'], [{'id': '19'}])
            self.assertTrue(app.events.empty())
            self.assertFalse(app.search_threads)
            app.discovery_stop.set()
            app.search_manual_players('closed', [])
            self.assertFalse(app.search_threads)
        finally:
            release.set()
            app.discovery_stop.set()
            for thread in list(app.search_threads.values()):
                thread.join(3)

    def test_sql_progress_handler_interrupts_obsolete_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / 'queue.sqlite'
            db = sqlite3.connect(file)
            try:
                db.execute('CREATE TABLE people(id TEXT PRIMARY KEY,data TEXT)')
                db.executemany('INSERT INTO people VALUES (?,?)', [(str(i), '{"name":"Player"}') for i in range(500)])
                db.commit()
            finally:
                db.close()
            cancel = Mock()
            cancel.is_set.side_effect = [False, True]
            with self.assertRaisesRegex(sqlite3.OperationalError, 'interrupt'):
                find_players(file, cancel=cancel)
