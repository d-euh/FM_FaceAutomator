"""Exercise actual Treeview selection and queue actions with a display."""
import os
import json
import threading
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
        with patch.object(App, 'auto_paths'):
            self.app = App(self.root, self.fixture.root / 'ui-config.json')
        self.addCleanup(self.cancel_callbacks)
        self.app.config = self.fixture.c
        self.app.tabs.select(self.app.jobs_tab)
        self.app.refresh_queue(self.engine.dashboard_state())
        self.root.update()

    def cancel_callbacks(self):
        self.app.discovery_stop.set()
        with self.app.search_lock:
            for cancel in self.app.search_cancel.values():
                cancel.set()
            threads = list(self.app.search_threads.values())
        if self.app.dashboard_thread is not None:
            threads.append(self.app.dashboard_thread)
        for thread in threads:
            thread.join(3)
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)

    def test_dashboard_database_wait_stays_off_tk_thread(self):
        from engine import Engine
        if self.app.dashboard_thread is not None:
            self.app.dashboard_thread.join(2)
        main_thread = threading.get_ident()
        entered = threading.Event()
        calls = []
        def construct(config):
            calls.append(threading.get_ident())
            if calls[-1] == main_thread:
                raise AssertionError('UI opened a database connection')
            entered.set()
            return Engine(config)
        self.engine.db.execute('BEGIN IMMEDIATE')
        try:
            with patch('app.Engine', side_effect=construct):
                self.app.drain()
                self.assertTrue(entered.wait(2))
                responsive = threading.Event()
                self.root.after_idle(responsive.set)
                self.root.update()
                self.assertTrue(responsive.is_set())
                thread = self.app.dashboard_thread
                self.assertTrue(thread.is_alive())
                self.app.poll_dashboard()
                self.assertIs(self.app.dashboard_thread, thread)
                self.engine.db.rollback()
                thread.join(3)
                self.assertFalse(thread.is_alive())
            self.assertTrue(calls)
            self.assertNotIn(main_thread, calls)
        finally:
            self.engine.db.rollback()

    def test_stale_dashboard_cannot_restore_deleted_queue_row(self):
        old = self.engine.dashboard_state()
        token = self.app.dashboard_token
        self.app.tree.selection_set('1')
        self.app.delete_job()
        self.app.events.put({'dashboard': token, 'workspace': self.engine.c['state_dir'], 'state': old})
        with patch.object(self.app, 'poll_dashboard'):
            self.app.drain()
        self.assertFalse(self.app.tree.exists('1'))

    def test_dashboard_render_error_does_not_stop_polling(self):
        self.app.events.put({'dashboard': self.app.dashboard_token, 'workspace': self.engine.c['state_dir'],
                             'state': self.engine.dashboard_state()})
        with patch.object(self.app, 'update_dashboard', side_effect=ValueError('invalid dashboard')), patch.object(self.app, 'poll_dashboard') as poll:
            self.app.drain()
        self.assertEqual(self.app.status.get(), 'invalid dashboard')
        poll.assert_called_once()

    def test_workspace_switch_cannot_delete_jobs_using_old_selection(self):
        self.app.tree.selection_set('1')
        self.app.config = self.app.config | {'state_dir': str(self.fixture.root / 'other-save')}
        with patch('app.Engine') as open_engine:
            self.assertEqual(self.app.selected_ids(), [])
            self.app.delete_job()
            self.app.clear_queue()
            self.app.drain()
        open_engine.assert_not_called()
        self.assertFalse(self.app.tree.get_children())
        self.assertEqual(self.engine.db.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'failed')

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
        self.app.refresh_queue(self.engine.dashboard_state())
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
        self.app.refresh_queue(self.engine.dashboard_state())
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
        self.app.refresh_queue(self.engine.dashboard_state())
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
            self.app.refresh_queue(self.engine.dashboard_state())
            self.assertEqual(self.app.tree.item('1', 'values')[4], '게임 대기')
            self.assertIn('게임 대기 중', self.app.activity.get())

    def test_screen_log_retains_newest_entries_with_bounded_lines_and_characters(self):
        from app import LOG_LINE_LIMIT, LOG_CHARACTER_LIMIT
        for number in range(LOG_LINE_LIMIT + 25):
            self.app.append_log(f'memory-log-{number}')
        text = self.app.log.get('1.0', 'end-1c')
        self.assertNotIn('memory-log-0\n', text)
        self.assertIn(f'memory-log-{LOG_LINE_LIMIT + 24}', text)
        self.assertLessEqual(int(self.app.log.index('end-1c').split('.')[0]) - 1, LOG_LINE_LIMIT)
        with patch('app.LOG_CHARACTER_LIMIT', 10000):
            for _ in range(5):
                self.app.append_log('x' * 7500 + 'newest-tail')
            self.assertLessEqual(self.app.log.count('1.0', 'end-1c', 'chars')[0], 10000)
        self.app.append_log('x' * (LOG_CHARACTER_LIMIT + 100) + 'newest-tail')
        self.assertIn('긴 로그의 중간 부분 생략', self.app.log.get('1.0', 'end-1c'))
        self.assertTrue(self.app.log.get('1.0', 'end-1c').endswith('newest-tail\n'))
        self.assertEqual(self.app.log.cget('state'), 'disabled')

    def test_uploaded_app_icon_loads_through_normal_window_startup(self):
        if os.name != 'nt':
            self.assertEqual((self.root.app_icon.width(), self.root.app_icon.height()), (256, 256))
            self.assertIn(str(self.root.app_icon), self.root.tk.call('image', 'names'))
        child = tk.Toplevel(self.root)
        try:
            self.root.update()
            self.assertTrue(child.winfo_exists())
        finally:
            child.destroy()

    def test_direct_generation_can_enqueue_another_player_while_one_off_worker_is_busy(self):
        engine = self.engine
        engine.setmeta('club_catalog', json.dumps([{'id': '20', 'name': 'Arsenal'}]))
        engine.db.commit()
        panel = self.app.manual_panel
        panel.workspace = self.app.config['state_dir']
        panel.player = json.loads(engine.db.execute("SELECT data FROM people WHERE id='2'").fetchone()[0])
        panel.club_id = '20'
        panel.clubs = {'20': {'id': '20', 'name': 'Arsenal'}}
        started, release = threading.Event(), threading.Event()
        def busy(current):
            current.update(1, 'running')
            started.set()
            release.wait(5)
        with patch.object(self.app, 'save', return_value=True):
            self.app.background(busy)
        try:
            self.assertTrue(started.wait(3))
            self.assertTrue(self.app.active())
            self.assertFalse(self.app.watching)
            with patch.object(self.app, 'poll_dashboard'):
                self.app.drain()
            self.assertFalse(panel.generate_button.instate(['disabled']))
            worker = self.app.thread
            panel.generate_button.invoke()
            self.assertIsNotNone(self.app.request_thread)
            self.app.request_thread.join(3)
            self.assertFalse(self.app.request_active())
            self.assertIs(self.app.thread, worker)
            self.assertTrue(self.app.active())
            job = engine.db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual((job['player_id'], job['status']), ('2', 'pending'))
            self.assertTrue(json.loads(job['data'])['manual_request'])
            self.assertEqual(engine.db.execute('SELECT status FROM jobs WHERE id=1').fetchone()[0], 'running')
            self.assertEqual(engine.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)
            with patch.object(self.app, 'poll_dashboard'):
                self.app.drain()
            self.assertFalse(panel.generate_button.instate(['disabled']))
        finally:
            release.set()
            self.app.thread.join(3)
            if self.app.request_thread:
                self.app.request_thread.join(3)

    def test_manual_request_stays_disabled_only_while_enqueue_is_in_progress(self):
        panel = self.app.manual_panel
        panel.player = {'id': '2'}
        panel.club_id = '20'
        panel.clubs = {'20': {'id': '20', 'name': 'Arsenal'}}
        with patch.object(self.app, 'request_active', return_value=True), \
             patch.object(self.app, 'poll_dashboard'), \
             patch.object(self.app, 'background') as background, \
             patch('app.Engine') as engine:
            self.app.drain()
            self.assertTrue(panel.generate_button.instate(['disabled']))
            self.app.request_manual('2', '20', '', 'identity')
            background.assert_not_called()
            engine.assert_not_called()
        with patch.object(self.app, 'poll_dashboard'):
            self.app.drain()
        self.assertFalse(panel.generate_button.instate(['disabled']))
