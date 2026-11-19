"""Native generation-scope page with presets and searchable per-club directions."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from scope_rules import DIRECTIONS, LEAGUES, PRESETS, describe, migrate_scope


class ScopePanel:
    def __init__(self, parent, variables, save, read, home, changed, advanced):
        self.variables, self.changed = variables, changed
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
        ttk.Button(top, text="홈으로", command=home).pack(side="right")
        ttk.Label(parent, text="어느 구단의 어떤 이동을 만들지 선택하세요. 변경한 범위는 저장 후 감시를 다시 시작하면 적용됩니다.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
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
        ttk.Label(left, text="영입은 새 구단, 방출은 이전 구단을 기준으로 판단합니다.\n방출 후 선택하지 않은 구단으로 옮겨도 생성합니다.\n무소속 상태에는 새 유니폼이 없어 생성하지 않습니다.", style="CardMuted.TLabel", wraplength=350).pack(anchor="w", pady=14)
        ttk.Label(left, textvariable=self.summary, style="CardText.TLabel", wraplength=350).pack(fill="x", pady=6)
        ttk.Button(left, text="범위 저장", style="Primary.TButton", command=save).pack(fill="x", pady=(16, 0))
        ttk.Button(left, text="고급설정", command=advanced).pack(anchor="w", pady=(10, 0))
        ttk.Label(right, text="구단 직접 설정", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(right, text="구단을 추가하면 ‘직접 설정’으로 전환합니다. 구단마다 방향을 다르게 지정할 수 있습니다.", style="CardMuted.TLabel", wraplength=600).pack(anchor="w", pady=(6, 12))
        search = ttk.Frame(right, style="Card.TFrame")
        search.pack(fill="x")
        ttk.Entry(search, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(search, text="세이브 구단 읽기", command=read).pack(side="right")
        ttk.Label(right, textvariable=self.note, style="CardMuted.TLabel", wraplength=600).pack(anchor="w", pady=8)
        self.available = ttk.Treeview(right, columns=("id", "name", "league"), show="headings", height=6, selectmode="browse")
        for key, title, width in (("id", "구단 ID", 85), ("name", "구단 이름", 245), ("league", "리그", 130)):
            self.available.heading(key, text=title)
            self.available.column(key, width=width, stretch=key == "name")
        self.available.pack(fill="x")
        self.available.bind("<<TreeviewSelect>>", self.select_available)
        self.search.trace_add("write", lambda *_: self.filter_catalog())
        form = ttk.Frame(right, style="Card.TFrame")
        form.pack(fill="x", pady=12)
        ttk.Entry(form, textvariable=self.manual_id, width=12).pack(side="left", padx=(0, 6))
        ttk.Combobox(form, textvariable=self.club_direction, values=list(DIRECTIONS.values()), state="readonly", width=19).pack(side="left", padx=(0, 6))
        ttk.Button(form, text="추가 · 방향 변경", command=self.add_club).pack(side="left")
        ttk.Label(right, text="선택한 구단", style="CardTitle.TLabel").pack(anchor="w", pady=(6, 8))
        self.selected = ttk.Treeview(right, columns=("id", "name", "direction"), show="headings", height=5, selectmode="browse")
        for key, title, width in (("id", "구단 ID", 85), ("name", "구단 이름", 245), ("direction", "생성 방향", 150)):
            self.selected.heading(key, text=title)
            self.selected.column(key, width=width, stretch=key == "name")
        self.selected.pack(fill="x")
        self.selected.bind("<<TreeviewSelect>>", self.select_rule)
        row = ttk.Frame(right, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="선택 구단 삭제", command=self.remove_club).pack(side="left")
        ttk.Checkbutton(row, style="Card.TCheckbutton", text="내가 맡은 구단도 함께 포함", variable=self.include_managed, command=self.render_summary).pack(side="right")

    def value(self):
        reverse = {label: key for key, label in DIRECTIONS.items()}
        return {"preset": self.preset.get(), "direction": reverse[self.direction.get()], "clubs": dict(self.rules), "include_managed": self.include_managed.get()}

    def load(self, config):
        value = migrate_scope(config)
        self.rules = dict(value["clubs"])
        self.preset.set(value["preset"])
        self.direction.set(DIRECTIONS[value["direction"]])
        self.include_managed.set(value.get("include_managed", False))
        self.render_rules()
        self.render_summary()

    def choose_preset(self, key):
        self.preset.set(key)
        self.render_summary()

    def render_summary(self):
        rules = self.value()
        self.summary.set("현재 범위: " + describe({"scope_rules": rules}))
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

    def __init__(self, parent, variables, save, scope, home):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 16))
        ttk.Label(top, text="고급설정", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="홈으로", command=home).pack(side="right")
        ttk.Button(top, text="생성 범위로", command=scope).pack(side="right", padx=8)
        ttk.Label(parent, text="기본값은 추가 제한 없음입니다. 필요한 경우에만 변경하세요.", style="Muted.TLabel").pack(anchor="w", pady=(0, 16))
        advanced = ttk.Frame(parent, style="Card.TFrame", padding=20)
        advanced.pack(fill="x")
        ttk.Label(advanced, text="추가 조건 · 호출량", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for index, (key, label) in enumerate((("player_ids", "추가 선수 ID (쉼표)"), ("exclude_player_ids", "제외 선수 ID (쉼표)"), ("regen_player_ids", "생성선수 r- 매핑 ID (쉼표)"))):
            variables[key] = tk.StringVar()
            ttk.Label(advanced, text=label, style="CardText.TLabel").grid(row=index + 1, column=0, sticky="w", padx=(0, 16), pady=5)
            ttk.Entry(advanced, textvariable=variables[key]).grid(row=index + 1, column=1, sticky="ew", pady=5)
        ttk.Label(advanced, text="ID 항목을 비워두면 별도 추가·제외·매핑을 지정하지 않습니다.", style="CardMuted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 16))
        for index, (key, label) in enumerate((("max_age", "최대 나이"), ("daily_limit", "최근 24시간 호출 상한 · 회"), ("cooldown_hours", "같은 선수 재생성 간격 · 시간"), ("settle_seconds", "대기열 추가 후 생성 대기 · 초")), start=5):
            ttk.Label(advanced, text=label, style="CardText.TLabel").grid(row=index, column=0, sticky="w", padx=(0, 16), pady=6)
            variables[key] = tk.StringVar()
            ttk.Combobox(advanced, textvariable=variables[key], values=(self.UNLIMITED[key],), width=24).grid(row=index, column=1, sticky="ew", pady=6)
        ttk.Label(advanced, text="숫자를 입력하면 해당 제한을 적용합니다. 0 또는 빈칸은 제한 없음입니다.", style="CardMuted.TLabel").grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 16))
        ttk.Label(advanced, text="감시 간격 · 세이브 업데이트 횟수", style="CardText.TLabel").grid(row=10, column=0, sticky="w", padx=(0, 16), pady=6)
        variables["save_update_interval"] = tk.StringVar()
        ttk.Spinbox(advanced, textvariable=variables["save_update_interval"], from_=1, to=999999, width=24).grid(row=10, column=1, sticky="ew", pady=6)
        ttk.Label(advanced, text="1 = 매 업데이트마다 생성 · 2 = 저장 갱신 2회마다 생성\n이적은 매번 기록하고, 지정 횟수가 차면 누적 작업을 처리합니다. 최초 기준 읽기는 횟수에서 제외합니다.", style="CardMuted.TLabel", wraplength=900).grid(row=11, column=0, columnspan=2, sticky="w", pady=(4, 16))
        variables["initial_generation"] = tk.BooleanVar()
        ttk.Checkbutton(advanced, style="Card.TCheckbutton", text="처음 발견한 선수도 생성 · 기본값은 기준만 기록", variable=variables["initial_generation"]).grid(row=12, column=0, columnspan=2, sticky="w", pady=(10, 0))
        advanced.columnconfigure(1, weight=1)
        ttk.Button(parent, text="고급설정 저장", style="Primary.TButton", command=save).pack(anchor="w", pady=(16, 0))
