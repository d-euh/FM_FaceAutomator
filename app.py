"""Korean native desktop UI. No web server or Face Studio dependency."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from engine import DEFAULTS, WATCH_POLL_SECONDS, Engine, PastSaveError, detection_messages, load_config, player_kit_variant, process_lock, read_source, write_atomic
from workspaces import select_workspace
from assets import AssetCatalog, AssetError, reference_png, source_exclusions
from discovery import discover_defaults
import scope_rules
from scope_ui import AdvancedPanel, ScopePanel
from gunzo import BUNDLED_FONTS, bundled_font_path, default_font_path, name_font
from theme import BACKGROUND, LOG_BACKGROUND, MUTED, PREVIEW_BACKGROUND, PURPLE, apply_theme


ROOT = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
KIT_LABELS = {"home": "홈", "away": "원정", "third": "서드"}


class App:
    def __init__(self, window, config_path):
        self.window, self.path = window, Path(config_path).resolve()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.thread = None
        self.photo = None
        self.vars = {}
        self.path_scan = 0
        self.path_scanning = False
        self.last_discovery_inputs = None
        self.start_after_discovery = False
        self.discovery_stop = threading.Event()
        self.dashboard_key = None
        self.recent_results = []
        self.recent_index = 0
        self.recent_state = None
        self.catalog_key = None
        self.job_choices = {}
        self.job_records = {}
        self.queue_buttons = {}
        self.status = tk.StringVar(value="경로와 범위를 확인하고 감시를 시작하세요.")
        self.scope_summary = tk.StringVar(value="내가 맡은 구단만 · 방출·영입 모두")
        window.title("FM Face Automator")
        window.geometry("1220x870")
        window.minsize(1060, 750)
        family = "Malgun Gothic" if os.name == "nt" else "Noto Sans CJK KR"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family=family, size=10)
        apply_theme(window, family)
        tk.Frame(window, height=4, background=PURPLE).pack(fill="x")
        header = ttk.Frame(window, padding=(24, 20, 24, 16))
        header.pack(fill="x")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="FM Face Automator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="세이브가 바뀌면, 새로운 팀의 페이스온으로", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.tabs = ttk.Notebook(window)
        self.tabs.pack(fill="both", expand=True, padx=20)
        self.home_tab, home = self.page(scroll=True)
        self.scope_tab, scope = self.page(scroll=True)
        self.jobs_tab, jobs = self.page()
        self.settings_tab, settings = self.page(scroll=True)
        self.prompts_tab, prompts = self.page(scroll=True)
        for host, label in ((self.home_tab, "홈"), (self.scope_tab, "생성 범위"), (self.jobs_tab, "작업 대기열"), (self.settings_tab, "폴더 · 연결"), (self.prompts_tab, "커스텀 지시")):
            self.tabs.add(host, text=label)
        ttk.Label(header, text="v0.10.2", style="Badge.TLabel").pack(side="right", padx=12)
        self.build_home(home)
        self.scope_panel = ScopePanel(scope, self.vars, self.save, self.scan, self.update_scope_summary,
                                      self.open_advanced)
        self.advanced_window = tk.Toplevel(window)
        self.advanced_window.withdraw()
        self.advanced_window.title("고급설정 · FM Face Automator")
        self.advanced_window.transient(window)
        self.advanced_window.geometry("940x740")
        self.advanced_window.minsize(820, 560)
        self.advanced_window.protocol("WM_DELETE_WINDOW", self.advanced_window.withdraw)
        self.advanced_window.bind("<Escape>", lambda event: self.advanced_window.withdraw())
        advanced_host, advanced = self.page(scroll=True, parent=self.advanced_window)
        advanced_host.pack(fill="both", expand=True)
        self.advanced_panel = AdvancedPanel(advanced, self.vars, self.save, self.advanced_window.withdraw)
        settings.columnconfigure(1, weight=1)
        self.fields(settings)
        self.prompt_fields(prompts)
        jobs.columnconfigure(0, weight=1)
        jobs.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(jobs)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for title, callback in [("자동 생성 시작", self.start), ("작업 종료 후 멈춤", self.pause)]:
            ttk.Button(toolbar, text=title, command=callback, style="Primary.TButton" if callback == self.start else "TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="관리 도구", command=self.tools_popup).pack(side="right")
        ttk.Label(jobs, textvariable=self.status, wraplength=1000, style="Muted.TLabel").grid(row=1, column=0, sticky="ew", pady=(0, 12))
        table = ttk.Frame(jobs)
        table.grid(row=2, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("id", "player", "club", "status", "note"), show="headings", height=8)
        for key, label, width in [("id", "작업", 45), ("player", "선수", 145), ("club", "이동 · 새 소속팀", 210), ("status", "상태", 100), ("note", "설명", 400)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=key == "note")
        self.tree.grid(row=0, column=0, sticky="nsew")
        queue_scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        queue_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=queue_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Double-1>", lambda event: self.open_job())
        actions = ttk.Frame(jobs)
        actions.grid(row=3, column=0, sticky="ew", pady=12)
        for title, callback in [("개별 지시", self.edit_player), ("결과 보기", self.preview), ("다시 시도", self.retry), ("유니폼 변경", self.choose_kit)]:
            button = ttk.Button(actions, text=title, command=callback, state="disabled")
            button.pack(side="left", padx=(0, 6))
            self.queue_buttons[title] = button
        self.detail = tk.StringVar(value="작업을 선택해 개별 지시를 편집하세요. 편집 중인 작업은 합성을 기다립니다.")
        ttk.Label(jobs, textvariable=self.detail, wraplength=1000, style="Muted.TLabel").grid(row=5, column=0, sticky="ew", pady=(0, 6))
        log_host = ttk.Frame(window, padding=(20, 10, 20, 16))
        log_host.pack(side="bottom", fill="x", before=self.tabs)
        log_bar = ttk.Frame(log_host)
        log_bar.pack(fill="x")
        ttk.Label(log_bar, text="최근 활동", style="Muted.TLabel").pack(side="left", padx=(0, 12))
        ttk.Label(log_bar, textvariable=self.status, style="Muted.TLabel", wraplength=820).pack(side="left", fill="x", expand=True)
        self.log_toggle = ttk.Button(log_bar, text="활동 기록 펼치기", style="Compact.TButton", command=self.toggle_log)
        self.log_toggle.pack(side="right")
        self.log = tk.Text(log_host, height=4, font=(family, 9), state="disabled", background=LOG_BACKGROUND, foreground=MUTED, relief="flat", padx=10, pady=8)
        self.load()
        self.window.after(100, self.auto_paths)
        self.window.after(500, self.drain)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def open_advanced(self):
        self.advanced_window.deiconify()
        self.advanced_window.lift()
        self.advanced_window.focus_set()

    def toggle_log(self):
        if self.log.winfo_manager():
            self.log.pack_forget()
            self.log_toggle.configure(text="활동 기록 펼치기")
        else:
            self.log.pack(fill="x", pady=(8, 0))
            self.log_toggle.configure(text="활동 기록 접기")

    def tools_popup(self):
        win = tk.Toplevel(self.window)
        win.title("관리 도구")
        win.transient(self.window)
        frame = ttk.Frame(win, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="필요할 때만 사용하는 도구", style="Section.TLabel").pack(anchor="w", pady=(0, 16))
        for label, callback in (("세이브 분석 · 기준 확인", self.scan), ("현재 선수도 생성 대기", self.enqueue),
                                ("감지 진단 내보내기", self.export_detection), ("선수 목록 내보내기", self.export), ("변경 전 페이스팩 복원", self.restore)):
            def run(action=callback):
                win.destroy()
                action()
            ttk.Button(frame, text=label, command=run, state="disabled" if self.active() and callback != self.export_detection else "normal").pack(fill="x", pady=4)
        ttk.Label(frame, text="이미지 저장과 config.xml 갱신, 저장 실패 재시도는 자동으로 처리합니다.\nAI 호출 실패는 ‘다시 시도’를 선택해야 재요청합니다.", style="Muted.TLabel", wraplength=420).pack(anchor="w", pady=(16, 0))

    def page(self, scroll=False, parent=None):
        host = ttk.Frame(self.tabs if parent is None else parent)
        if not scroll:
            content = ttk.Frame(host, padding=20)
            content.pack(fill="both", expand=True)
            return host, content
        canvas = tk.Canvas(host, highlightthickness=0, background=BACKGROUND)
        bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        content = ttk.Frame(canvas, padding=20)
        item = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        def wheel(event):
            widget = event.widget
            while widget is not None:
                if widget == content or widget == canvas:
                    delta = -1 if getattr(event, "num", 0) == 4 else 1 if getattr(event, "num", 0) == 5 else -int(event.delta / 120)
                    canvas.yview_scroll(delta, "units")
                    break
                widget = getattr(widget, "master", None)
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.window.bind_all(event, wheel, add="+")
        return host, content

    def build_home(self, parent):
        parent.configure(padding=(20, 12))
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        parent.rowconfigure(0, weight=1)
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        hero = ttk.Frame(left, style="Panel.Card.TFrame", padding=24)
        hero.pack(fill="both", expand=True)
        ttk.Label(hero, text="저장 후 자동으로 완성되는 페이스온", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(hero, text="이적 감지 → 선택한 범위 확인 → Codex 합성 → 이미지·매핑 저장", style="CardMuted.TLabel", wraplength=560).pack(anchor="w", pady=(8, 16))
        ttk.Label(hero, text="선택한 생성 범위", style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(hero, textvariable=self.scope_summary, style="CardTitle.TLabel", wraplength=540).pack(anchor="w", pady=(6, 14))
        ttk.Label(hero, text="01 세이브 연결     02 생성 범위 선택     03 자동 생성", style="CardMuted.TLabel").pack(anchor="w", pady=(0, 16))
        ttk.Label(hero, textvariable=self.status, style="CardMuted.TLabel", wraplength=540).pack(anchor="w", pady=(0, 12))
        controls = ttk.Frame(hero, style="Card.TFrame")
        controls.pack(fill="x")
        ttk.Button(controls, text="자동 생성 시작", style="Primary.TButton", command=self.start).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="작업 종료 후 멈춤", command=self.pause).pack(side="left")
        stats = ttk.Frame(left)
        stats.pack(side="bottom", fill="x", pady=(16, 0), before=hero)
        self.metric_vars = {}
        for key, label in (("pending", "대기 중"), ("running", "생성 중"), ("applied", "저장 완료")):
            card = ttk.Frame(stats, style="Panel.Card.TFrame", padding=16)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10) if key != "applied" else 0)
            ttk.Label(card, text=label, style="CardMuted.TLabel").pack(anchor="w")
            self.metric_vars[key] = tk.StringVar(value="0")
            ttk.Label(card, textvariable=self.metric_vars[key], style="Metric.TLabel").pack(anchor="w", pady=(4, 0))
        recent = ttk.Frame(parent, style="Panel.Card.TFrame", padding=(20, 12))
        recent.grid(row=0, column=1, sticky="nsew")
        ttk.Label(recent, text="최근 생성된 페이스온", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 14))
        self.recent_canvas = tk.Canvas(recent, width=350, height=350, background=PREVIEW_BACKGROUND, highlightthickness=0)
        self.recent_canvas.pack()
        self.recent_canvas.create_text(175, 175, text="첫 페이스온을 기다리고 있습니다\n생성이 끝나면 여기에 표시됩니다", fill=MUTED, font="TkDefaultFont", justify="center")
        self.recent_name = tk.StringVar(value="350 × 350 · 영문 이름 · ID 파일명")
        ttk.Label(recent, textvariable=self.recent_name, style="CardText.TLabel", wraplength=350).pack(anchor="w", pady=(14, 0))
        navigation = ttk.Frame(recent, style="Card.TFrame")
        navigation.pack(fill="x", pady=(10, 0))
        self.recent_previous = ttk.Button(navigation, text="◀ 이전", command=lambda: self.browse_recent(-1), state="disabled")
        self.recent_previous.pack(side="left")
        self.recent_position = tk.StringVar(value="0 / 0")
        ttk.Label(navigation, textvariable=self.recent_position, style="CardText.TLabel", anchor="center").pack(side="left", fill="x", expand=True)
        self.recent_next = ttk.Button(navigation, text="다음 ▶", command=lambda: self.browse_recent(1), state="disabled")
        self.recent_next.pack(side="right")

    def update_scope_summary(self):
        if hasattr(self, "config"):
            draft = self.config if self.active() else self.config | {"scope_rules": self.scope_panel.value()}
            self.scope_summary.set(scope_rules.describe(draft))

    def update_dashboard(self, engine):
        counts = {r[0]: r[1] for r in engine.db.execute("SELECT status,count(*) FROM jobs GROUP BY status")}
        for key, var in self.metric_vars.items():
            var.set(str(counts.get(key, 0)))
        catalog_key = (self.config["state_dir"], engine.meta("source_stamp"), engine.meta("catalog_key"), engine.meta("catalog_updated"))
        if catalog_key != self.catalog_key:
            self.catalog_key = catalog_key
            self.scope_panel.set_catalog(json.loads(engine.meta("club_catalog") or "[]"),
                                         json.loads(engine.meta("managed") or "[]"), json.loads(engine.meta("league_status") or "{}"))
        state = self.config["state_dir"]
        selected = self.recent_results[self.recent_index]["id"] if self.recent_results and self.recent_index else None
        if state != self.recent_state:
            selected = None
        self.recent_state = state
        self.recent_results = engine.recent_results()
        self.recent_index = next((i for i, item in enumerate(self.recent_results) if item["id"] == selected), 0)
        self.show_recent()

    def browse_recent(self, direction):
        if self.recent_results:
            self.recent_index = min(max(self.recent_index + direction, 0), len(self.recent_results) - 1)
            self.show_recent()

    def show_recent(self):
        if not self.recent_results:
            self.clear_preview()
            return
        latest = self.recent_results[self.recent_index]
        self.recent_position.set(f'{self.recent_index + 1} / {len(self.recent_results)}')
        self.recent_previous.configure(state="normal" if self.recent_index else "disabled")
        self.recent_next.configure(state="normal" if self.recent_index + 1 < len(self.recent_results) else "disabled")
        key = (self.recent_state, latest["id"], latest["artifact"], latest["stamp"], latest["status"])
        if key != self.dashboard_key:
            self.dashboard_key = key
            self.recent_canvas.delete("all")
            try:
                with Image.open(latest["artifact"]) as image:
                    image = image.convert("RGBA")
                    image.thumbnail((350, 350), Image.Resampling.LANCZOS)
                    self.recent_photo = ImageTk.PhotoImage(image, master=self.window)
                self.recent_canvas.create_image(175, 175, image=self.recent_photo)
                status = {"applied": "저장 완료", "generated": "저장 대기", "apply_failed": "저장 실패",
                          "superseded": "이전 결과", "failed": "작업 실패", "blocked": "보류",
                          "pending": "재시도 대기", "running": "재생성 중", "interrupted": "중단"}.get(latest["status"], latest["status"])
                self.recent_name.set(f'{latest["name"]}\n{latest["club_name"]} · 작업 {latest["id"]} · {status}')
            except Exception:
                self.recent_canvas.create_text(175, 175, text="이미지 파일을 열 수 없습니다", fill=MUTED, font="TkDefaultFont")
                self.recent_name.set("결과 파일을 확인하세요.")

    def clear_preview(self):
        self.dashboard_key = None
        self.recent_results = []
        self.recent_index = 0
        self.recent_position.set("0 / 0")
        self.recent_previous.configure(state="disabled")
        self.recent_next.configure(state="disabled")
        self.recent_canvas.delete("all")
        self.recent_canvas.create_text(175, 175, text="아직 생성된 페이스온이 없습니다", fill=MUTED, font="TkDefaultFont")
        self.recent_name.set("350 × 350 · 영문 이름 · ID 파일명")

    def fields(self, parent):
        ttk.Label(parent, text="폴더 · Codex · 글꼴 연결", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        form = ttk.Frame(parent, style="Panel.Card.TFrame", padding=22)
        form.grid(row=1, column=0, columnspan=3, sticky="ew")
        parent.columnconfigure(0, weight=1)
        parent = form
        parent.columnconfigure(1, weight=1)
        rows = [("source", "연결할 세이브 파일", "file"),
                ("portraits_dir", "기존 페이스팩 폴더", "dir"), ("kits_dir", "유니폼 키트 폴더", "dir"),
                ("pack_dir", "생성 페이스팩 저장 위치", "dir"), ("codex", "Codex 실행 파일", "exe"),
                ("graphics_root", "자료 검색 위치 · 선택", "dir"),
                ("name_font_path", "이름 글꼴 · TTF/OTF/TTC", "font")]
        for index, (key, label, chooser) in enumerate(rows, 1):
            ttk.Label(parent, text=label, style="CardText.TLabel").grid(row=index, column=0, sticky="w", padx=(0, 18), pady=10)
            self.vars[key] = tk.StringVar()
            if chooser == "font":
                entry = ttk.Combobox(parent, textvariable=self.vars[key], values=[str(bundled_font_path(font)) for font in BUNDLED_FONTS])
                entry.bind("<<ComboboxSelected>>", lambda event: event.widget.xview_moveto(1))
            else:
                entry = ttk.Entry(parent, textvariable=self.vars[key])
            entry.grid(row=index, column=1, sticky="ew", pady=10)
            buttons = ttk.Frame(parent, style="Card.TFrame")
            buttons.grid(row=index, column=2, padx=(10, 0))
            ttk.Button(buttons, text="폰트 불러오기" if chooser == "font" else "선택", command=lambda k=key, c=chooser: self.choose(k, c)).pack(side="left")
            if chooser == "font":
                ttk.Button(buttons, text="기본 글꼴", command=self.default_font).pack(side="left", padx=(8, 0))
        self.workspace_note = tk.StringVar(value="세이브별 이적 기준과 작업 기록은 자동으로 분리·관리합니다.")
        ttk.Label(parent, textvariable=self.workspace_note, style="CardMuted.TLabel", wraplength=1000).grid(row=8, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Label(parent, text="합성에 사용할 유니폼", style="CardText.TLabel").grid(row=9, column=0, sticky="w", pady=12)
        self.vars["kit_variant"] = tk.StringVar()
        ttk.Combobox(parent, textvariable=self.vars["kit_variant"], values=list(KIT_LABELS.values()), state="readonly", width=14).grid(row=9, column=1, sticky="w")
        self.path_status = tk.StringVar(value="폴더와 Codex 경로를 자동 확인합니다. 다른 항목만 직접 바꾸세요.")
        ttk.Label(parent, textvariable=self.path_status, style="CardMuted.TLabel", wraplength=1000).grid(row=10, column=0, columnspan=3, sticky="w", pady=20)
        ttk.Label(parent, text="기본 제공 폰트: Koverwatch(기본값) · Bebas Neue · Venus Rising. 이름 글꼴의 드롭다운에서 선택하세요.\n다른 폰트를 직접 선택할 수도 있습니다. 변경 후 설정을 저장하세요.", style="CardMuted.TLabel", wraplength=1000).grid(row=11, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(parent, text="기존 파일이 있는 페이스팩에도 저장할 수 있습니다. 교체 전 이미지는 자동 백업합니다.\n골키퍼는 골키퍼 키트를 자동 선택합니다. 해당 자료가 없으면 작업을 보류하고 유니폼 변경을 안내합니다.", style="CardMuted.TLabel", wraplength=1000).grid(row=12, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Button(parent, text="설정 저장", style="Primary.TButton", command=self.save).grid(row=13, column=0, sticky="w")
        self.vars["live_refresh_enabled"] = tk.BooleanVar()
        ttk.Checkbutton(parent, text="생성 후 게임 그래픽 갱신 · 실험 기능", variable=self.vars["live_refresh_enabled"],
                        style="Card.TCheckbutton").grid(row=14, column=0, columnspan=3, sticky="w", pady=(22, 8))
        ttk.Label(parent, text="전용 플러그인을 설치한 Steam 26620374에서 사용합니다. 처음에는 꺼져 있습니다.\n선택한 저장 폴더를 게임에 등록하고 재검색합니다. 수동 추가한 새 PNG에는 config.xml 매핑도 필요합니다.\n지원 빌드·파일 해시·게임 대기 상태를 확인하며, 게임 갱신 실패가 AI 재호출을 일으키지는 않습니다.",
                  style="CardMuted.TLabel", wraplength=1000).grid(row=15, column=0, columnspan=3, sticky="w")
        ttk.Button(parent, text="게임 갱신 테스트 · AI 호출 없음", command=self.test_live_refresh).grid(row=16, column=0, columnspan=2, sticky="w", pady=12)
        self.live_status = tk.StringVar(value="실시간 게임 갱신 꺼짐")
        ttk.Label(parent, textvariable=self.live_status, style="CardMuted.TLabel", wraplength=1000).grid(row=17, column=0, columnspan=3, sticky="w")

    def test_live_refresh(self):
        if not self.active() and not self.save():
            return
        if not self.config.get("live_refresh_enabled"):
            messagebox.showinfo("게임 갱신 테스트", "‘생성 후 게임 그래픽 갱신’을 체크하고 설정을 저장하세요.")
            return
        engine = Engine(self.config)
        try:
            if not (Path(self.config["pack_dir"]) / "config.xml").is_file():
                raise ValueError("생성 페이스팩 저장 위치에 config.xml이 있어야 합니다. 먼저 페이스온 하나를 생성하세요.")
            engine.queue_live_refresh()
            engine.pump_live_refresh()
            self.events.put("게임 갱신 테스트 요청 · AI를 호출하지 않습니다. 폴더 · 연결의 갱신 상태를 확인하세요.")
        except Exception as exc:
            messagebox.showerror("게임 갱신 테스트", str(exc))
        finally:
            engine.close()

    def prompt_fields(self, parent):
        ttk.Label(parent, text="커스텀 지시", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        heading = ttk.Frame(parent)
        heading.pack(fill="x")
        ttk.Label(heading, text="모든 선수에게 적용할 지시", style="Section.TLabel").pack(side="left")
        ttk.Button(heading, text="공통 지시 저장", command=self.save).pack(side="right")
        ttk.Label(parent, text="예: 비 오는 경기장에서 골을 넣고 활짝 웃는 모습. 앞머리는 뒤로 넘기고 한 손을 들어주세요.", wraplength=980).pack(anchor="w", pady=(8, 6))
        self.additional_text = tk.Text(parent, height=5, wrap="word", font="TkTextFont")
        self.additional_text.pack(fill="x")
        ttk.Label(parent, text="지시가 있으면 머리카락·표정·자세를 고정하지 않습니다. 얼굴 동일성은 유지합니다.\n공통 지시 저장은 자동 생성을 멈춘 뒤 할 수 있습니다. 개별 대기 작업은 실행 중에도 편집할 수 있습니다.", foreground=MUTED, wraplength=980).pack(anchor="w", pady=10)
        personal = ttk.Frame(parent, style="Card.TFrame", padding=20)
        personal.pack(fill="x", pady=(8, 18))
        ttk.Label(personal, text="대기 작업에만 적용할 개별 지시", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.personal_job = tk.StringVar()
        row = ttk.Frame(personal, style="Card.TFrame")
        row.pack(fill="x")
        self.personal_selector = ttk.Combobox(row, textvariable=self.personal_job, state="readonly")
        self.personal_selector.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.personal_edit_button = ttk.Button(row, text="개별 지시 편집", command=self.edit_chosen_job, state="disabled")
        self.personal_edit_button.pack(side="right")
        ttk.Label(personal, text="선수 이름으로 작업을 선택하세요. 개별 지시는 공통 지시보다 우선하며 해당 작업에만 적용됩니다.", style="CardMuted.TLabel", wraplength=900).pack(anchor="w", pady=(10, 0))
        ttk.Label(parent, text="건조폼 출력: 350×350 고정 · 코너 반경 60px · 하단 그라데이션과 선수 이름").pack(anchor="w", pady=(0, 8))
        ttk.Label(parent, text="기본 사진 스타일과 건조폼은 자동 적용합니다. 원하는 외형·분위기는 위 커스텀 지시에 적어주세요.", style="Muted.TLabel", wraplength=980).pack(anchor="w", pady=(0, 10))
        ttk.Label(parent, text="이름은 AI가 그리지 않고 프로그램이 정확한 문자열로 넣습니다. 이름 수정은 다음 합성부터 반영됩니다.\nPNG와 config.xml을 모두 저장해야 완료 처리합니다. 저장 실패 시 이미지를 보관하고 추가 합성 없이 저장만 재시도합니다.", foreground=MUTED, wraplength=980).pack(anchor="w", pady=10)

    def default_font(self):
        self.vars["name_font_path"].set(str(default_font_path()))

    def choose(self, key, kind):
        if kind == "font":
            value = filedialog.askopenfilename(title="선수 이름 폰트 불러오기", initialdir=str(default_font_path().parent), filetypes=[("글꼴 파일 (TTF / OTF / TTC)", "*.ttf *.otf *.ttc *.TTF *.OTF *.TTC"), ("모든 파일", "*")])
            if value:
                try:
                    name_font(value)
                except Exception as exc:
                    messagebox.showerror("글꼴 오류", str(exc))
                    return
        else:
            value = filedialog.askdirectory() if kind == "dir" else filedialog.askopenfilename(filetypes=[("FM27 / JSON", "*.fm *.json"), ("모든 파일", "*")]) if kind == "file" else filedialog.askopenfilename()
        if value:
            self.vars[key].set(value)
            if key in ("source", "graphics_root"):
                self.auto_paths()

    def auto_paths(self):
        if self.active():
            return
        self.path_scan += 1
        scan_id = self.path_scan
        self.path_scanning = True
        self.path_status.set("폴더·최신 세이브·Codex 경로 자동 확인 중… 확인된 경로는 기본값에 채웁니다.")
        snapshot = {key: self.vars[key].get() for key in ("source", "portraits_dir", "kits_dir", "pack_dir", "graphics_root", "codex")}
        config = dict(self.config)
        for key, value in snapshot.items():
            config[key] = str((self.path.parent / value).resolve()) if value and key != "codex" else value
        def discover():
            try:
                updates, notes = discover_defaults(config, self.path.parent, stop=self.discovery_stop)
            except Exception as exc:
                updates, notes = {}, [str(exc)]
            self.events.put({"path_scan": scan_id, "snapshot": snapshot, "updates": updates, "notes": notes})
        threading.Thread(target=discover, daemon=True).start()

    def accept_paths(self, result):
        if result["path_scan"] != self.path_scan:
            return
        self.path_scanning = False
        changed = []
        for key, value in result["updates"].items():
            # Never overwrite a field the user changed while discovery ran.
            if self.vars[key].get() == result["snapshot"][key]:
                self.vars[key].set(value)
                self.config[key] = value
                changed.append(key)
        self.config = select_workspace(self.config, self.path.parent)
        try:
            write_atomic(self.path, json.dumps(self.config, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as exc:
            self.events.put(f"자동 경로 설정 저장 실패: {exc}")
        missing = [label for key, label in (("source", "세이브"), ("portraits_dir", "얼굴"), ("kits_dir", "유니폼"), ("name_font_path", "글꼴"))
                   if not self.vars[key].get() or not Path(self.vars[key].get()).exists()]
        text = f"자동 경로 확인 완료 · {len(changed)}개 기본값 반영. 표시된 경로가 다르면 직접 바꾸세요."
        if missing:
            text += " 찾지 못한 항목: " + ", ".join(missing)
        if result["notes"]:
            text += f' · 검색 경고 {len(result["notes"])}건'
        self.path_status.set(text)
        self.last_discovery_inputs = {key: self.vars[key].get() for key in result["snapshot"]}
        self.events.put(text)
        if self.start_after_discovery:
            self.start_after_discovery = False
            self.start()

    def load(self):
        if not self.path.exists():
            write_atomic(self.path, json.dumps(DEFAULTS | {"scope_rules": scope_rules.DEFAULT_SCOPE}, ensure_ascii=False, indent=2).encode("utf-8"))
        c = load_config(self.path)
        c["automatic_workspaces"] = True
        c = select_workspace(c, self.path.parent)
        for key, var in self.vars.items():
            value = c[key]
            if key == "kit_variant":
                value = KIT_LABELS[value]
            if key in AdvancedPanel.UNLIMITED and value == 0:
                value = AdvancedPanel.UNLIMITED[key]
            var.set(",".join(value) if isinstance(value, list) else value)
        self.additional_text.insert("1.0", c["additional_instructions"])
        self.config = c
        self.scope_panel.load(c)

    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def save(self):
        if self.active():
            messagebox.showinfo("설정", "현재 작업 후 정지한 다음 설정을 저장하세요.")
            return False
        try:
            c = dict(self.config)
            for key, var in self.vars.items():
                value = var.get()
                if key == "kit_variant":
                    value = {label: variant for variant, label in KIT_LABELS.items()}[value]
                if key in AdvancedPanel.UNLIMITED and str(value).strip() in ("", AdvancedPanel.UNLIMITED[key]):
                    value = 0
                if key in ("club_ids", "player_ids", "exclude_player_ids", "regen_player_ids"):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                    if any(not v.isdigit() for v in value):
                        raise ValueError("ID는 숫자로 입력하세요.")
                elif key in ("daily_limit", "max_age", "save_update_interval"):
                    value = int(value)
                elif key in ("cooldown_hours", "settle_seconds"):
                    value = float(value)
                c[key] = value
            c["style"] = DEFAULTS["style"]
            c["frame_template"] = ""
            c["additional_instructions"] = self.additional_text.get("1.0", "end").strip()
            c["scope_rules"] = self.scope_panel.value()
            c["automatic_workspaces"] = True
            if not c["source"]:
                raise ValueError("세이브 파일을 선택하세요.")
            # Validate before replacing a working configuration.
            temp = self.path.with_name(".config-check.json")
            try:
                write_atomic(temp, json.dumps(c, ensure_ascii=False, indent=2).encode("utf-8"))
                checked = load_config(temp)
                default_font = default_font_path()
                if Path(checked["name_font_path"]).is_file() or Path(checked["name_font_path"]) != default_font:
                    name_font(checked["name_font_path"])
            finally:
                temp.unlink(missing_ok=True)
            write_atomic(self.path, json.dumps(checked, ensure_ascii=False, indent=2).encode("utf-8"))
            self.config = checked
            self.update_scope_summary()
            self.events.put("설정 저장 완료")
            return True
        except Exception as exc:
            messagebox.showerror("설정 오류", str(exc))
            return False

    def background(self, task):
        if self.active() or not self.save():
            return
        self.stop.clear()
        config = dict(self.config)
        def run():
            engine = None
            try:
                with ExitStack() as locks:
                    locks.enter_context(process_lock(config["state_dir"]))
                    engine = Engine(config)
                    engine.recover()
                    while True:
                        try:
                            task(engine)
                            break
                        except PastSaveError:
                            replacement = select_workspace(engine.c, self.path.parent, fresh=True)
                            locks.enter_context(process_lock(replacement["state_dir"]))
                            engine.close()
                            engine = Engine(replacement)
                            engine.recover()
                            self.events.put({"workspace": replacement})
                            self.events.put("이전 시점의 세이브 감지 · 기존 기록을 보존하고 새 기준을 자동으로 만듭니다.")
            except Exception as exc:
                self.events.put(f"오류: {exc}")
            finally:
                if engine:
                    engine.close()
                self.events.put("작업 종료")
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def scan(self):
        def task(e):
            count = e.ingest(read_source(e.c))
            self.events.put(f"선수 목록 읽기 완료 · 새 이적 작업 {count}개")
            for message in detection_messages(json.loads(e.meta("detection_summary"))):
                self.events.put(message)
        self.background(task)

    def enqueue(self):
        def task(e):
            e.ingest(read_source(e.c))
            self.events.put(f"현재 범위에서 {e.enqueue_current()}개 작업 추가")
        self.background(task)

    def start(self):
        current = {key: self.vars[key].get() for key in ("source", "portraits_dir", "kits_dir", "pack_dir", "graphics_root", "codex")}
        if not self.active() and not self.path_scanning and current != self.last_discovery_inputs:
            self.auto_paths()
        if self.path_scanning:
            self.start_after_discovery = True
            self.status.set("경로 자동 확인이 끝나면 감시를 시작합니다.")
            return
        def task(e):
            converted = e.prepare_watch()
            if converted:
                self.events.put(f"기존 결과 {converted}개를 선수 ID 파일명으로 갱신했습니다. 재합성하지 않습니다.")
            self.events.put("감시·합성 실행 중 · Codex 사용량이 발생할 수 있습니다.")
            self.events.put("감시 파일: " + e.c["source"])
            self.events.put(f'생성 간격: 세이브 업데이트 {e.c["save_update_interval"]}회마다 · 최초 기준 읽기는 제외')
            last_wait_message = None
            while not self.stop.is_set():
                try:
                    result = e.watch_step()
                    refresh_status = e.meta("live_refresh_status")
                    if refresh_status and refresh_status != getattr(e, "_shown_live_status", None):
                        self.events.put(refresh_status)
                        e._shown_live_status = refresh_status
                    if result.get("changed"):
                        self.events.put(f'세이브 변경 점검 · 신규 작업 {result["added"]}개')
                        for message in detection_messages(result["detection"]):
                            self.events.put(message)
                    if result["processed"]:
                        self.events.put("합성 작업 1개 처리 · 대기열에서 상태를 확인하세요.")
                        last_wait_message = None
                    elif result.get("waiting"):
                        if result.get("save_updates_pending"):
                            message = f'세이브 업데이트 {result["save_updates_pending"]}/{result["save_update_interval"]}회 · 생성 대기 {result["waiting"]}개'
                        else:
                            message = f'자동 감시 중 · 대기 {result["waiting"]}개 · 생성 대기/호출 상한/재생성 간격 후 자동 진행'
                        if message != last_wait_message:
                            self.events.put(message)
                            last_wait_message = message
                    else:
                        last_wait_message = None
                except PastSaveError:
                    raise
                except Exception as exc:
                    self.events.put(f"점검 보류: {exc}")
                self.stop.wait(WATCH_POLL_SECONDS)
        self.background(task)

    def pause(self):
        self.start_after_discovery = False
        self.stop.set()
        self.status.set("정지 요청 · 진행 중인 Codex 작업이 끝나면 멈춥니다.")

    def export_detection(self):
        source = Path(self.config["state_dir"]) / "latest_detection.json"
        if not source.is_file():
            messagebox.showinfo("감지 진단", "선수·이적을 읽거나 감시 중 세이브 점검이 끝나면 진단 정보가 만들어집니다.")
            return
        path = filedialog.asksaveasfilename(title="감지 진단 저장", defaultextension=".json",
                                          initialfile="fm_detection.json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                write_atomic(path, source.read_bytes())
                self.events.put("감지 진단 저장 완료: " + path)
            except Exception as exc:
                messagebox.showerror("감지 진단", str(exc))

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def select(self, event=None):
        jid = self.selected()
        if jid:
            values = self.tree.item(str(jid), "values")
            self.detail.set(values[-1])
        self.update_job_actions()

    def update_job_actions(self):
        job = self.job_records.get(self.selected())
        editable = job and not job["editing"] and job["status"] in ("pending", "blocked", "failed", "interrupted")
        available = {"개별 지시": editable, "유니폼 변경": editable and not self.active(),
                     "결과 보기": job and bool(job["artifact"]),
                     "다시 시도": job and not job["editing"] and job["status"] in ("failed", "blocked", "interrupted", "apply_failed")}
        for label, button in self.queue_buttons.items():
            button.configure(state="normal" if available[label] else "disabled")

    def open_job(self):
        job = self.job_records.get(self.selected())
        if job:
            self.edit_player() if job["status"] in ("pending", "blocked", "failed", "interrupted") else self.preview()

    def apply(self):
        jid = self.selected()
        if jid:
            self.background(lambda e: (e.apply(jid), self.events.put("선택 결과 적용 완료")))

    def retry(self):
        jid = self.selected()
        if jid:
            engine = Engine(self.config)
            try:
                engine.retry(jid)
                self.events.put("재시도 요청을 반영했습니다. 자동 생성 중이면 이어 처리합니다. 저장 실패는 추가 AI 호출 없이 복구합니다.")
            finally:
                engine.close()

    def choose_kit(self):
        if self.active():
            messagebox.showinfo("유니폼 선택", "현재 작업 후 정지한 다음 선택하세요.")
            return
        jid = self.selected()
        if not jid:
            messagebox.showinfo("유니폼 선택", "대기열에서 선수를 선택하세요.")
            return
        if not self.save():
            return
        e = Engine(self.config)
        try:
            job = e.db.execute("SELECT data,status FROM jobs WHERE id=?", (jid,)).fetchone()
            if not job:
                return
            player = json.loads(job["data"])
            if job["status"] not in ("pending", "blocked", "failed", "interrupted"):
                messagebox.showinfo("유니폼 선택", "대기·보류·실패·중단 작업에서 선택하세요. 완성된 이미지는 이 선택으로 바뀌지 않습니다.")
                return
        finally:
            e.close()
        config = dict(self.config)
        variant = player_kit_variant(config, player)
        key = f'{player["club_id"]}:{variant}'
        chosen = config.get("kit_overrides", {}).get(key)
        editor = tk.Toplevel(self.window)
        editor.title(f'유니폼 변경 · {player["club_name"]} · {variant}')
        editor.geometry("960x620")
        editor.minsize(800, 540)
        editor.transient(self.window)
        editor.grab_set()
        frame = ttk.Frame(editor, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f'구단 {player["club_id"]} · {variant} — 같은 구단·유형의 이후 작업에도 적용합니다.').pack(anchor="w")
        status = tk.StringVar(value="설정된 유니폼 폴더에서 후보를 검색하고 있습니다…")
        ttk.Label(frame, textvariable=status, wraplength=900).pack(fill="x", pady=8)
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        listing = ttk.Frame(body)
        listing.pack(side="left", fill="both", expand=True, padx=(0, 12))
        candidates = tk.Listbox(listing, exportselection=False, width=45, font="TkTextFont")
        vertical = ttk.Scrollbar(listing, orient="vertical", command=candidates.yview)
        horizontal = ttk.Scrollbar(listing, orient="horizontal", command=candidates.xview)
        candidates.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="right", fill="y")
        horizontal.pack(side="bottom", fill="x")
        candidates.pack(fill="both", expand=True)
        preview = ttk.Label(body, text="이미지를 선택하면 미리보기가 표시됩니다.", anchor="center", width=38)
        preview.pack(side="right", fill="both")
        selected_path = tk.StringVar()
        ttk.Label(frame, textvariable=selected_path, wraplength=900).pack(fill="x", pady=10)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        paths = []
        selection = {"path": None}

        def show(event=None):
            selection["path"] = None
            use.configure(state="disabled")
            indexes = candidates.curselection()
            if not indexes:
                return
            path = paths[indexes[0]]
            selected_path.set(str(path))
            try:
                with Image.open(BytesIO(reference_png(path))) as image:
                    image.thumbnail((350, 350), Image.Resampling.LANCZOS)
                    editor.photo = ImageTk.PhotoImage(image, master=editor)
                preview.configure(image=editor.photo, text="")
                selection["path"] = path
                use.configure(state="normal")
            except Exception as exc:
                preview.configure(image="", text="미리보기를 열 수 없습니다.")
                status.set(str(exc))

        def add(path):
            path = Path(path).resolve()
            if path not in paths:
                paths.append(path)
                candidates.insert("end", str(path))
            index = paths.index(path)
            candidates.selection_clear(0, "end")
            candidates.selection_set(index)
            candidates.see(index)
            show()

        def browse():
            path = filedialog.askopenfilename(parent=editor, title="사용할 유니폼 이미지", filetypes=[("이미지", "*.png *.jpg *.jpeg *.webp *.bmp"), ("모든 파일", "*.*")])
            if path:
                add(path)

        def commit(automatic=False):
            path = selection["path"]
            if not automatic and path is None:
                return
            try:
                if not automatic:
                    reference_png(path)
            except Exception as exc:
                messagebox.showerror("유니폼 선택", str(exc), parent=editor)
                return
            previous = self.config.get("kit_overrides", {})
            updated = dict(previous)
            if automatic:
                updated.pop(key, None)
            else:
                updated[key] = str(path)
            self.config["kit_overrides"] = updated
            if not self.save():
                self.config["kit_overrides"] = previous
                return
            editor.destroy()
            self.background(lambda engine: (engine.retry(jid), self.events.put(f"구단 {key} 유니폼 선택 반영. 감시·생성 시작으로 실행하세요.")))

        use = ttk.Button(buttons, text="이 이미지 사용", command=commit, state="disabled")
        use.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="파일 직접 선택", command=browse).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="자동 검색으로 되돌리기", command=lambda: commit(True)).pack(side="left")
        ttk.Button(buttons, text="취소", command=editor.destroy).pack(side="right")
        candidates.bind("<<ListboxSelect>>", show)
        results = queue.Queue()

        def scan():
            try:
                catalog = AssetCatalog(config["kits_dir"], exclude=source_exclusions(config, config["kits_dir"]),
                                       allow_managed=Path(config["kits_dir"]).resolve() == Path(config["pack_dir"]).resolve())
                try:
                    found = catalog.kit_candidates(player["club_id"], variant)
                    note = "지정하지 않으면 매 작업에서 무작위 후보를 사용합니다."
                except AssetError as exc:
                    found, note = list(exc.candidates), str(exc)
                results.put((found, note))
            except Exception as exc:
                results.put(([], str(exc)))

        def poll():
            if not editor.winfo_exists():
                return
            try:
                found, note = results.get_nowait()
            except queue.Empty:
                editor.after(100, poll)
                return
            current = selection["path"]
            for path in found:
                add(path)
            if current:
                add(current)
            elif paths:
                candidates.selection_clear(0, "end")
                candidates.selection_set(0)
                show()
            status.set(f"{len(paths)}개 이미지. {note} 직접 파일을 지정할 수도 있습니다.")

        if chosen:
            add(chosen)
        threading.Thread(target=scan, daemon=True).start()
        editor.after(100, poll)

    def edit_chosen_job(self):
        jid = self.job_choices.get(self.personal_job.get())
        if jid:
            self.edit_player(jid)
        else:
            messagebox.showinfo("개별 지시", "편집할 대기 작업을 먼저 선택하세요.")

    def edit_player(self, job_id=None):
        jid = job_id or self.selected()
        if not jid:
            messagebox.showinfo("개별 지시", "대기열에서 편집할 작업을 선택하세요.")
            return
        e = Engine(self.config)
        try:
            player, options = e.begin_job_edit(jid)
        except Exception as exc:
            e.close()
            messagebox.showinfo("개별 지시", str(exc))
            return
        editor = tk.Toplevel(self.window)
        editor.title(f'개별 지시 · {player["name"]} · 작업 {jid}')
        editor.geometry("720x500")
        editor.transient(self.window)
        editor.grab_set()
        frame = ttk.Frame(editor, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f'{player["name"]} · {player["club_name"]}', style="Section.TLabel").pack(anchor="w", pady=(0, 14))
        ttk.Label(frame, text="하단 영문 이름 · 비워두면 자동").pack(anchor="w")
        name = tk.StringVar(value=options.get("display_name", ""))
        ttk.Entry(frame, textvariable=name).pack(fill="x", pady=(6, 14))
        ttk.Label(frame, text="이 작업에만 적용할 지시").pack(anchor="w")
        directions = tk.Text(frame, height=7, wrap="word", font="TkTextFont")
        directions.pack(fill="both", expand=True, pady=6)
        directions.insert("1.0", options.get("additional_instructions", ""))
        ttk.Label(frame, text="편집 중에는 이 작업의 합성을 잠시 보류합니다. 저장하거나 닫으면 처리를 재개합니다.\n개별 지시는 공통 지시보다 우선하며 다음 이적 작업에 자동으로 복사하지 않습니다.", style="Muted.TLabel", wraplength=670).pack(anchor="w", pady=10)
        released = False
        def cancel():
            nonlocal released
            if not released:
                e.finish_job_edit(jid)
                e.close()
                released = True
            if editor.winfo_exists():
                editor.destroy()
        def commit():
            nonlocal released
            try:
                if self.config["state_dir"] != e.c["state_dir"]:
                    raise ValueError("감시 세이브가 바뀌었습니다. 최신 작업을 다시 선택하세요.")
                e.finish_job_edit(jid, {"display_name": name.get().strip(), "additional_instructions": directions.get("1.0", "end").strip()})
                e.close()
                released = True
                self.events.put(f'{player["name"]}: 작업 {jid}의 개별 지시 저장 완료')
                editor.destroy()
            except Exception as exc:
                messagebox.showerror("개별 지시", str(exc), parent=editor)
        editor.protocol("WM_DELETE_WINDOW", cancel)
        editor.bind("<Escape>", lambda event: cancel())
        editor.bind("<Destroy>", lambda event: cancel() if event.widget == editor and not released else None)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="이 작업에 저장", command=commit).pack(side="left")
        ttk.Button(buttons, text="취소", command=cancel).pack(side="right")

    def export(self):
        if self.active():
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="players.csv")
        if path:
            self.background(lambda e: (e.export_players(path), self.events.put("선수·구단 ID 목록 저장 완료")))

    def restore(self):
        if self.active():
            return
        backup = filedialog.askopenfilename(initialdir=str(Path(self.config["pack_dir"]) / "backups"), filetypes=[("XML", "*.xml")])
        if backup:
            self.background(lambda e: (e.restore(backup), self.events.put("페이스팩 매핑 복구 완료 · 게임에서 다시 불러오세요.")))

    def preview(self):
        jid = self.selected()
        if not jid:
            return
        engine = Engine(self.config)
        try:
            job = engine.db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not job or not job["artifact"]:
                return
            win = tk.Toplevel(self.window)
            win.title(f"합성 결과 · 작업 {jid}")
            image = tk.PhotoImage(file=job["artifact"])
            image = image.subsample(max(1, (image.width() + 639) // 640))
            label = ttk.Label(win, image=image)
            label.image = image
            label.pack(padx=15, pady=15)
            ttk.Label(win, text="완료 결과는 자동 저장됩니다. 얼굴·유니폼을 확인하고 필요하면 재생성하세요.").pack(pady=(0, 15))
        except Exception as exc:
            messagebox.showerror("미리보기", str(exc))
        finally:
            engine.close()

    def drain(self):
        while not self.events.empty():
            text = self.events.get()
            if isinstance(text, dict) and "path_scan" in text:
                self.accept_paths(text)
                continue
            if isinstance(text, dict) and "workspace" in text:
                self.config.update(state_dir=text["workspace"]["state_dir"], workspaces=text["workspace"]["workspaces"])
                write_atomic(self.path, json.dumps(self.config, ensure_ascii=False, indent=2).encode("utf-8"))
                self.catalog_key = None
                continue
            self.status.set(text)
            self.log.configure(state="normal")
            self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        database = Path(self.config["state_dir"]) / "queue.sqlite"
        if database.exists():
            engine = None
            try:
                engine = Engine(self.config)
                if not self.active():
                    engine.pump_live_refresh()
                self.live_status.set(engine.meta("live_refresh_status") or "게임 갱신 연결 확인 대기" if self.config.get("live_refresh_enabled") else "실시간 게임 갱신 꺼짐")
                self.update_dashboard(engine)
                selected = self.tree.selection()
                self.tree.delete(*self.tree.get_children())
                labels = {"pending": "대기", "running": "합성 중", "generated": "자동 저장 대기", "apply_failed": "저장 실패", "applied": "완료", "blocked": "보류", "failed": "실패", "superseded": "이전 상태", "interrupted": "중단됨"}
                choices = {}
                self.job_records = {}
                for job in engine.jobs():
                    self.job_records[job["id"]] = job
                    row = json.loads(job["data"])
                    movement = row["club_name"]
                    if row.get("from_club_id") and row["from_club_id"] != row["club_id"]:
                        source = self.scope_panel.catalog.get(row["from_club_id"], {})
                        destination = self.scope_panel.catalog.get(row["club_id"], {})
                        movement = (source.get("short_name") or row.get("from_club_name") or row["from_club_id"]) + " → " + (destination.get("short_name") or row["club_name"])
                    if job["status"] in ("pending", "blocked", "failed", "interrupted"):
                        choices[f'{row["name"]} · {row["club_name"]} · 작업 {job["id"]}'] = job["id"]
                    status = "지시 편집 중" if job["editing"] else labels.get(job["status"], job["status"])
                    note = "생성 완료" if job["status"] == "applied" else (
                        ("개별 지시 · " if job["has_custom"] else "") +
                        ("골키퍼 · " if row.get("is_goalkeeper") is True else "") + job["note"])
                    self.tree.insert("", "end", iid=str(job["id"]), values=(job["id"], row["name"], movement, status, note))
                self.job_choices = choices
                self.personal_selector.configure(values=list(choices))
                self.personal_edit_button.configure(state="normal" if choices else "disabled")
                if self.personal_job.get() not in choices:
                    self.personal_job.set(next(iter(choices), "편집할 대기 작업이 없습니다"))
                if selected and self.tree.exists(selected[0]):
                    self.tree.selection_set(selected)
                self.update_job_actions()
            except Exception as exc:
                self.status.set(str(exc))
            finally:
                if engine:
                    engine.close()
        else:
            self.job_choices = {}
            self.job_records = {}
            self.update_job_actions()
            self.personal_selector.configure(values=[])
            self.personal_job.set("편집할 대기 작업이 없습니다")
            self.personal_edit_button.configure(state="disabled")
            if self.dashboard_key is not None:
                self.clear_preview()
            for variable in self.metric_vars.values():
                variable.set("0")
            if self.catalog_key is not None:
                self.catalog_key = None
                self.scope_panel.set_catalog([], [], {})
        self.window.after(1500, self.drain)

    def close(self):
        self.discovery_stop.set()
        if self.active():
            self.pause()
            self.status.set("종료 대기 · 현재 작업이 끝나면 창이 닫힙니다.")
            self.window.after(500, self.finish_close)
        else:
            self.window.destroy()

    def finish_close(self):
        if self.active():
            self.window.after(500, self.finish_close)
        else:
            self.window.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--scan", action="store_true", help="Read source and update queue without calling Codex")
    args = parser.parse_args()
    if args.scan:
        c = load_config(args.config)
        with process_lock(c["state_dir"]):
            e = Engine(c)
            try:
                print(json.dumps({"new_jobs": e.ingest(read_source(c)), "jobs": len(e.jobs())}))
            finally:
                e.close()
    else:
        window = tk.Tk()
        App(window, args.config)
        window.mainloop()


if __name__ == "__main__":
    main()
