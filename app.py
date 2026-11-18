"""Korean native desktop UI. No web server or Face Studio dependency."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from engine import DEFAULTS, Engine, file_stamp, load_config, process_lock, read_source, write_atomic
from assets import AssetCatalog, AssetError, discover_roots, reference_png


ROOT = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent


class App:
    def __init__(self, window, config_path):
        self.window, self.path = window, Path(config_path).resolve()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.thread = None
        self.photo = None
        self.vars = {}
        window.title("FM Face Automator · 350×350 건조폼")
        window.geometry("1120x800")
        window.minsize(920, 680)
        family = "Malgun Gothic" if os.name == "nt" else "Noto Sans CJK KR"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family=family, size=10)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=(family, 10))
        style.configure("TButton", padding=(10, 7), font=(family, 10))
        style.configure("TLabel", font=(family, 10))
        style.configure("Title.TLabel", font=(family, 19, "bold"))
        header = ttk.Frame(window, padding=18)
        header.pack(fill="x")
        ttk.Label(header, text="FM Face Automator", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="저장된 이적 변화 → 선택 범위 → Codex 합성 → 전용 페이스팩", foreground="#536070").pack(anchor="w", pady=(5, 0))
        self.tabs = ttk.Notebook(window)
        self.tabs.pack(fill="both", expand=True, padx=18)
        settings_host = ttk.Frame(self.tabs)
        settings_canvas = tk.Canvas(settings_host, highlightthickness=0)
        settings_scroll = ttk.Scrollbar(settings_host, orient="vertical", command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_scroll.pack(side="right", fill="y")
        settings_canvas.pack(side="left", fill="both", expand=True)
        settings = ttk.Frame(settings_canvas, padding=14)
        settings_item = settings_canvas.create_window((0, 0), window=settings, anchor="nw")
        settings.bind("<Configure>", lambda event: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<Configure>", lambda event: settings_canvas.itemconfigure(settings_item, width=event.width))
        jobs = ttk.Frame(self.tabs, padding=12)
        prompts_host = ttk.Frame(self.tabs)
        prompts_canvas = tk.Canvas(prompts_host, highlightthickness=0)
        prompts_scroll = ttk.Scrollbar(prompts_host, orient="vertical", command=prompts_canvas.yview)
        prompts_canvas.configure(yscrollcommand=prompts_scroll.set)
        prompts_scroll.pack(side="right", fill="y")
        prompts_canvas.pack(side="left", fill="both", expand=True)
        prompts = ttk.Frame(prompts_canvas, padding=18)
        prompts_item = prompts_canvas.create_window((0, 0), window=prompts, anchor="nw")
        prompts.bind("<Configure>", lambda event: prompts_canvas.configure(scrollregion=prompts_canvas.bbox("all")))
        prompts_canvas.bind("<Configure>", lambda event: prompts_canvas.itemconfigure(prompts_item, width=event.width))
        self.tabs.add(settings_host, text="설정 · 생성 범위")
        self.tabs.add(jobs, text="작업 대기열 · 미리보기")
        self.tabs.add(prompts_host, text="추가 지시 · 건조폼")
        settings.columnconfigure(1, weight=1)
        self.fields(settings)
        self.prompt_fields(prompts)
        toolbar = ttk.Frame(jobs)
        toolbar.pack(fill="x", pady=(0, 10))
        for title, callback in [("선수·이적 읽기", self.scan), ("현재 범위도 생성 대기", self.enqueue), ("감시·생성 시작", self.start), ("현재 작업 후 정지", self.pause)]:
            ttk.Button(toolbar, text=title, command=callback).pack(side="left", padx=(0, 6))
        self.status = tk.StringVar(value="대기 중 · 감시·생성을 시작하기 전에는 Codex를 호출하지 않습니다.")
        ttk.Label(jobs, textvariable=self.status, wraplength=1000).pack(fill="x", pady=(0, 8))
        self.tree = ttk.Treeview(jobs, columns=("id", "player", "club", "status", "note"), show="headings", height=14)
        for key, label, width in [("id", "작업", 45), ("player", "선수", 155), ("club", "소속팀", 145), ("status", "상태", 105), ("note", "설명", 480)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=key == "note")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        actions = ttk.Frame(jobs)
        actions.pack(fill="x", pady=10)
        for title, callback in [("이미지 미리보기", self.preview), ("저장 재시도", self.apply), ("합성 재시도", self.retry), ("선수 ID 목록 저장", self.export), ("적용 백업 복구", self.restore), ("선수별 이름·지시", self.edit_player)]:
            ttk.Button(actions, text=title, command=callback).pack(side="left", padx=(0, 6))
        ttk.Button(jobs, text="유니폼 이미지 선택", command=self.choose_kit).pack(anchor="w", pady=(0, 8))
        self.detail = tk.StringVar(value="원본·키트는 기존 팩의 config.xml에서 ID로 찾습니다. 매핑이 없으면 ID 파일명을 사용합니다.")
        ttk.Label(jobs, textvariable=self.detail, wraplength=1000).pack(fill="x", pady=(0, 8))
        self.log = tk.Text(window, height=5, font=("Consolas", 10), state="disabled")
        self.log.pack(side="bottom", fill="x", padx=18, pady=12, before=self.tabs)
        self.load()
        self.window.after(500, self.drain)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def fields(self, parent):
        rows = [("source", "FM27 세이브 / JSON", "file"), ("state_dir", "작업 폴더 (세이브별)", "dir"),
                ("portraits_dir", "원본 얼굴 폴더", "dir"), ("kits_dir", "유니폼 참조 폴더", "dir"),
                ("pack_dir", "전용 페이스팩 폴더", "dir"), ("codex", "Codex 실행 파일", "exe"),
                ("club_ids", "추가 구단 ID (쉼표)", None), ("player_ids", "추가 선수 ID (쉼표)", None),
                ("exclude_player_ids", "제외 선수 ID (쉼표)", None),
                ("regen_player_ids", "생성선수 r- 매핑 ID", None)]
        for index, (key, label, chooser) in enumerate(rows):
            ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", padx=(0, 15), pady=4)
            self.vars[key] = tk.StringVar()
            ttk.Entry(parent, textvariable=self.vars[key]).grid(row=index, column=1, sticky="ew", pady=4)
            if chooser:
                ttk.Button(parent, text="선택", command=lambda k=key, c=chooser: self.choose(k, c)).grid(row=index, column=2, padx=(8, 0))
        flags = ttk.Frame(parent)
        flags.grid(row=10, column=0, columnspan=3, sticky="w", pady=10)
        for key, title in [("my_club_only", "내가 맡은 구단 포함"), ("all_players", "모든 구단 포함"), ("initial_generation", "처음 발견한 선수도 생성")]:
            self.vars[key] = tk.BooleanVar()
            ttk.Checkbutton(flags, text=title, variable=self.vars[key]).pack(side="left", padx=(0, 14))
        ttk.Label(flags, text="유니폼").pack(side="left", padx=(8, 6))
        self.vars["kit_variant"] = tk.StringVar()
        ttk.Combobox(flags, textvariable=self.vars["kit_variant"], values=("home", "away", "third"), state="readonly", width=8).pack(side="left")
        numbers = ttk.Frame(parent)
        numbers.grid(row=11, column=0, columnspan=3, sticky="w", pady=5)
        for key, title in [("daily_limit", "24시간 호출 상한"), ("max_age", "최대 나이(0=전체)"), ("cooldown_hours", "재생성 간격(시간)"), ("settle_seconds", "변경 대기(초)"), ("poll_seconds", "감시 간격(초)")]:
            group = ttk.Frame(numbers)
            group.pack(side="left", padx=(0, 14))
            ttk.Label(group, text=title).pack(anchor="w")
            self.vars[key] = tk.StringVar()
            ttk.Entry(group, textvariable=self.vars[key], width=12).pack(anchor="w", pady=4)
        ttk.Label(parent, text="완료 결과는 350×350 PNG · 하단 선수 이름 · FM config.xml 갱신까지 자동 저장합니다.\n구단·선수·내 구단 선택은 합집합이며 나이·제외 ID를 추가 적용합니다. 최초 읽기는 기본적으로 기준점만 만듭니다.\n.fm은 저장 시점 기준으로 감지합니다. 원본 얼굴과 유니폼은 사용자가 준비하며 자동 다운로드하지 않습니다.\n생성선수 판별은 추측하지 않습니다. r- 매핑이 필요한 선수 ID를 지정하세요. 실제 FM27 호환성 검증은 필요합니다.", foreground="#536070", wraplength=980).grid(row=12, column=0, columnspan=3, sticky="w", pady=12)
        ttk.Button(parent, text="설정 저장", command=self.save).grid(row=13, column=0, sticky="w")
        ttk.Button(parent, text="Codex 찾기", command=self.find_codex).grid(row=13, column=1, sticky="w")
        ttk.Button(parent, text="자료 폴더 자동 찾기", command=self.find_folders).grid(row=13, column=2, sticky="w")

    def prompt_fields(self, parent):
        ttk.Label(parent, text="전체 선수 공통 추가 지시", style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text="예: 비 오는 경기장에서 골을 넣고 활짝 웃는 모습. 앞머리는 뒤로 넘기고 한 손을 들어주세요.", wraplength=980).pack(anchor="w", pady=(8, 6))
        self.additional_text = tk.Text(parent, height=5, wrap="word", font="TkTextFont")
        self.additional_text.pack(fill="x")
        ttk.Label(parent, text="추가 지시가 있으면 머리카락·표정·자세 유지 문구를 넣지 않습니다. 얼굴 동일성은 기본 유지합니다.\n선수별 입력은 대기열에서 ‘선수별 이름·지시’를 선택하세요. 공통 지시와 충돌하면 선수별 지시를 우선합니다.", foreground="#536070", wraplength=980).pack(anchor="w", pady=10)
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
        ttk.Label(parent, text="이름은 AI가 그리지 않고 프로그램이 정확한 문자열로 넣습니다. 이름 수정은 다음 합성부터 반영됩니다.\nPNG와 config.xml을 모두 저장해야 완료 처리합니다. 저장 실패 시 이미지를 보관하고 추가 합성 없이 저장만 재시도합니다.", foreground="#536070", wraplength=980).pack(anchor="w", pady=10)
        ttk.Button(parent, text="설정 저장", command=self.save).pack(anchor="w")

    def choose(self, key, kind):
        value = filedialog.askdirectory() if kind == "dir" else filedialog.askopenfilename(filetypes=[("FM27 / JSON", "*.fm *.json"), ("모든 파일", "*")]) if kind == "file" else filedialog.askopenfilename()
        if value:
            self.vars[key].set(value)

    def find_codex(self):
        exe = shutil.which("codex")
        if exe and Path(exe).suffix.lower() not in (".cmd", ".bat"):
            self.vars["codex"].set(exe)
            return
        npm = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "@openai"
        matches = list(npm.rglob("codex.exe")) if npm.is_dir() else []
        if matches:
            self.vars["codex"].set(str(matches[0]))
        else:
            messagebox.showinfo("Codex", "Codex CLI 설치와 로그인을 먼저 완료하고 실제 codex.exe를 선택하세요.")

    def confirm_asset_folder(self, key, candidate, parent):
        label = "원본 얼굴" if key == "portraits_dir" else "유니폼 키트"
        answer = messagebox.askyesnocancel(
            f"{label} 폴더 확인",
            f"자동 검색으로 찾은 {label} 폴더입니다.\n\n{candidate}\n\n이 경로가 맞나요?\n\n예: 이 경로 사용\n아니요: 폴더 직접 지정\n취소: 기존 경로 유지",
            parent=parent,
        )
        if answer is None:
            return None
        folder = candidate
        if answer is False:
            folder = filedialog.askdirectory(
                parent=parent, title=f"{label} 폴더 직접 지정",
                initialdir=str(candidate), mustexist=True,
            )
        if not folder:
            return None
        if not Path(folder).is_dir():
            messagebox.showerror("폴더 확인", "해당 폴더가 없습니다. 폴더를 다시 지정하세요.", parent=parent)
            return None
        return str(Path(folder).resolve())

    def find_folders(self):
        if self.active():
            messagebox.showinfo("자료 폴더", "현재 작업 후 정지한 다음 자료 폴더를 변경하세요.")
            return
        dialog = tk.Toplevel(self.window)
        dialog.title("FM 자료 폴더 찾기 · 페이스팩 / 2D 키트")
        dialog.geometry("1000x490")
        dialog.transient(self.window)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="문서·OneDrive·세이브 인접 그래픽 폴더와 입력한 자료 폴더만 검색합니다.").pack(anchor="w")
        root_var = tk.StringVar(value=self.config.get("graphics_root", ""))
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=10)
        ttk.Label(row, text="추가 검색 위치").pack(side="left", padx=(0, 8))
        ttk.Entry(row, textvariable=root_var).pack(side="left", fill="x", expand=True)
        def choose_root():
            folder = filedialog.askdirectory(parent=dialog)
            if folder:
                root_var.set(folder)
        ttk.Button(row, text="폴더 선택", command=choose_root).pack(side="left", padx=6)
        listing = ttk.Treeview(frame, columns=("path", "faces", "kits", "basis"), show="headings", height=9)
        for key, text, width in [("path", "폴더", 480), ("faces", "얼굴 매핑", 75), ("kits", "키트 매핑", 75), ("basis", "검색 근거", 240)]:
            listing.heading(key, text=text)
            listing.column(key, width=width)
        listing.pack(fill="both", expand=True)
        status = tk.StringVar(value="검색을 시작하면 파일을 변경하지 않고 폴더와 config.xml을 확인합니다.")
        ttk.Label(frame, textvariable=status, wraplength=950).pack(anchor="w", pady=10)
        selected = tk.StringVar(value="후보가 하나면 경로를 확인합니다. ‘아니요’를 누르면 직접 지정으로 넘어갑니다. 후보가 여러 개면 먼저 행을 선택하세요.")
        ttk.Label(frame, textvariable=selected, wraplength=950).pack(anchor="w")
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(10, 0))
        messages = queue.Queue()
        stop = threading.Event()
        running = [False]
        def search():
            if running[0]:
                return
            config = dict(self.config)
            for key in ("source", "portraits_dir", "kits_dir", "pack_dir", "state_dir"):
                value = self.vars[key].get().strip()
                config[key] = str((self.path.parent / value).resolve()) if value else ""
            config["graphics_root"] = str((self.path.parent / root_var.get()).resolve()) if root_var.get().strip() else ""
            listing.delete(*listing.get_children())
            roots = discover_roots(config)
            if not roots:
                status.set("기본 위치에서 찾지 못했습니다. 추가 검색 위치를 선택하거나 설정 화면에 자료 폴더를 직접 입력하세요.")
                return
            running[0] = True
            search_button.configure(state="disabled")
            def scan():
                found, warnings, textures = {}, 0, 0
                for root in roots:
                    if stop.is_set():
                        return
                    messages.put(("status", f"읽는 중: {root}"))
                    try:
                        catalog = AssetCatalog(root, exclude=(config["state_dir"], config["pack_dir"]), stop=stop)
                        for candidate in catalog.suggestions():
                            found[candidate["path"]] = candidate
                        warnings += len(catalog.warnings) + len(catalog.missing_faces) + len(catalog.missing_kits)
                        textures += catalog.textures
                    except Exception as exc:
                        warnings += 1
                        messages.put(("status", str(exc)))
                messages.put(("done", (list(found.values()), warnings, textures)))
            threading.Thread(target=scan, daemon=True).start()
        def poll():
            if not dialog.winfo_exists():
                return
            while not messages.empty():
                kind, value = messages.get()
                if kind == "status":
                    status.set(value)
                else:
                    candidates, warnings, textures = value
                    for item in candidates:
                        listing.insert("", "end", values=(item["path"], item["faces"], item["kits"], item["basis"]))
                    status.set(f"검색 완료: 후보 {len(candidates)}곳 · 누락/읽기 경고 {warnings}건 · 3D 텍스처 {textures}건 제외. 매핑 수는 파일 연결 수이며 품질 검증은 합성 전에 합니다.")
                    running[0] = False
                    search_button.configure(state="normal")
                    dialog.after_idle(confirm_detected, candidates)
            dialog.after(120, poll)
        def use(key, candidate=None):
            if candidate is None:
                if not listing.selection():
                    return False
                candidate = listing.item(listing.selection()[0], "values")[0]
            folder = self.confirm_asset_folder(key, candidate, dialog)
            if folder is None:
                selected.set("폴더 지정을 취소했습니다. 기존 경로를 유지합니다.")
                return False
            self.vars[key].set(folder)
            self.config["graphics_root"] = str((self.path.parent / root_var.get()).resolve()) if root_var.get().strip() else ""
            selected.set(f'{"원본 얼굴" if key == "portraits_dir" else "유니폼 키트"} 폴더로 선택: {folder} · 닫은 뒤 설정을 저장하세요.')
            return True
        def confirm_detected(candidates):
            if not dialog.winfo_exists():
                return
            for key, kind in (("portraits_dir", "faces"), ("kits_dir", "kits")):
                matches = [item for item in candidates if item[kind] > 0]
                if len(matches) == 1 and not use(key, matches[0]["path"]):
                    break
        def close():
            stop.set()
            dialog.destroy()
        search_button = ttk.Button(controls, text="자동 검색", command=search)
        search_button.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="얼굴 경로 확인", command=lambda: use("portraits_dir")).pack(side="left", padx=4)
        ttk.Button(controls, text="키트 경로 확인", command=lambda: use("kits_dir")).pack(side="left", padx=4)
        ttk.Button(controls, text="닫기", command=close).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.after(120, poll)
        search()

    def load(self):
        if not self.path.exists():
            write_atomic(self.path, json.dumps(DEFAULTS, ensure_ascii=False, indent=2).encode("utf-8"))
        c = load_config(self.path)
        for key, var in self.vars.items():
            value = c[key]
            var.set(",".join(value) if isinstance(value, list) else value)
        self.style_text.insert("1.0", c["style"])
        self.additional_text.insert("1.0", c["additional_instructions"])
        self.config = c

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
        self.background(task)

    def enqueue(self):
        def task(e):
            e.ingest(read_source(e.c))
            self.events.put(f"현재 범위에서 {e.enqueue_current()}개 작업 추가")
        self.background(task)

    def start(self):
        def task(e):
            stamp = None
            self.events.put("감시·합성 실행 중 · Codex 사용량이 발생할 수 있습니다.")
            while not self.stop.is_set():
                try:
                    observed = file_stamp(e.c["source"])
                    # Avoid parsing while the game is likely still writing its save.
                    if time.time() - Path(e.c["source"]).stat().st_mtime < 3:
                        self.stop.wait(e.c["poll_seconds"])
                        continue
                    if observed != stamp:
                        added = e.ingest(read_source(e.c))
                        stamp = observed
                        self.events.put(f"세이브 변경 점검 · 신규 작업 {added}개")
                    if e.run_one():
                        self.events.put("합성 작업 1개 처리 · 대기열에서 상태를 확인하세요.")
                except Exception as exc:
                    self.events.put(f"점검 보류: {exc}")
                self.stop.wait(e.c["poll_seconds"])
        self.background(task)

    def pause(self):
        self.stop.set()
        self.status.set("정지 요청 · 진행 중인 Codex 작업이 끝나면 멈춥니다.")

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
                catalog = AssetCatalog(config["kits_dir"], exclude=(config["state_dir"], config["pack_dir"]))
                try:
                    found = [catalog.kit(player["club_id"], config["kit_variant"])]
                    note = "검색된 후보를 확인하고 선택하세요."
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
        ttk.Label(frame, text="하단에 표시할 선수 이름 (비워두면 세이브 이름)").pack(anchor="w")
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
            ttk.Label(win, text="얼굴 동일성·소속팀 유니폼·왜곡을 확인한 뒤 적용하세요.").pack(pady=(0, 15))
        except Exception as exc:
            messagebox.showerror("미리보기", str(exc))
        finally:
            engine.close()

    def drain(self):
        while not self.events.empty():
            text = self.events.get()
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
                selected = self.tree.selection()
                self.tree.delete(*self.tree.get_children())
                labels = {"pending": "대기", "running": "합성 중", "generated": "자동 저장 대기", "apply_failed": "저장 실패", "applied": "완료", "blocked": "보류", "failed": "실패", "superseded": "이전 상태", "interrupted": "중단됨"}
                for job in engine.jobs():
                    row = json.loads(job["data"])
                    self.tree.insert("", "end", iid=str(job["id"]), values=(job["id"], row["name"], row["club_name"], labels.get(job["status"], job["status"]), job["note"]))
                if selected and self.tree.exists(selected[0]):
                    self.tree.selection_set(selected)
            except Exception as exc:
                self.status.set(str(exc))
            finally:
                if engine:
                    engine.close()
        self.window.after(1500, self.drain)

    def close(self):
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
