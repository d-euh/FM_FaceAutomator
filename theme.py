"""Silver-grey surfaces, neutral text, and RGB(113, 10, 158) accents."""
from tkinter import ttk

BACKGROUND = "#D6D7DB"
SURFACE = "#F5F5F7"
INPUT = "#FFFFFF"
TEXT = "#28252F"
MUTED = "#6B6773"
PURPLE = "#710A9E"
PURPLE_HOVER = "#58077B"
BORDER = "#BEC0C8"
SELECTED = "#EBDFF1"
HOVER = "#E5E5EB"
LOG_BACKGROUND = "#CED0D6"
PREVIEW_BACKGROUND = "#E3E4E9"
DISABLED = "#A6A4AD"


def apply_theme(window, family):
    window.configure(background=BACKGROUND)
    for pattern, value in {
        "*background": BACKGROUND, "*foreground": TEXT,
        "*insertBackground": TEXT, "*selectBackground": SELECTED,
        "*selectForeground": TEXT, "*highlightBackground": BORDER,
        "*highlightColor": PURPLE, "*Text.background": INPUT,
        "*Listbox.background": INPUT,
        "*TCombobox*Listbox.background": INPUT,
        "*TCombobox*Listbox.foreground": TEXT,
        "*TCombobox*Listbox.selectBackground": SELECTED,
        "*TCombobox*Listbox.selectForeground": TEXT,
    }.items():
        window.option_add(pattern, value)
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure(".", font=(family, 10), background=BACKGROUND, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    troughcolor=BACKGROUND, focuscolor=PURPLE)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("TButton", padding=(13, 9), background=SURFACE, foreground=TEXT, bordercolor=BORDER, relief="flat")
    style.map("TButton", background=[("disabled", BACKGROUND), ("pressed", SELECTED), ("active", HOVER)],
              foreground=[("disabled", DISABLED)], bordercolor=[("focus", PURPLE), ("active", BORDER)])
    style.configure("Primary.TButton", background=PURPLE, foreground=INPUT, bordercolor=PURPLE, borderwidth=1, relief="flat")
    style.map("Primary.TButton", background=[("disabled", DISABLED), ("pressed", PURPLE_HOVER), ("active", PURPLE_HOVER)],
              foreground=[("disabled", SURFACE), ("!disabled", INPUT)],
              bordercolor=[("disabled", DISABLED), ("!disabled", PURPLE)])
    style.configure("Title.TLabel", font=(family, 20, "bold"))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Card.TFrame", background=SURFACE, borderwidth=0, relief="flat")
    style.configure("CardText.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("CardTitle.TLabel", background=SURFACE, foreground=TEXT, font=(family, 13, "bold"))
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Metric.TLabel", background=SURFACE, foreground=PURPLE, font=(family, 25, "bold"))
    style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT,
                    selectbackground=SELECTED, selectforeground=TEXT)
    style.map("TEntry", fieldbackground=[("disabled", BACKGROUND), ("readonly", SURFACE)],
              foreground=[("disabled", DISABLED)], bordercolor=[("focus", PURPLE)])
    style.configure("TCombobox", fieldbackground=INPUT, foreground=TEXT, background=SURFACE, arrowcolor=MUTED,
                    selectbackground=SELECTED, selectforeground=TEXT)
    style.map("TCombobox", fieldbackground=[("disabled", BACKGROUND), ("readonly", INPUT)],
              foreground=[("disabled", DISABLED), ("readonly", TEXT)],
              background=[("active", HOVER), ("readonly", SURFACE)], arrowcolor=[("disabled", DISABLED)])
    for name, background in (("TCheckbutton", BACKGROUND), ("TRadiobutton", BACKGROUND), ("Card.TCheckbutton", SURFACE)):
        style.configure(name, background=background, foreground=TEXT, indicatorbackground=INPUT, indicatorforeground=INPUT)
        style.map(name, background=[("active", background)], foreground=[("disabled", DISABLED)],
                  indicatorbackground=[("selected", PURPLE), ("active", SELECTED)])
    style.configure("Treeview", background=INPUT, fieldbackground=INPUT, foreground=TEXT, rowheight=30, bordercolor=BORDER)
    style.configure("Treeview.Heading", background=HOVER, foreground=TEXT, font=(family, 10, "bold"), padding=(8, 8), relief="flat")
    style.map("Treeview", background=[("selected", SELECTED)], foreground=[("disabled", DISABLED), ("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", SELECTED)])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", background=BACKGROUND, foreground=MUTED, padding=(18, 10), bordercolor=BORDER)
    style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", HOVER)],
              foreground=[("disabled", DISABLED), ("selected", PURPLE), ("active", TEXT)],
              lightcolor=[("selected", SURFACE)], darkcolor=[("selected", BORDER)])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=BORDER, troughcolor=BACKGROUND, arrowcolor=MUTED, bordercolor=BORDER)
        style.map(name, background=[("active", DISABLED), ("pressed", DISABLED)], arrowcolor=[("disabled", DISABLED)])
