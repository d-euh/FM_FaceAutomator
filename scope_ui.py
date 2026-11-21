"""Native generation-scope page with presets and searchable per-club directions."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from scope_rules import DIRECTIONS, LEAGUES, PRESETS, describe, migrate_scope
from transfer_types import TRANSFER_TYPES
from squad_types import KINDS as SQUAD_TYPES

LOAN_TYPES = ('loan', 'loan_return')


class ScopePanel:
    def __init__(self, parent, variables, save, read, changed, advanced, find_players=None, generate=None):
        self.variables, self.changed = variables, changed
        self.parent, self.find_players = parent, find_players
        self.player_rules, self.players = {}, {}
        self.player_search = tk.StringVar()
        self.player_mode = tk.StringVar(value="생성 대상")
        self.player_note = tk.StringVar(value="선수 목록을 불러오세요.")
        self.player_timer = None
        self.focus_player = None
        for key in ('player_ids', 'exclude_player_ids'):
            variables[key] = tk.StringVar()
        self.catalog, self.rules, self.managed = {}, {}, []
        self.league_status = {}
        self.preset = tk.StringVar(value="managed")
        self.direction = tk.StringVar(value=DIRECTIONS["both"])
        self.include_managed = tk.BooleanVar(value=False)
        self.squad_types = {kind: tk.BooleanVar(value=True) for kind in SQUAD_TYPES}
        self.transfer_types = {kind: tk.BooleanVar(value=True) for kind in TRANSFER_TYPES if kind not in LOAN_TYPES}
        self.loan_moves = tk.IntVar(value=1)
        self.saved_loan_types = LOAN_TYPES
        self.search = tk.StringVar()
        self.manual_id = tk.StringVar()
        self.club_direction = tk.StringVar(value=DIRECTIONS["both"])
        self.note = tk.StringVar(value="선수·이적을 읽으면 세이브의 구단을 이름으로 검색할 수 있습니다.")
        self.summary = tk.StringVar()
        parent.configure(padding=(16, 12))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        style = ttk.Style(parent)
        style.configure('Scope.Treeview', rowheight=26)
        style.configure('Scope.Treeview.Heading', padding=(5, 3))
        toolbar = ttk.Frame(parent, style='Panel.Card.TFrame', padding=12)
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        toolbar.columnconfigure(1, weight=1)
        toolbar.columnconfigure(3, weight=2)
        ttk.Label(toolbar, text='감지 대상', style='CardText.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(toolbar, text='이동 방향', style='CardText.TLabel').grid(row=0, column=1, sticky='w', padx=(12, 0))
        self.preset_label = tk.StringVar(value=PRESETS['managed'])
        self.preset_selector = ttk.Combobox(toolbar, textvariable=self.preset_label, values=list(PRESETS.values()), state='readonly', width=23)
        self.preset_selector.grid(row=1, column=0, sticky='ew')
        self.preset_selector.bind('<<ComboboxSelected>>', self.select_preset)
        ttk.Combobox(toolbar, textvariable=self.direction, values=list(DIRECTIONS.values()), state='readonly', width=18).grid(row=1, column=1, sticky='ew', padx=(12, 0))
        ttk.Button(toolbar, text='목록 불러오기', style='Compact.TButton', command=read).grid(row=1, column=2, padx=12)
        ttk.Label(toolbar, textvariable=self.summary, style='CardMuted.TLabel', wraplength=300).grid(row=0, column=3, rowspan=2, sticky='w')
        self.direction.trace_add('write', lambda *_: self.render_summary())
        kinds = ttk.Frame(toolbar, style='Card.TFrame')
        kinds.grid(row=2,column=0,columnspan=4,sticky='ew',pady=(8,0))
        ttk.Label(kinds,text='포함할 이적 유형',style='CardText.TLabel').pack(side='left',padx=(0,14))
        for kind, label in TRANSFER_TYPES.items():
            if kind == LOAN_TYPES[0]:
                self.loan_checkbox = ttk.Checkbutton(
                    kinds, text='임대 이동', variable=self.loan_moves, style='Card.TCheckbutton',
                    command=self.select_loan_moves)
                self.loan_checkbox.pack(side='left', padx=(0, 14))
            if kind in LOAN_TYPES:
                continue
            ttk.Checkbutton(kinds,text=label,variable=self.transfer_types[kind],style='Card.TCheckbutton',command=self.render_summary).pack(side='left',padx=(0,14))

        groups = ttk.Frame(kinds, style='Card.TFrame')
        groups.pack(side='left',padx=(10,0))
        ttk.Label(groups,text='선수단',style='CardText.TLabel').pack(side='left',padx=(0,14))
        for kind,label in SQUAD_TYPES.items():
            ttk.Checkbutton(groups,text=label,variable=self.squad_types[kind],style='Card.TCheckbutton',command=self.render_summary).pack(side='left',padx=(0,14))

        body = ttk.Frame(parent)
        body.grid(row=1, column=0, sticky='nsew')
        body.columnconfigure(0, weight=1, uniform='scope')
        body.columnconfigure(1, weight=1, uniform='scope')
        body.rowconfigure(0, weight=1)
        self.preset_card = ttk.Frame(body, style='Panel.Card.TFrame', padding=18)
        self.preset_card.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        ttk.Label(self.preset_card, text='선택한 이적 감지 범위', style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(self.preset_card, textvariable=self.summary, style='CardText.TLabel', wraplength=410).pack(anchor='w', pady=(16, 8))
        self.managed_note = tk.StringVar()
        ttk.Label(self.preset_card, textvariable=self.managed_note, style='CardMuted.TLabel', wraplength=410).pack(anchor='w', pady=(0, 8))
        ttk.Label(self.preset_card, textvariable=self.note, style='CardMuted.TLabel', wraplength=410).pack(anchor='w')
        ttk.Button(self.preset_card, text='구단 직접 설정', command=lambda: self.choose_preset('custom')).pack(anchor='w', pady=18)

        self.club_card = left = ttk.Frame(body, style='Panel.Card.TFrame', padding=12)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1, uniform='club-lists')
        left.rowconfigure(5, weight=1, uniform='club-lists')
        ttk.Label(left, text='구단 직접 설정 · 이름/ID 검색', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Entry(left, textvariable=self.search).grid(row=1, column=0, sticky='ew', pady=6)
        self.available = self.compact_table(left, 2, (('id', '구단 ID', 70), ('name', '구단 이름', 160), ('league', '리그', 125)))
        self.available.bind('<<TreeviewSelect>>', self.select_available)
        self.search.trace_add('write', lambda *_: self.filter_catalog())
        form = ttk.Frame(left, style='Card.TFrame')
        form.grid(row=3, column=0, sticky='ew', pady=6)
        ttk.Label(form,text='ID',style='CardText.TLabel').pack(side='left',padx=(0,4))
        ttk.Entry(form, textvariable=self.manual_id, width=8).pack(side='left', padx=(0, 6))
        ttk.Combobox(form, textvariable=self.club_direction, values=list(DIRECTIONS.values()), state='readonly', width=16).pack(side='left', padx=(0, 6))
        ttk.Button(form, text='추가 · 변경', style='Compact.TButton', command=self.add_club).pack(side='left')
        ttk.Label(left, text='선택한 구단', style='CardText.TLabel').grid(row=4, column=0, sticky='w', pady=(0, 4))
        self.selected = self.compact_table(left, 5, (('id', '구단 ID', 70), ('name', '구단 이름', 160), ('direction', '이동 방향', 125)))
        self.selected.bind('<<TreeviewSelect>>', self.select_rule)
        row = ttk.Frame(left, style='Card.TFrame')
        row.grid(row=6, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(row, text='선택 구단 삭제', style='Compact.TButton', command=self.remove_club).pack(side='left')
        ttk.Checkbutton(row, style='Card.TCheckbutton', text='내 구단도 포함', variable=self.include_managed, command=self.render_summary).pack(side='right')

        right = ttk.Frame(body, style='Panel.Card.TFrame', padding=12)
        right.grid(row=0, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1, uniform='player-lists')
        right.rowconfigure(5, weight=1, uniform='player-lists')
        ttk.Label(right, text='선수 개별 설정 · 이름/ID 검색', style='CardTitle.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Entry(right, textvariable=self.player_search).grid(row=1, column=0, sticky='ew', pady=6)
        self.player_available = self.compact_table(right, 2, (('id', '선수 ID', 78), ('name', '선수 이름', 140), ('club', '소속 구단', 140)))
        self.player_available.bind('<<TreeviewSelect>>', lambda event: self.select_player(False))
        self.player_available.bind('<Double-1>', lambda event: self.add_player())
        form = ttk.Frame(right, style='Card.TFrame')
        form.grid(row=3, column=0, sticky='ew', pady=6)
        ttk.Combobox(form, textvariable=self.player_mode, values=('생성 대상', '생성 제외'), state='readonly', width=12).pack(side='left', padx=(0, 8))
        ttk.Button(form, text='추가 · 변경', style='Compact.TButton', command=self.add_player).pack(side='left')
        ttk.Label(right, text='선택한 선수', style='CardText.TLabel').grid(row=4, column=0, sticky='w', pady=(0, 4))
        self.player_selected = self.compact_table(right, 5, (('id', '선수 ID', 78), ('name', '선수 이름', 130), ('club', '소속 구단', 120), ('mode', '처리', 75)))
        self.player_selected.bind('<<TreeviewSelect>>', lambda event: self.select_player(True))
        row = ttk.Frame(right, style='Card.TFrame')
        row.grid(row=6, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(row, text='선택 선수 삭제', style='Compact.TButton', command=self.remove_player).pack(side='left')
        ttk.Label(row, textvariable=self.player_note, style='CardMuted.TLabel', wraplength=230).pack(side='right')
        self.player_search.trace_add('write', self.queue_player_search)

        footer = ttk.Frame(parent)
        footer.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        self.save_button = ttk.Button(footer, text='설정 저장', style='Primary.TButton', command=save)
        self.save_button.grid(row=0, column=0, sticky='w')
        self.advanced_button = ttk.Button(footer, text='고급설정', style='Compact.TButton', command=advanced)
        self.advanced_button.grid(row=1, column=0, sticky='w', pady=(6, 0))
        if generate:
            ttk.Button(footer, text='현재 선수 생성 대기', style='Compact.TButton', command=generate).grid(row=0, column=1, sticky='e', padx=(12, 0))
        footer.columnconfigure(1, weight=1)

    @staticmethod
    def compact_table(parent, row, columns):
        frame = ttk.Frame(parent, style='Card.TFrame')
        frame.grid(row=row, column=0, sticky='nsew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=tuple(item[0] for item in columns), show='headings', height=2, selectmode='browse', style='Scope.Treeview')
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=45, stretch=key == 'name')
        tree.grid(row=0, column=0, sticky='nsew')
        bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        bar.grid(row=0, column=1, sticky='ns')
        return tree

    def select_preset(self, event=None):
        self.choose_preset({label: key for key, label in PRESETS.items()}[self.preset_label.get()])

    def select_loan_moves(self):
        self.loan_checkbox.state(['!alternate'])
        self.render_summary()

    def value(self):
        reverse = {label: key for key, label in DIRECTIONS.items()}
        loan_moves = self.loan_moves.get()
        selected_loans = self.saved_loan_types if loan_moves == -1 else LOAN_TYPES if loan_moves else ()
        selected_types = set(selected_loans)
        selected_types.update(kind for kind, variable in self.transfer_types.items() if variable.get())
        return {"preset": self.preset.get(), "direction": reverse[self.direction.get()], "clubs": dict(self.rules), "include_managed": self.include_managed.get(),
                'transfer_types': [kind for kind in TRANSFER_TYPES if kind in selected_types],
                'squad_types':[kind for kind,variable in self.squad_types.items() if variable.get()]}

    def load(self, config):
        value = migrate_scope(config)
        self.rules = dict(value["clubs"])
        self.preset.set(value["preset"])
        self.direction.set(DIRECTIONS[value["direction"]])
        self.include_managed.set(value.get("include_managed", False))
        for kind, variable in self.transfer_types.items():
            variable.set(kind in value['transfer_types'])
        self.saved_loan_types = tuple(kind for kind in LOAN_TYPES if kind in value['transfer_types'])
        mixed = len(self.saved_loan_types) == 1
        self.loan_moves.set(-1 if mixed else int(bool(self.saved_loan_types)))
        self.loan_checkbox.state(['alternate' if mixed else '!alternate'])
        for kind, variable in self.squad_types.items():
            variable.set(kind in value['squad_types'])
        self.player_rules = {str(pid): 'include' for pid in config.get('player_ids', [])}
        self.player_rules.update({str(pid): 'exclude' for pid in config.get('exclude_player_ids', [])})
        self.render_players()
        self.refresh_players()
        self.render_rules()
        self.render_summary()

    def choose_preset(self, key):
        self.preset.set(key)
        self.render_summary()

    def render_summary(self):
        rules = self.value()
        self.summary.set(describe({'scope_rules': rules} | self.player_config()))
        self.preset_label.set(PRESETS[rules['preset']])
        if rules['preset'] == 'custom':
            self.preset_card.grid_remove()
            self.club_card.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        else:
            self.club_card.grid_remove()
            self.preset_card.grid()
        self.refresh_note()
        self.changed()

    def set_catalog(self, clubs, managed, status):
        self.catalog = {str(c["id"]): c for c in clubs}
        self.managed = managed
        names = [self.catalog.get(str(cid), {}).get('name', str(cid)) for cid in managed]
        self.managed_note.set('내 구단: ' + ', '.join(names) if names else '담당 구단 정보는 세이브에서 확인합니다.')
        self.league_status = status
        self.refresh_note()
        self.filter_catalog()
        self.render_rules()
        self.refresh_players()

    @staticmethod
    def player_table(parent, columns, height):
        frame = ttk.Frame(parent, style='Card.TFrame')
        frame.pack(fill='x')
        tree = ttk.Treeview(frame, columns=tuple(item[0] for item in columns), show='headings', height=height, selectmode='browse')
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, stretch=key == 'name')
        bar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        tree.pack(side='left', fill='x', expand=True)
        return tree

    def queue_player_search(self, *args):
        if self.player_timer is not None:
            self.parent.after_cancel(self.player_timer)
        self.player_timer = self.parent.after(250, self.refresh_players)

    def refresh_players(self):
        self.player_timer = None
        if self.find_players:
            self.find_players(self.player_search.get(), list(self.player_rules))

    def set_players(self, available, selected):
        self.players = {row['id']: row for row in available + selected}
        self.focus_player = None
        self.player_available.delete(*self.player_available.get_children())
        for row in available:
            self.player_available.insert('', 'end', iid=row['id'], values=(row['id'], row['name'], row.get('club_name') or '무소속'))
        self.player_note.set(f'{len(available)}명 표시 · 이름/ID 검색' if available else '검색 결과 없음 · 목록을 불러오세요')
        self.render_players()

    def select_player(self, selected):
        tree = self.player_selected if selected else self.player_available
        if tree.selection():
            self.focus_player = tree.selection()[0]
            if selected:
                self.player_mode.set('생성 제외' if self.player_rules[self.focus_player] == 'exclude' else '생성 대상')

    def player_config(self):
        return {'player_ids': [pid for pid, mode in self.player_rules.items() if mode == 'include'],
                'exclude_player_ids': [pid for pid, mode in self.player_rules.items() if mode == 'exclude']}

    def add_player(self):
        if not self.focus_player:
            return
        self.player_rules[self.focus_player] = 'exclude' if self.player_mode.get() == '생성 제외' else 'include'
        self.sync_players()

    def remove_player(self):
        for pid in self.player_selected.selection():
            self.player_rules.pop(pid, None)
        self.sync_players()

    def sync_players(self):
        for key, ids in self.player_config().items():
            self.variables[key].set(','.join(ids))
        self.render_players()
        self.render_summary()

    def render_players(self):
        self.player_selected.delete(*self.player_selected.get_children())
        for pid, mode in self.player_rules.items():
            player = self.players.get(pid, {})
            self.player_selected.insert('', 'end', iid=pid, values=(pid, player.get('name', '선수 ' + pid), player.get('club_name', ''), '생성 제외' if mode == 'exclude' else '생성 대상'))

    def refresh_note(self):
        preset = self.preset.get()
        status = self.league_status
        if preset in ("top5", *LEAGUES):
            expected = set(LEAGUES.values()) if preset == "top5" else {LEAGUES[preset]}
            missing = expected - set(status.get("resolved", []))
            if missing:
                self.note.set(status.get("error") or "해당 리그 구단 정보를 확인해야 합니다. 세이브 구단 읽기 또는 감시 시작으로 자동 확인합니다.")
                return
            count = sum(bool(expected.intersection(club.get("league_ids", []))) for club in self.catalog.values())
            self.note.set(f'{status.get("season", "현재 시즌")} 일정에서 대상 구단 {count}개 확인 · 이름 또는 ID 검색')
            return
        self.note.set(f'세이브 구단 {len(self.catalog):,}개 · 구단 이름 또는 ID로 검색하세요.')

    def filter_catalog(self):
        self.available.delete(*self.available.get_children())
        query = self.search.get().strip().casefold()
        labels = {value: PRESETS[key].removesuffix("만") for key, value in LEAGUES.items()}
        found = [c for c in self.catalog.values() if not query or query in (str(c["id"]) + " " + c["name"] + " " + c.get("short_name", "")).casefold()]
        for club in sorted(found, key=lambda c: (c["id"] not in self.managed, c["name"]))[:150]:
            leagues = ", ".join(labels.get(v, v) for v in club.get("league_ids", []))
            self.available.insert("", "end", iid=club["id"], values=(club["id"], club["name"], leagues))

    def select_available(self, event=None):
        if self.available.selection():
            self.manual_id.set(self.available.selection()[0])

    def select_rule(self, event=None):
        if self.selected.selection():
            key = self.selected.selection()[0]
            self.manual_id.set(key)
            self.club_direction.set(DIRECTIONS[self.rules[key]])

    def add_club(self):
        cid = self.manual_id.get().strip()
        if not cid.isdigit():
            messagebox.showinfo("구단 설정", "검색 결과에서 구단을 선택하거나 숫자 구단 ID를 입력하세요.")
            return
        self.rules[cid] = {value: key for key, value in DIRECTIONS.items()}[self.club_direction.get()]
        self.preset.set("custom")
        self.render_rules()
        self.render_summary()

    def remove_club(self):
        for key in self.selected.selection():
            self.rules.pop(key, None)
        self.render_rules()
        self.render_summary()

    def render_rules(self):
        self.selected.delete(*self.selected.get_children())
        for cid, direction in self.rules.items():
            self.selected.insert("", "end", iid=cid, values=(cid, self.catalog.get(cid, {}).get("name", "구단 " + cid), DIRECTIONS[direction]))


class AdvancedPanel:
    """Optional controls, opened from the scope page instead of shown inline."""

    UNLIMITED = {"max_age": "전체", "daily_limit": "제한 없음", "cooldown_hours": "제한 없음", "settle_seconds": "대기 없음"}

    def __init__(self, parent, variables, save, close):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 16))
        ttk.Label(top, text="고급설정", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="창 닫기", command=close).pack(side="right")
        advanced = ttk.Frame(parent, style="Card.TFrame", padding=20)
        advanced.pack(fill="x")
        ttk.Label(advanced, text="추가 조건 · 호출량", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for index, (key, label) in enumerate((("max_age", "최대 나이"), ("daily_limit", "최근 24시간 호출 상한 · 회"), ("cooldown_hours", "같은 선수 재생성 간격 · 시간"), ("settle_seconds", "생성 전 대기 · 초")), start=1):
            ttk.Label(advanced, text=label, style="CardText.TLabel").grid(row=index, column=0, sticky="w", padx=(0, 16), pady=6)
            variables[key] = tk.StringVar()
            ttk.Combobox(advanced, textvariable=variables[key], values=(self.UNLIMITED[key],), width=24).grid(row=index, column=1, sticky="ew", pady=6)
        ttk.Label(advanced, text="0 또는 빈칸은 제한 없음", style="CardMuted.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 12))
        ttk.Label(advanced, text="저장 갱신 간격 · 회", style="CardText.TLabel").grid(row=6, column=0, sticky="w", padx=(0, 16), pady=6)
        variables["save_update_interval"] = tk.StringVar()
        ttk.Spinbox(advanced, textvariable=variables["save_update_interval"], from_=1, to=999999, width=24).grid(row=6, column=1, sticky="ew", pady=6)
        variables["initial_generation"] = tk.BooleanVar()
        ttk.Checkbutton(advanced, style="Card.TCheckbutton", text="처음 발견한 선수도 생성", variable=variables["initial_generation"]).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        advanced.columnconfigure(1, weight=1)
        ttk.Button(parent, text="고급설정 저장", style="Primary.TButton", command=save).pack(anchor="w", pady=(16, 0))
