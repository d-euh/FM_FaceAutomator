"""Korean native desktop UI. No web server or Face Studio dependency."""
from __future__ import annotations

import argparse
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

from engine import DEFAULTS, Engine, detection_messages, load_config, process_lock, read_source, write_atomic
from assets import AssetCatalog, AssetError, reference_png, source_exclusions
from discovery import discover_defaults
import scope_rules
from scope_ui import ScopePanel
from theme import BLACK, PURPLE, apply_theme


ROOT = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


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
        self.catalog_key = None
        self.status = tk.StringVar(value="경로와 범위를 확인하고 감시를 시작하세요.")
        self.scope_summary = tk.StringVar(value="내가 맡은 구단만 · 방출·영입 모두")
        window.title("FM Face Automator")
        window.geometry("1220x870")
        window.minsize(1060, 750)
        family = "Malgun Gothic" if os.name == "nt" else "Noto Sans CJK KR"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family=family, size=10)
        apply_theme(window, family)
        header = ttk.Frame(window, padding=(24, 20, 24, 16))
        header.pack(fill="x")
        title = ttk.Frame(header)
        title.pack(side="left")
        ttk.Label(title, text="FM Face Automator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="세이브가 바뀌면, 새로운 팀의 페이스온으로", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.tabs = ttk.Notebook(window)
        self.tabs.pack(fill="both", expand=True, padx=20)
        self.home_tab, home = self.page()
        self.scope_tab, scope = self.page(scroll=True)
        self.jobs_tab, jobs = self.page()
        self.settings_tab, settings = self.page(scroll=True)
        self.prompts_tab, prompts = self.page(scroll=True)
        for host, label in ((self.home_tab, "홈"), (self.scope_tab, "생성 범위"), (self.jobs_tab, "작업 대기열"), (self.settings_tab, "폴더 · 연결"), (self.prompts_tab, "추가 지시 · 건조폼")):
            self.tabs.add(host, text=label)
        ttk.Button(header, text="홈", command=lambda: self.tabs.select(self.home_tab)).pack(side="right")
        ttk.Button(header, text="생성 범위 설정", command=lambda: self.tabs.select(self.scope_tab)).pack(side="right", padx=8)
        ttk.Label(header, text="v0.5.1", style="Muted.TLabel").pack(side="right", padx=12)
        self.build_home(home)
        self.scope_panel = ScopePanel(scope, self.vars, self.save, self.scan,
                                      lambda: self.tabs.select(self.home_tab), self.update_scope_summary)
        settings.columnconfigure(1, weight=1)
        self.fields(settings)
        self.prompt_fields(prompts)
        toolbar = ttk.Frame(jobs)
        toolbar.pack(fill="x", pady=(0, 12))
        for title, callback in [("선수·이적 읽기", self.scan), ("현재 범위도 생성 대기", self.enqueue), ("감시·생성 시작", self.start), ("현재 작업 후 정지", self.pause)]:
            ttk.Button(toolbar, text=title, command=callback, style="Primary.TButton" if callback == self.start else "TButton").pack(side="left", padx=(0, 8))
        ttk.Label(jobs, textvariable=self.status, wraplength=1100, style="Muted.TLabel").pack(fill="x", pady=(0, 12))
        self.tree = ttk.Treeview(jobs, columns=("id", "player", "club", "status", "note"), show="headings", height=13)
        for key, label, width in [("id", "작업", 45), ("player", "선수", 145), ("club", "이동 · 새 소속팀", 210), ("status", "상태", 100), ("note", "설명", 400)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=key == "note")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        actions = ttk.Frame(jobs)
        actions.pack(fill="x", pady=12)
        for title, callback in [("이미지 미리보기", self.preview), ("저장 재시도", self.apply), ("합성 재시도", self.retry), ("선수 ID 목록 저장", self.export), ("적용 백업 복구", self.restore), ("선수별 이름·지시", self.edit_player)]:
            ttk.Button(actions, text=title, command=callback).pack(side="left", padx=(0, 6))
        optional = ttk.Frame(jobs)
        optional.pack(fill="x", pady=(0, 8))
        ttk.Button(optional, text="유니폼 이미지 선택", command=self.choose_kit).pack(side="left", padx=(0, 6))
        ttk.Button(optional, text="감지 진단 저장", command=self.export_detection).pack(side="left")
        self.detail = tk.StringVar(value="이전·새 구단을 비교해 선택한 영입·방출 방향의 선수만 생성합니다.")
        ttk.Label(jobs, textvariable=self.detail, wraplength=1100, style="Muted.TLabel").pack(fill="x", pady=(0, 6))
        log_host = ttk.Frame(window, padding=(20, 10, 20, 16))
        log_host.pack(side="bottom", fill="x", before=self.tabs)
        self.log = tk.Text(log_host, height=4, font=(family, 9), state="disabled", background=BLACK, foreground=PURPLE, relief="flat", padx=10, pady=8)
        self.log.pack(fill="x")
        self.load()
        self.window.after(100, self.auto_paths)
        self.window.after(500, self.drain)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def page(self, scroll=False):
        host = ttk.Frame(self.tabs)
        if not scroll:
            content = ttk.Frame(host, padding=20)
            content.pack(fill="both", expand=True)
            return host, content
        canvas = tk.Canvas(host, highlightthickness=0, background=BLACK)
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
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=0)
        parent.rowconfigure(0, weight=1)
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        hero = ttk.Frame(left, style="Card.TFrame", padding=20)
        hero.pack(fill="both", expand=True)
        ttk.Label(hero, text="저장 후 자동으로 완성되는 페이스온", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(hero, text="이적 감지 → 선택한 범위 확인 → Codex 합성 → 이미지·매핑 저장", style="CardMuted.TLabel", wraplength=560).pack(anchor="w", pady=(8, 16))
        ttk.Label(hero, text="선택한 생성 범위", style="CardMuted.TLabel").pack(anchor="w")
        ttk.Label(hero, textvariable=self.scope_summary, style="CardTitle.TLabel", wraplength=540).pack(anchor="w", pady=(6, 14))
        ttk.Button(hero, text="생성 범위 설정 →", command=lambda: self.tabs.select(self.scope_tab)).pack(anchor="w", pady=(0, 16))
        ttk.Label(hero, textvariable=self.status, style="CardMuted.TLabel", wraplength=540).pack(anchor="w", pady=(0, 12))
        controls = ttk.Frame(hero, style="Card.TFrame")
        controls.pack(fill="x")
        ttk.Button(controls, text="감시·생성 시작", style="Primary.TButton", command=self.start).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="현재 작업 후 정지", command=self.pause).pack(side="left")
        stats = ttk.Frame(left)
        stats.pack(side="bottom", fill="x", pady=(16, 0), before=hero)
        self.metric_vars = {}
        for key, label in (("pending", "대기 중"), ("running", "생성 중"), ("applied", "저장 완료")):
            card = ttk.Frame(stats, style="Card.TFrame", padding=16)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10) if key != "applied" else 0)
            ttk.Label(card, text=label, style="CardMuted.TLabel").pack(anchor="w")
            self.metric_vars[key] = tk.StringVar(value="0")
            ttk.Label(card, textvariable=self.metric_vars[key], style="Metric.TLabel").pack(anchor="w", pady=(4, 0))
        recent = ttk.Frame(parent, style="Card.TFrame", padding=20)
        recent.grid(row=0, column=1, sticky="nsew")
        ttk.Label(recent, text="최근 생성된 페이스온", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 14))
        self.recent_canvas = tk.Canvas(recent, width=350, height=350, background=BLACK, highlightthickness=0)
        self.recent_canvas.pack()
        self.recent_canvas.create_text(175, 175, text="첫 페이스온을 기다리고 있습니다\n생성이 끝나면 여기에 표시됩니다", fill=PURPLE, font="TkDefaultFont", justify="center")
        self.recent_name = tk.StringVar(value="350 × 350 · 영문 이름 · ID 파일명")
        ttk.Label(recent, textvariable=self.recent_name, style="CardText.TLabel", wraplength=350).pack(anchor="w", pady=(14, 0))

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
        latest = json.loads(engine.meta("latest_result") or "null")
        if latest is None:
            candidates = [job for job in engine.jobs() if job["artifact"] and Path(job["artifact"]).is_file()]
            if candidates:
                job = max(candidates, key=lambda j: Path(j["artifact"]).stat().st_mtime_ns)
                player = json.loads(job["data"])
                latest = {"id": job["id"], "artifact": job["artifact"], "name": player["name"], "club_name": player["club_name"]}
        key = (self.config["state_dir"], latest["artifact"]) if latest else None
        if latest is None and self.dashboard_key is not None:
            self.clear_preview()
        if latest and key != self.dashboard_key:
            self.dashboard_key = key
            try:
                with Image.open(latest["artifact"]) as image:
                    image = image.convert("RGBA")
                    image.thumbnail((350, 350), Image.Resampling.LANCZOS)
                    self.recent_photo = ImageTk.PhotoImage(image, master=self.window)
                self.recent_canvas.delete("all")
                self.recent_canvas.create_image(175, 175, image=self.recent_photo)
                self.recent_name.set(f'{latest["name"]}\n{latest["club_name"]} · 작업 {latest["id"]}')
            except Exception:
                self.recent_name.set("최근 결과 이미지 파일을 열 수 없습니다.")

    def clear_preview(self):
        self.dashboard_key = None
        self.recent_canvas.delete("all")
        self.recent_canvas.create_text(175, 175, text="아직 생성된 페이스온이 없습니다", fill=PURPLE, font="TkDefaultFont")
        self.recent_name.set("350 × 350 · 영문 이름 · ID 파일명")

    def fields(self, parent):
        ttk.Label(parent, text="폴더 · Codex 연결", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))
        rows = [("source", "FM27 세이브 / JSON", "file"), ("state_dir", "작업 폴더 · 세이브별", "dir"),
                ("portraits_dir", "원본 얼굴 폴더", "dir"), ("kits_dir", "유니폼 참조 폴더", "dir"),
                ("pack_dir", "페이스팩 저장 폴더", "dir"), ("codex", "Codex 실행 파일", "exe"),
                ("graphics_root", "FM 자료 상위 폴더 · 선택", "dir")]
        for index, (key, label, chooser) in enumerate(rows, 1):
            ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", padx=(0, 18), pady=10)
            self.vars[key] = tk.StringVar()
            ttk.Entry(parent, textvariable=self.vars[key]).grid(row=index, column=1, sticky="ew", pady=10)
            ttk.Button(parent, text="선택", command=lambda k=key, c=chooser: self.choose(k, c)).grid(row=index, column=2, padx=(10, 0))
        ttk.Label(parent, text="합성에 사용할 유니폼").grid(row=8, column=0, sticky="w", pady=12)
        self.vars["kit_variant"] = tk.StringVar()
        ttk.Combobox(parent, textvariable=self.vars["kit_variant"], values=("home", "away", "third"), state="readonly", width=14).grid(row=8, column=1, sticky="w")
        self.path_status = tk.StringVar(value="폴더와 Codex 경로를 자동 확인합니다. 다른 항목만 직접 바꾸세요.")
        ttk.Label(parent, textvariable=self.path_status, style="Muted.TLabel", wraplength=1050).grid(row=9, column=0, columnspan=3, sticky="w", pady=20)
        ttk.Label(parent, text="기존 파일이 있는 페이스팩에도 저장합니다. 같은 선수 ID의 이미지와 매핑은 백업 후 갱신합니다.", style="Muted.TLabel", wraplength=1050).grid(row=10, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Button(parent, text="설정 저장", style="Primary.TButton", command=self.save).grid(row=11, column=0, sticky="w")
        ttk.Button(parent, text="홈으로", command=lambda: self.tabs.select(self.home_tab)).grid(row=11, column=1, sticky="w")

    def prompt_fields(self, parent):
        ttk.Label(parent, text="전체 선수 공통 추가 지시", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="예: 비 오는 경기장에서 골을 넣고 활짝 웃는 모습. 앞머리는 뒤로 넘기고 한 손을 들어주세요.", wraplength=980).pack(anchor="w", pady=(8, 6))
        self.additional_text = tk.Text(parent, height=5, wrap="word", font="TkTextFont")
        self.additional_text.pack(fill="x")
        ttk.Label(parent, text="추가 지시가 있으면 머리카락·표정·자세 유지 문구를 넣지 않습니다. 얼굴 동일성은 기본 유지합니다.\n선수별 입력은 대기열에서 ‘선수별 이름·지시’를 선택하세요. 공통 지시와 충돌하면 선수별 지시를 우선합니다.", foreground=PURPLE, wraplength=980).pack(anchor="w", pady=10)
        ttk.Label(parent, text="기본 사진 스타일").pack(anchor="w")
        self.style_text = tk.Text(parent, height=3, wrap="word", font="TkTextFont")
        self.style_text.pack(fill="x", pady=(6, 12))
        ttk.Label(parent, text="건조폼 출력: 350×350 고정 · 둥근 모서리 · 하단 그라데이션과 선수 이름").pack(anchor="w", pady=(0, 8))
        for key, title in [("name_font_path", "이름 글꼴 (선택 사항: TTF/OTF/TTC)"), ("frame_template", "추가 폼 템플릿 (선택 사항: 투명 350×350 PNG)")]:
            ttk.Label(parent, text=title).pack(anchor="w")
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(4, 8))
            self.vars[key] = tk.StringVar()
            ttk.Entry(row, textvariable=self.vars[key]).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="선택", command=lambda k=key: self.choose(k, "asset")).pack(side="left", padx=(8, 0))
        ttk.Label(parent, text="이름은 AI가 그리지 않고 프로그램이 정확한 문자열로 넣습니다. 이름 수정은 다음 합성부터 반영됩니다.\nPNG와 config.xml을 모두 저장해야 완료 처리합니다. 저장 실패 시 이미지를 보관하고 추가 합성 없이 저장만 재시도합니다.", foreground=PURPLE, wraplength=980).pack(anchor="w", pady=10)
        ttk.Button(parent, text="설정 저장", command=self.save).pack(anchor="w")

    def choose(self, key, kind):
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
        snapshot = {key: self.vars[key].get() for key in ("source", "portraits_dir", "kits_dir", "pack_dir", "state_dir", "graphics_root", "codex")}
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
        try:
            write_atomic(self.path, json.dumps(self.config, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as exc:
            self.events.put(f"자동 경로 설정 저장 실패: {exc}")
        missing = [label for key, label in (("source", "세이브"), ("portraits_dir", "얼굴"), ("kits_dir", "유니폼"))
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
        for key, var in self.vars.items():
            value = c[key]
            var.set(",".join(value) if isinstance(value, list) else value)
        self.style_text.insert("1.0", c["style"])
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
                if key in ("club_ids", "player_ids", "exclude_player_ids", "regen_player_ids"):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                    if any(not v.isdigit() for v in value):
                        raise ValueError("ID는 숫자로 입력하세요.")
                elif key in ("daily_limit", "max_age", "poll_seconds"):
                    value = int(value)
                elif key in ("cooldown_hours", "settle_seconds"):
                    value = float(value)
                c[key] = value
            c["style"] = self.style_text.get("1.0", "end").strip()
            c["additional_instructions"] = self.additional_text.get("1.0", "end").strip()
            c["scope_rules"] = self.scope_panel.value()
            if not c["source"]:
                raise ValueError("세이브 파일을 선택하세요.")
            # Validate before replacing a working configuration.
            temp = self.path.with_name(".config-check.json")
            try:
                write_atomic(temp, json.dumps(c, ensure_ascii=False, indent=2).encode("utf-8"))
                checked = load_config(temp)
            finally:
                temp.unlink(missing_ok=True)
            write_atomic(self.path, json.dumps(c, ensure_ascii=False, indent=2).encode("utf-8"))
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
                with process_lock(config["state_dir"]):
                    engine = Engine(config)
                    engine.recover()
                    task(engine)
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
        current = {key: self.vars[key].get() for key in ("source", "portraits_dir", "kits_dir", "pack_dir", "state_dir", "graphics_root", "codex")}
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
            while not self.stop.is_set():
                try:
                    result = e.watch_step()
                    if result.get("changed"):
                        self.events.put(f'세이브 변경 점검 · 신규 작업 {result["added"]}개')
                        for message in detection_messages(result["detection"]):
                            self.events.put(message)
                    if result["processed"]:
                        self.events.put("합성 작업 1개 처리 · 대기열에서 상태를 확인하세요.")
                    elif result.get("waiting"):
                        self.events.put(f'자동 감시 중 · 대기 {result["waiting"]}개 · 변경 대기/호출 상한/재생성 간격 후 자동 진행')
                except Exception as exc:
                    self.events.put(f"점검 보류: {exc}")
                self.stop.wait(e.c["poll_seconds"])
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

    def apply(self):
        jid = self.selected()
        if jid:
            self.background(lambda e: (e.apply(jid), self.events.put("선택 결과 적용 완료")))

    def retry(self):
        jid = self.selected()
        if jid:
            self.background(lambda e: (e.retry(jid), self.events.put("재시도 대기열에 반영했습니다. 감시·생성 시작으로 실행하세요.")))

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
        key = f'{player["club_id"]}:{config["kit_variant"]}'
        chosen = config.get("kit_overrides", {}).get(key)
        editor = tk.Toplevel(self.window)
        editor.title(f'유니폼 선택 · {player["club_name"]} · {config["kit_variant"]}')
        editor.geometry("960x620")
        editor.minsize(800, 540)
        editor.transient(self.window)
        editor.grab_set()
        frame = ttk.Frame(editor, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f'구단 {player["club_id"]} · {config["kit_variant"]} — 같은 구단·유형의 이후 작업에도 적용합니다.').pack(anchor="w")
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
                    found = catalog.kit_candidates(player["club_id"], config["kit_variant"])
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

    def edit_player(self):
        if self.active():
            messagebox.showinfo("선수별 지시", "현재 작업 후 정지한 다음 수정하세요.")
            return
        jid = self.selected()
        if not jid:
            messagebox.showinfo("선수별 지시", "대기열에서 선수를 선택하세요.")
            return
        e = Engine(self.config)
        try:
            record = e.db.execute("SELECT data FROM jobs WHERE id=?", (jid,)).fetchone()
            if not record:
                return
            player = json.loads(record[0])
        finally:
            e.close()
        options = self.config.get("player_overrides", {}).get(player["id"], {})
        if options.get("identity") and options["identity"] != player["identity"]:
            options = {}
        editor = tk.Toplevel(self.window)
        editor.title(f'선수별 이름·추가 지시 · {player["name"]} ({player["id"]})')
        editor.geometry("680x430")
        editor.transient(self.window)
        editor.grab_set()
        frame = ttk.Frame(editor, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="하단 영문 선수 이름 (비워두면 세이브의 라틴 문자 이름 우선)").pack(anchor="w")
        name = tk.StringVar(value=options.get("display_name", ""))
        ttk.Entry(frame, textvariable=name).pack(fill="x", pady=(6, 14))
        ttk.Label(frame, text="이 선수의 추가 지시").pack(anchor="w")
        directions = tk.Text(frame, height=7, wrap="word", font="TkTextFont")
        directions.pack(fill="both", expand=True, pady=6)
        directions.insert("1.0", options.get("additional_instructions", ""))
        ttk.Label(frame, text="전체 공통 지시에 더해 적용합니다. 이름·지시는 이 선수의 다음 합성부터 반영됩니다.", wraplength=620).pack(anchor="w", pady=10)
        def commit():
            previous = dict(self.config.get("player_overrides", {}))
            updated = dict(previous)
            updated[player["id"]] = {"identity": player["identity"], "display_name": name.get().strip(), "additional_instructions": directions.get("1.0", "end").strip()}
            self.config["player_overrides"] = updated
            if self.save():
                self.events.put(f'{player["name"]}: 선수별 이름·추가 지시 저장 완료')
                editor.destroy()
            else:
                self.config["player_overrides"] = previous
        ttk.Button(frame, text="선수별 설정 저장", command=commit).pack(anchor="w")

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
                self.update_dashboard(engine)
                selected = self.tree.selection()
                self.tree.delete(*self.tree.get_children())
                labels = {"pending": "대기", "running": "합성 중", "generated": "자동 저장 대기", "apply_failed": "저장 실패", "applied": "완료", "blocked": "보류", "failed": "실패", "superseded": "이전 상태", "interrupted": "중단됨"}
                for job in engine.jobs():
                    row = json.loads(job["data"])
                    movement = row["club_name"]
                    if row.get("from_club_id") and row["from_club_id"] != row["club_id"]:
                        source = self.scope_panel.catalog.get(row["from_club_id"], {})
                        destination = self.scope_panel.catalog.get(row["club_id"], {})
                        movement = (source.get("short_name") or row.get("from_club_name") or row["from_club_id"]) + " → " + (destination.get("short_name") or row["club_name"])
                    self.tree.insert("", "end", iid=str(job["id"]), values=(job["id"], row["name"], movement, labels.get(job["status"], job["status"]), job["note"]))
                if selected and self.tree.exists(selected[0]):
                    self.tree.selection_set(selected)
            except Exception as exc:
                self.status.set(str(exc))
            finally:
                if engine:
                    engine.close()
        else:
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
