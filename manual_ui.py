"""Single-player portrait requests, independent of automatic transfer scopes."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from scope_ui import ScopePanel


class ManualPanel:
    def __init__(self, parent, search, read, request):
        self.parent, self.search, self.request = parent, search, request
        self.workspace = None
        self.clubs, self.players = {}, {}
        self.player = None
        self.club_id = None
        self.timer = None
        self.query = tk.StringVar()
        self.club_query = tk.StringVar()
        self.player_name = tk.StringVar(value='선수를 선택하세요')
        self.club_name = tk.StringVar(value='기본값: 현 소속팀')
        self.note = tk.StringVar(value='선수 목록을 불러온 뒤 이름 또는 ID로 검색하세요.')
        ttk.Label(parent, text='직접 생성', style='Title.TLabel').pack(anchor='w', pady=(0, 16))
        columns = ttk.Frame(parent)
        columns.pack(fill='both', expand=True)
        columns.columnconfigure(0, weight=1, uniform='manual')
        columns.columnconfigure(1, weight=1, uniform='manual')
        left = ttk.Frame(columns, style='Panel.Card.TFrame', padding=20)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        right = ttk.Frame(columns, style='Panel.Card.TFrame', padding=20)
        right.grid(row=0, column=1, sticky='nsew')
        ttk.Label(left, text='선수 선택', style='CardTitle.TLabel').pack(anchor='w')
        form = ttk.Frame(left, style='Card.TFrame')
        form.pack(fill='x', pady=12)
        ttk.Entry(form, textvariable=self.query).pack(side='left', fill='x', expand=True, padx=(0, 8))
        ttk.Button(form, text='목록 불러오기', command=read).pack(side='right')
        self.available = ScopePanel.player_table(left, (('name', '선수', 180), ('club', '현 소속팀', 150), ('id', '선수 ID', 85)), 8)
        self.available.bind('<<TreeviewSelect>>', self.select_player)
        ttk.Label(left, textvariable=self.note, style='CardMuted.TLabel', wraplength=430).pack(anchor='w', pady=12)
        ttk.Label(right, textvariable=self.player_name, style='CardTitle.TLabel', wraplength=450).pack(anchor='w')
        ttk.Label(right, text='유니폼 구단', style='CardText.TLabel').pack(anchor='w', pady=(16, 6))
        chosen = ttk.Frame(right, style='Card.TFrame')
        chosen.pack(fill='x')
        ttk.Label(chosen, textvariable=self.club_name, style='CardText.TLabel', wraplength=300).pack(side='left', fill='x', expand=True)
        ttk.Button(chosen, text='현 소속팀', command=self.current_club).pack(side='right')
        ttk.Entry(right, textvariable=self.club_query).pack(fill='x', pady=(12, 6))
        self.club_list = ScopePanel.player_table(right, (('name', '구단 검색 · 이름 또는 ID', 280), ('id', '구단 ID', 90)), 2)
        self.club_list.bind('<<TreeviewSelect>>', self.select_club)
        ttk.Label(right, text='이 작업에만 적용할 지시 · 선택', style='CardText.TLabel').pack(anchor='w', pady=(16, 6))
        self.directions = tk.Text(right, height=4, wrap='word', font='TkTextFont')
        self.directions.pack(fill='x')
        self.generate_button = ttk.Button(right, text='생성 요청', style='Primary.TButton', command=self.submit, state='disabled')
        self.generate_button.pack(anchor='w', pady=(16, 0))
        self.query.trace_add('write', self.queue_search)
        self.club_query.trace_add('write', lambda *_: self.filter_clubs())

    def queue_search(self, *_):
        if self.timer is not None:
            self.parent.after_cancel(self.timer)
        self.timer = self.parent.after(250, self.refresh)

    def refresh(self):
        self.timer = None
        self.search(self.query.get(), [self.player['id']] if self.player else [])

    def set_catalog(self, clubs, workspace):
        if self.workspace != workspace:
            self.player, self.club_id = None, None
            self.players.clear()
            self.available.delete(*self.available.get_children())
            self.player_name.set('선수를 선택하세요')
            self.club_name.set('기본값: 현 소속팀')
            self.directions.delete('1.0', 'end')
            self.generate_button.configure(state='disabled')
        self.workspace = workspace
        self.clubs = {str(club['id']): club for club in clubs}
        self.filter_clubs()
        self.refresh()

    def set_players(self, rows, selected, note=None):
        self.players = {row['id']: row for row in rows + selected}
        self.available.delete(*self.available.get_children())
        for row in rows:
            self.available.insert('', 'end', iid=row['id'], values=(row['name'], row.get('club_name') or '무소속', row['id']))
        if self.player:
            current = self.players.get(self.player['id'])
            if current != self.player:
                self.player, self.club_id = None, None
                self.player_name.set('선수 정보가 바뀌었습니다. 다시 선택하세요')
                self.club_name.set('기본값: 현 소속팀')
            elif self.available.exists(self.player['id']):
                self.available.selection_set(self.player['id'])
        self.note.set(note or (f'이름·영문 이름·구단·ID 검색 · {len(rows)}명 표시' if rows else '검색 결과가 없습니다. 목록을 불러오거나 검색어를 바꿔 주세요.'))

    def select_player(self, event=None):
        ids = self.available.selection()
        if not ids:
            return
        player = self.players[ids[0]]
        if self.player == player:
            return
        self.player = player
        self.player_name.set(player['name'] + (' · ' + player['english_name'] if player.get('english_name') else ''))
        self.directions.delete('1.0', 'end')
        self.current_club()

    def current_club(self):
        self.club_id = self.player.get('club_id') if self.player else None
        self.club_name.set((self.player.get('club_name') or '무소속 · 구단을 선택하세요') if self.player else '기본값: 현 소속팀')
        self.club_query.set('')
        self.filter_clubs()

    def filter_clubs(self):
        query = self.club_query.get().strip().casefold()
        self.club_list.delete(*self.club_list.get_children())
        clubs = sorted(self.clubs.values(), key=lambda club: (str(club['id']) != self.club_id, club['name'].casefold()))
        for club in [club for club in clubs if not query or query in (str(club['id']) + ' ' + club['name']).casefold()][:150]:
            self.club_list.insert('', 'end', iid=str(club['id']), values=(club['name'], club['id']))
        if self.club_id and self.club_list.exists(self.club_id):
            self.club_list.selection_set(self.club_id)

    def select_club(self, event=None):
        ids = self.club_list.selection()
        if ids:
            self.club_id = ids[0]
            self.club_name.set(self.clubs[self.club_id]['name'])

    def set_available(self, allowed):
        self.generate_button.configure(state='normal' if allowed and self.player and self.club_id in self.clubs else 'disabled')

    def submit(self):
        if self.player and self.club_id in self.clubs:
            self.request(self.player['id'], self.club_id, self.directions.get('1.0', 'end').strip(), self.player['identity'])
