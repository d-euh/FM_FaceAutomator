"""Native generation-scope page with presets and searchable per-club directions."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from scope_rules import DIRECTIONS, LEAGUES, PRESETS, describe, migrate_scope


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
        self.search = tk.StringVar()
        self.manual_id = tk.StringVar()
        self.club_direction = tk.StringVar(value=DIRECTIONS["both"])
        self.note = tk.StringVar(value="선수·이적을 읽으면 세이브의 구단을 이름으로 검색할 수 있습니다.")
        self.summary = tk.StringVar()
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 18))
        ttk.Label(top, text="생성 범위", style="Title.TLabel").pack(side="left")
        columns = ttk.Frame(parent)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1)
        columns.columnconfigure(1, weight=2)
        left = ttk.Frame(columns, style="Card.TFrame", padding=20)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = ttk.Frame(columns, style="Card.TFrame", padding=20)
        right.grid(row=0, column=1, sticky="nsew")
        ttk.Label(left, text="빠른 선택", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
        buttons = ttk.Frame(left, style="Card.TFrame")
        buttons.pack(fill="x")
        self.buttons = {}
        for index, (key, title) in enumerate(PRESETS.items()):
            button = ttk.Button(buttons, text=title, command=lambda k=key: self.choose_preset(k))
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0, 6), pady=4)
            self.buttons[key] = button
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        ttk.Label(left, text="이동 방향", style="CardTitle.TLabel").pack(anchor="w", pady=(22, 8))
        ttk.Combobox(left, textvariable=self.direction, values=list(DIRECTIONS.values()), state="readonly", width=26).pack(fill="x")
        self.direction.trace_add("write", lambda *_: self.render_summary())
        ttk.Label(left, textvariable=self.summary, style="CardText.TLabel", wraplength=350).pack(fill="x", pady=6)
        ttk.Button(left, text="범위 저장", style="Primary.TButton", command=save).pack(fill="x", pady=(16, 0))
        ttk.Button(left, text="고급설정", command=advanced).pack(anchor="w", pady=(10, 0))
        if generate:
            ttk.Button(left, text="현재 선수 생성 대기", command=generate).pack(anchor="w", pady=(10, 0))
        ttk.Label(right, text="구단 직접 설정", style="CardTitle.TLabel").pack(anchor="w")
        search = ttk.Frame(right, style="Card.TFrame")
        search.pack(fill="x")
        ttk.Entry(search, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(search, text="구단 목록 불러오기", command=read).pack(side="right")
        ttk.Label(right, textvariable=self.note, style="CardMuted.TLabel", wraplength=600).pack(anchor="w", pady=8)
        self.available = ttk.Treeview(right, columns=("id", "name", "league"), show="headings", height=3, selectmode="browse")
        for key, title, width in (("id", "구단 ID", 85), ("name", "구단 이름", 245), ("league", "리그", 130)):
            self.available.heading(key, text=title)
            self.available.column(key, width=width, stretch=key == "name")
        self.available.pack(fill="x")
        self.available.bind("<<TreeviewSelect>>", self.select_available)
        self.search.trace_add("write", lambda *_: self.filter_catalog())
        form = ttk.Frame(right, style="Card.TFrame")
        form.pack(fill="x", pady=6)
        ttk.Entry(form, textvariable=self.manual_id, width=12).pack(side="left", padx=(0, 6))
        ttk.Combobox(form, textvariable=self.club_direction, values=list(DIRECTIONS.values()), state="readonly", width=19).pack(side="left", padx=(0, 6))
        ttk.Button(form, text="추가 · 방향 변경", command=self.add_club).pack(side="left")
        ttk.Label(right, text="선택한 구단", style="CardTitle.TLabel").pack(anchor="w", pady=(6, 8))
        self.selected = ttk.Treeview(right, columns=("id", "name", "direction"), show="headings", height=2, selectmode="browse")
        for key, title, width in (("id", "구단 ID", 85), ("name", "구단 이름", 245), ("direction", "생성 방향", 150)):
            self.selected.heading(key, text=title)
            self.selected.column(key, width=width, stretch=key == "name")
        self.selected.pack(fill="x")
        self.selected.bind("<<TreeviewSelect>>", self.select_rule)
        row = ttk.Frame(right, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="선택 구단 삭제", command=self.remove_club).pack(side="left")
        ttk.Checkbutton(row, style="Card.TCheckbutton", text="내가 맡은 구단도 함께 포함", variable=self.include_managed, command=self.render_summary).pack(side="right")
        ttk.Label(right, text="선수 직접 설정", style="CardTitle.TLabel").pack(anchor="w", pady=(18, 8))
        search = ttk.Frame(right, style="Card.TFrame")
        search.pack(fill="x")
        ttk.Entry(search, textvariable=self.player_search).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(search, text="선수 목록 불러오기", command=read).pack(side="right")
        ttk.Label(right, textvariable=self.player_note, style="CardMuted.TLabel").pack(anchor="w", pady=6)
        self.player_available = self.player_table(right, (("id", "선수 ID", 80), ("name", "선수 이름", 200), ("club", "소속 구단", 200)), 3)
        self.player_available.bind("<<TreeviewSelect>>", lambda event: self.select_player(False))
        self.player_available.bind("<Double-1>", lambda event: self.add_player())
        form = ttk.Frame(right, style="Card.TFrame")
        form.pack(fill="x", pady=6)
        ttk.Combobox(form, textvariable=self.player_mode, values=("생성 대상", "생성 제외"), state="readonly", width=14).pack(side="left", padx=(0, 8))
        ttk.Button(form, text="선수 추가 · 변경", command=self.add_player).pack(side="left")
        ttk.Label(right, text="선택한 선수", style="CardTitle.TLabel").pack(anchor="w", pady=(6, 8))
        self.player_selected = self.player_table(right, (("id", "선수 ID", 80), ("name", "선수 이름", 180), ("club", "소속 구단", 150), ("mode", "처리", 80)), 2)
        self.player_selected.bind("<<TreeviewSelect>>", lambda event: self.select_player(True))
        ttk.Button(right, text="선택 선수 삭제", command=self.remove_player).pack(anchor="w", pady=(8, 0))
        self.player_search.trace_add('write', self.queue_player_search)

    def value(self):
        reverse = {label: key for key, label in DIRECTIONS.items()}
        return {"preset": self.preset.get(), "direction": reverse[self.direction.get()], "clubs": dict(self.rules), "include_managed": self.include_managed.get()}

    def load(self, config):
        value = migrate_scope(config)
        self.rules = dict(value["clubs"])
        self.preset.set(value["preset"])
        self.direction.set(DIRECTIONS[value["direction"]])
        self.include_managed.set(value.get("include_managed", False))
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
        self.summary.set("현재 범위: " + describe({"scope_rules": rules} | self.player_config()))
        for key, button in self.buttons.items():
            selected = key == rules["preset"]
            button.configure(style="Primary.TButton" if selected else "TButton", text=("✓ " if selected else "") + PRESETS[key])
        self.refresh_note()
        self.changed()

    def set_catalog(self, clubs, managed, status):
        self.catalog = {str(c["id"]): c for c in clubs}
        self.managed = managed
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
        self.player_note.set(f'이름·영문 이름·구단·ID 검색 · 최대 {len(available)}명 표시' if available else '검색 결과가 없습니다. 선수 목록을 불러오거나 검색어를 바꿔 주세요.')
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
