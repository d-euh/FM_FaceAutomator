"""Exercise actual Treeview selection and queue actions with a display."""
import os
import json
import tkinter as tk
import unittest
from unittest.mock import patch

from app import App
import test_queue_controls as fixtures


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'A graphical display is required')
class QueueSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.QueueControlTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = self.fixture.engine
        self.engine.update(1, 'failed')
        self.engine.update(3, 'blocked')
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root, self.fixture.root / 'ui-config.json')
        self.addCleanup(self.cancel_callbacks)
        self.app.config = self.fixture.c
        self.app.tabs.select(self.app.jobs_tab)
        self.app.refresh_queue(self.engine)
        self.root.update()

    def cancel_callbacks(self):
        self.app.discovery_stop.set()
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)

    def click(self, row, state=0):
        x, y, width, height = self.app.tree.bbox(str(row))
        self.app.tree.event_generate('<ButtonPress-1>', x=x + 20, y=y + height // 2, state=state)
        self.app.tree.event_generate('<ButtonRelease-1>', x=x + 20, y=y + height // 2, state=state)
        self.root.update()

    def test_control_shift_select_all_and_refresh_preserve_multiple_selection(self):
        self.click(1)
        self.click(3, 0x0004)
        self.assertEqual(set(self.app.selected_ids()), {1, 3})
        self.assertIsNone(self.app.selected())
        self.assertIsNone(self.app.queue_drag)
        self.engine.update(2, 'failed')
        self.app.refresh_queue(self.engine)
        self.root.update()
        self.assertEqual(set(self.app.selected_ids()), {1, 3})
        self.click(1)
        self.click(3, 0x0001)
        self.assertEqual(set(self.app.selected_ids()), {1, 2, 3})
        self.app.tree.selection_set('1')
        self.app.tree.focus_force()
        self.root.update()
        self.app.tree.event_generate('<Control-a>')
        self.root.update()
        self.assertEqual(set(self.app.selected_ids()), {1, 2, 3})

    def test_bulk_retry_only_processes_selected_retryable_jobs(self):
        self.app.tree.selection_set('1', '3')
        self.root.update()
        with patch.object(self.app, 'background', side_effect=lambda task: task(self.engine)), patch.object(self.app, 'process_one') as process:
            self.app.retry()
        self.assertEqual({call.kwargs['job_id'] for call in process.call_args_list}, {1, 3})
        self.assertEqual(self.engine.db.execute('SELECT status FROM jobs WHERE id=2').fetchone()[0], 'pending')
        self.assertFalse(self.app.queue_action_states()['위로 이동'])
        self.assertFalse(self.app.queue_action_states()['유니폼 변경'])

    def test_bulk_delete_protects_running_job_and_keeps_surviving_selection(self):
        self.engine.update(1, 'running')
        self.app.refresh_queue(self.engine)
        self.app.tree.selection_set('1', '2', '3')
        self.root.update()
        self.app.delete_job()
        self.root.update()
        self.assertEqual([job['id'] for job in self.engine.jobs()], [1])
        self.assertEqual(self.app.selected_ids(), [1])
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM jobs').fetchone()[0], 3)

    def test_right_click_preserves_selected_group_and_single_drag_still_arms(self):
        self.app.tree.selection_set('1', '3')
        self.root.update()
        x, y, width, height = self.app.tree.bbox('3')
        event = type('Event', (), dict(x=x + 20, y=y + height // 2, x_root=10, y_root=10))()
        with patch.object(self.app, 'show_job_menu'):
            self.app.queue_menu(event)
        self.assertEqual(set(self.app.selected_ids()), {1, 3})
        self.app.tree.selection_set('1')
        self.root.update()
        x, y, width, height = self.app.tree.bbox('1')
        self.app.tree.event_generate('<ButtonPress-1>', x=x + 20, y=y + height // 2)
        self.assertEqual(self.app.queue_drag['id'], 1)
        self.app.cancel_queue_drag()

    def test_selection_survives_when_first_selected_job_is_deleted(self):
        self.engine.begin_job_edit(2)
        self.app.refresh_queue(self.engine)
        self.app.tree.selection_set('1', '2', '3')
        self.root.update()
        self.app.delete_job()
        self.root.update()
        self.assertEqual(self.app.selected_ids(), [2])
        self.assertEqual([job['id'] for job in self.engine.jobs()], [2])

    def test_selected_retry_stays_alive_until_temporary_game_wait_finishes(self):
        calls = []
        def run(**kwargs):
            calls.append(kwargs)
            self.engine.last_job_id = 1
            self.engine.waiting_for_game = len(calls) == 1
            return not self.engine.waiting_for_game
        with patch.object(self.engine, 'run_one', side_effect=run), patch.object(self.app.stop, 'wait', return_value=False) as wait:
            self.assertTrue(self.app.process_one(self.engine, job_id=1))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call['job_id'] == 1 for call in calls))
        wait.assert_called_once_with(1)

    def test_game_wait_can_be_stopped_without_starting_another_attempt(self):
        def run(**kwargs):
            self.engine.last_job_id = 1
            self.engine.waiting_for_game = True
            return False
        with patch.object(self.engine, 'run_one', side_effect=run) as execute, patch.object(self.app.stop, 'wait', return_value=True):
            self.assertFalse(self.app.process_one(self.engine, job_id=1))
        self.assertEqual(execute.call_count, 1)

    def test_game_wait_is_visible_in_queue_and_activity(self):
        row = json.loads(self.engine.jobs()[0]['data'])
        row['game_wait'] = True
        with self.engine.db:
            self.engine.db.execute("UPDATE jobs SET data=?,status='pending',note='게임 대기 · 진행 중' WHERE id=1", (json.dumps(row),))
        with patch.object(self.app, 'active', return_value=True):
            self.app.refresh_queue(self.engine)
            self.assertEqual(self.app.tree.item('1', 'values')[4], '게임 대기')
            self.assertIn('게임 대기 중', self.app.activity.get())
