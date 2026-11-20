"""Muted silver-grey surfaces, neutral text, and plum accents."""
from tkinter import ttk

BACKGROUND = "#C8C9CF"
SURFACE = "#E7E8EC"
INPUT = "#F3F3F5"
BUTTON_TEXT = "#FFFFFF"
TEXT = "#28252F"
MUTED = "#625F6A"
PURPLE = "#633078"
PURPLE_HOVER = "#512563"
PURPLE_DISABLED = "#9987A1"
BORDER = "#ADB0BA"
SELECTED = "#DED2E5"
HOVER = "#D7D8DF"
LOG_BACKGROUND = "#BFC1C8"
PREVIEW_BACKGROUND = "#D4D6DD"
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
    style.configure("TButton", padding=(13, 9), background=PURPLE, foreground=BUTTON_TEXT, bordercolor=PURPLE, relief="flat")
    style.configure("Compact.TButton", padding=(11, 5))
    style.configure("Badge.TLabel", background=SELECTED, foreground=PURPLE, padding=(12, 7), font=(family, 10, "bold"))
    style.map("TButton", background=[("disabled", PURPLE_DISABLED), ("pressed", PURPLE_HOVER), ("active", PURPLE_HOVER)],
              foreground=[("disabled", BUTTON_TEXT), ("!disabled", BUTTON_TEXT)], bordercolor=[("focus", PURPLE_HOVER), ("active", PURPLE_HOVER)])
    style.configure("Primary.TButton", background=PURPLE, foreground=BUTTON_TEXT, bordercolor=PURPLE_HOVER, borderwidth=2, relief="solid")
    style.map("Primary.TButton", background=[("disabled", PURPLE_DISABLED), ("pressed", PURPLE_HOVER), ("active", PURPLE_HOVER)],
              foreground=[("disabled", BUTTON_TEXT), ("!disabled", BUTTON_TEXT)],
              bordercolor=[("disabled", PURPLE_HOVER), ("!disabled", PURPLE_HOVER)])
    style.configure("Title.TLabel", font=(family, 22, "bold"))
    style.configure("Section.TLabel", font=(family, 13, "bold"), foreground=TEXT, background=BACKGROUND)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Card.TFrame", background=SURFACE, borderwidth=0, relief="flat")
    style.configure("Panel.Card.TFrame", background=SURFACE, borderwidth=1, relief="solid", bordercolor=BORDER)
    style.configure("CardText.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("CardTitle.TLabel", background=SURFACE, foreground=TEXT, font=(family, 13, "bold"))
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Metric.TLabel", background=SURFACE, foreground=PURPLE, font=(family, 25, "bold"))
    style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT,
                    selectbackground=SELECTED, selectforeground=TEXT, padding=(9, 6))
    style.map("TEntry", fieldbackground=[("disabled", BACKGROUND), ("readonly", SURFACE)],
              foreground=[("disabled", DISABLED)], bordercolor=[("focus", PURPLE)])
    style.configure("TCombobox", fieldbackground=INPUT, foreground=TEXT, background=SURFACE, arrowcolor=MUTED,
                    selectbackground=SELECTED, selectforeground=TEXT, padding=(9, 5))
    style.map("TCombobox", fieldbackground=[("disabled", BACKGROUND), ("readonly", INPUT)],
              foreground=[("disabled", DISABLED), ("readonly", TEXT)],
              background=[("active", HOVER), ("readonly", SURFACE)], arrowcolor=[("disabled", DISABLED)])
    for name, background in (("TCheckbutton", BACKGROUND), ("TRadiobutton", BACKGROUND), ("Card.TCheckbutton", SURFACE)):
        style.configure(name, background=background, foreground=TEXT, indicatorbackground=INPUT, indicatorforeground=INPUT)
        style.map(name, background=[("active", background)], foreground=[("disabled", DISABLED)],
                  indicatorbackground=[("selected", PURPLE), ("active", SELECTED)])
    style.configure("Treeview", background=INPUT, fieldbackground=INPUT, foreground=TEXT, rowheight=36, bordercolor=BORDER)
    style.configure("Treeview.Heading", background=HOVER, foreground=TEXT, font=(family, 10, "bold"), padding=(8, 8), relief="flat")
    style.map("Treeview", background=[("selected", SELECTED)], foreground=[("disabled", DISABLED), ("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", SELECTED)])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", background=BACKGROUND, foreground=MUTED, padding=(22, 12), bordercolor=BORDER)
    style.map("TNotebook.Tab", background=[("selected", SURFACE), ("active", HOVER)],
              foreground=[("disabled", DISABLED), ("selected", PURPLE), ("active", TEXT)],
              lightcolor=[("selected", SURFACE)], darkcolor=[("selected", BORDER)])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=BORDER, troughcolor=BACKGROUND, arrowcolor=MUTED, bordercolor=BORDER)
        style.map(name, background=[("active", DISABLED), ("pressed", DISABLED)], arrowcolor=[("disabled", DISABLED)])
