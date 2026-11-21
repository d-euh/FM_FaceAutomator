"""Single-player portrait requests, independent of automatic transfer scopes."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from assets import reference_png
from scope_ui import ScopePanel
from theme import MUTED, PREVIEW_BACKGROUND


class ManualPanel:
    def __init__(self, parent, search, read, request):
        self.parent, self.search, self.request = parent, search, request
        self.workspace = None
        self.clubs, self.players = {}, {}
        self.player = None
        self.club_id = None
        self.timer = None
        self.reference_path = None
        self.reference_image = None
        self.reference_photo = None
        self.reference_name = tk.StringVar(value='선택하지 않으면 기존 사진을 자동으로 찾습니다.')
        self.query = tk.StringVar()
        self.club_query = tk.StringVar()
        self.player_name = tk.StringVar(value='선수를 선택하세요')
        self.club_name = tk.StringVar(value='기본값: 현 소속팀')
        self.note = tk.StringVar(value='선수 목록을 불러온 뒤 이름 또는 ID로 검색하세요.')
        parent.configure(padding=(16, 12))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        columns = ttk.Frame(parent)
        columns.grid(row=0,column=0,sticky='nsew')
        columns.columnconfigure(0,weight=1,uniform='manual')
        columns.columnconfigure(1,weight=1,uniform='manual')
        columns.rowconfigure(0,weight=1)
        left = ttk.Frame(columns)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,12))
        left.columnconfigure(0,weight=1)
        left.rowconfigure(0,weight=1,uniform='manual-left')
        left.rowconfigure(1,weight=1,uniform='manual-left')
        search_card = ttk.Frame(left,style='Rounded.Panel.Card.TFrame',padding=12)
        search_card.grid(row=0,column=0,sticky='nsew',pady=(0,8))
        search_card.columnconfigure(0,weight=1)
        search_card.rowconfigure(2,weight=1)
        right = ttk.Frame(columns,style='Rounded.Panel.Card.TFrame',padding=14)
        right.grid(row=0,column=1,sticky='nsew')
        right.columnconfigure(0,weight=1)
        right.rowconfigure(4,weight=1)
        right.rowconfigure(6,weight=1)
        ttk.Label(search_card,text='선수 검색 · 이름 또는 ID',style='CardTitle.TLabel').grid(row=0,column=0,sticky='w')
        form = ttk.Frame(search_card,style='Card.TFrame')
        form.grid(row=1,column=0,sticky='ew',pady=8)
        ttk.Entry(form,textvariable=self.query).pack(side='left',fill='x',expand=True,padx=(0,8))
        ttk.Button(form,text='목록 불러오기',style='Compact.TButton',command=read).pack(side='right')
        self.available = ScopePanel.compact_table(search_card,2,(('name','선수',150),('club','현 소속팀',135),('id','선수 ID',85)))
        self.available.bind('<<TreeviewSelect>>',self.select_player)
        ttk.Label(search_card,textvariable=self.player_name,style='CardText.TLabel',wraplength=410).grid(row=3,column=0,sticky='w',pady=(6,0))
        ttk.Label(search_card,textvariable=self.note,style='CardMuted.TLabel',wraplength=410).grid(row=4,column=0,sticky='w',pady=(4,0))
        photo_card = ttk.Frame(left,style='Rounded.Panel.Card.TFrame',padding=12)
        photo_card.grid(row=1,column=0,sticky='nsew')
        photo_card.columnconfigure(0,weight=1)
        photo_card.rowconfigure(1,weight=1)
        photo_bar = ttk.Frame(photo_card,style='Card.TFrame')
        photo_bar.grid(row=0,column=0,sticky='ew',pady=(0,6))
        ttk.Label(photo_bar,text='참조 사진 · 선택',style='CardTitle.TLabel').pack(side='left')
        self.remove_photo_button = ttk.Button(photo_bar,text='제거',style='Compact.TButton',command=self.clear_reference,state='disabled')
        self.remove_photo_button.pack(side='right')
        self.choose_photo_button = ttk.Button(photo_bar,text='사진 불러오기',style='Compact.TButton',command=self.choose_reference,state='disabled')
        self.choose_photo_button.pack(side='right',padx=6)
        self.reference_canvas = tk.Canvas(photo_card,width=200,height=100,background=PREVIEW_BACKGROUND,highlightthickness=0)
        self.reference_canvas.grid(row=1,column=0,sticky='nsew')
        self.reference_canvas.bind('<Configure>', self.draw_reference)
        self.reference_canvas.bind('<Button-1>', lambda event:self.choose_reference() if self.player else None)
        ttk.Label(photo_card,textvariable=self.reference_name,style='CardMuted.TLabel',wraplength=410).grid(row=2,column=0,sticky='w',pady=(6,0))
        ttk.Label(right,text='구단을 선택하세요',style='CardTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(right,text='유니폼 구단 · 아래에서 이름/ID 검색',style='CardText.TLabel').grid(row=1,column=0,sticky='w',pady=(10,4))
        chosen = ttk.Frame(right,style='Card.TFrame')
        chosen.grid(row=2,column=0,sticky='ew')
        ttk.Label(chosen,textvariable=self.club_name,style='CardText.TLabel',wraplength=280).pack(side='left',fill='x',expand=True)
        ttk.Button(chosen,text='현 소속팀',style='Compact.TButton',command=self.current_club).pack(side='right')
        ttk.Entry(right,textvariable=self.club_query).grid(row=3,column=0,sticky='ew',pady=6)
        self.club_list = ScopePanel.compact_table(right,4,(('name','구단',250),('id','구단 ID',85)))
        self.club_list.bind('<<TreeviewSelect>>',self.select_club)
        ttk.Label(right,text='이 작업에만 적용할 지시 · 선택',style='CardText.TLabel').grid(row=5,column=0,sticky='w',pady=(10,4))
        self.directions = tk.Text(right,height=3,wrap='word',font='TkTextFont')
        self.directions.grid(row=6,column=0,sticky='nsew')
        self.generate_button = ttk.Button(right,text='생성 요청',style='Primary.TButton',command=self.submit,state='disabled')
        self.generate_button.grid(row=7,column=0,sticky='w',pady=(10,0))
        self.query.trace_add('write', self.queue_search)
        self.club_query.trace_add('write', lambda *_: self.filter_clubs())

    def choose_reference(self):
        if not self.player:
            return
        chosen = filedialog.askopenfilename(parent=self.parent.winfo_toplevel(), title='합성에 사용할 선수 사진',
                    filetypes=[('이미지', '*.png *.jpg *.jpeg *.webp *.bmp *.PNG *.JPG *.JPEG *.WEBP *.BMP'), ('모든 파일', '*')])
        if not chosen:
            return
        try:
            data = reference_png(chosen)
            with Image.open(BytesIO(data)) as image:
                preview = image.copy()
        except (OSError, ValueError) as exc:
            messagebox.showerror('사진을 불러올 수 없습니다', str(exc), parent=self.parent.winfo_toplevel())
            return
        self.reference_path, self.reference_image = chosen, preview
        self.reference_name.set(Path(chosen).name + ' · 이 요청의 얼굴 참조로 사용')
        self.remove_photo_button.configure(state='normal')
        self.draw_reference()

    def clear_reference(self):
        self.reference_path = self.reference_image = self.reference_photo = None
        self.reference_name.set('선택하지 않으면 기존 사진을 자동으로 찾습니다.')
        self.remove_photo_button.configure(state='disabled')
        self.draw_reference()

    def draw_reference(self, event=None):
        canvas = self.reference_canvas
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.delete('all')
        if self.reference_image is not None:
            preview = self.reference_image.copy()
            preview.thumbnail((max(1,width-12),max(1,height-12)), Image.Resampling.LANCZOS)
            self.reference_photo = ImageTk.PhotoImage(preview, master=canvas)
            canvas.create_image(width/2,height/2,image=self.reference_photo)
        else:
            canvas.create_text(width/2,height/2,text='사진 불러오기' if self.player else '먼저 선수를 선택하세요',fill=MUTED,font='TkTextFont')

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
            self.clear_reference()
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
                self.clear_reference()
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
        self.clear_reference()
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
        self.choose_photo_button.configure(state='normal' if self.player else 'disabled')

    def submit(self):
        if self.player and self.club_id in self.clubs:
            self.request(self.player['id'], self.club_id, self.directions.get('1.0', 'end').strip(), self.player['identity'], self.reference_path)
