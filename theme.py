"""Black surfaces and the requested RGB(113, 10, 158) app text."""
from tkinter import ttk

BLACK = "#000000"
PURPLE = "#710A9E"
BORDER = "#310544"
SELECTED = "#190323"


def apply_theme(window, family):
    window.configure(background=BLACK)
    for pattern, value in {
        "*background": BLACK, "*foreground": PURPLE,
        "*insertBackground": PURPLE, "*selectBackground": SELECTED,
        "*selectForeground": PURPLE, "*highlightBackground": BORDER,
        "*highlightColor": PURPLE,
        "*TCombobox*Listbox.background": BLACK,
        "*TCombobox*Listbox.foreground": PURPLE,
        "*TCombobox*Listbox.selectBackground": SELECTED,
        "*TCombobox*Listbox.selectForeground": PURPLE,
    }.items():
        window.option_add(pattern, value)
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure(".", font=(family, 10), background=BLACK, foreground=PURPLE,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BLACK,
                    troughcolor=BLACK, focuscolor=PURPLE)
    style.configure("TFrame", background=BLACK)
    style.configure("TLabel", background=BLACK, foreground=PURPLE)
    style.configure("TButton", padding=(13, 9), background=BLACK, foreground=PURPLE, bordercolor=BORDER, relief="flat")
    style.map("TButton", background=[("pressed", SELECTED), ("active", SELECTED), ("disabled", BLACK)],
              foreground=[("disabled", PURPLE)], bordercolor=[("focus", PURPLE), ("active", PURPLE)])
    style.configure("Primary.TButton", background=BLACK, foreground=PURPLE, bordercolor=PURPLE, borderwidth=2, relief="solid")
    style.map("Primary.TButton", background=[("active", SELECTED), ("pressed", SELECTED), ("disabled", BLACK)], foreground=[("disabled", PURPLE)])
    style.configure("Title.TLabel", font=(family, 20, "bold"))
    style.configure("Muted.TLabel", foreground=PURPLE)
    style.configure("Card.TFrame", background=BLACK, bordercolor=BORDER, borderwidth=1, relief="solid")
    for name in ("CardText.TLabel", "CardMuted.TLabel", "CardTitle.TLabel"):
        style.configure(name, background=BLACK, foreground=PURPLE)
    style.configure("CardTitle.TLabel", font=(family, 13, "bold"))
    style.configure("Metric.TLabel", background=BLACK, foreground=PURPLE, font=(family, 25, "bold"))
    style.configure("TEntry", fieldbackground=BLACK, foreground=PURPLE, insertcolor=PURPLE, bordercolor=BORDER,
                    selectbackground=SELECTED, selectforeground=PURPLE)
    style.map("TEntry", fieldbackground=[("readonly", BLACK), ("disabled", BLACK)], foreground=[("disabled", PURPLE)], bordercolor=[("focus", PURPLE)])
    style.configure("TCombobox", fieldbackground=BLACK, foreground=PURPLE, background=BLACK, arrowcolor=PURPLE, insertcolor=PURPLE,
                    selectbackground=SELECTED, selectforeground=PURPLE)
    style.map("TCombobox", fieldbackground=[("readonly", BLACK), ("disabled", BLACK)],
              foreground=[("readonly", PURPLE), ("disabled", PURPLE)],
              background=[("active", SELECTED), ("readonly", BLACK)], arrowcolor=[("disabled", PURPLE)])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=BLACK, foreground=PURPLE, indicatorbackground=BLACK, indicatorforeground=PURPLE)
        style.map(name, background=[("active", BLACK)], foreground=[("disabled", PURPLE)], indicatorbackground=[("selected", PURPLE), ("active", SELECTED)])
    style.configure("Treeview", background=BLACK, fieldbackground=BLACK, foreground=PURPLE, rowheight=30, bordercolor=BORDER)
    style.configure("Treeview.Heading", background=BLACK, foreground=PURPLE, padding=(8, 8), relief="flat")
    style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", PURPLE), ("disabled", PURPLE)])
    style.map("Treeview.Heading", background=[("active", SELECTED)])
    style.configure("TNotebook", background=BLACK, borderwidth=0)
    style.configure("TNotebook.Tab", background=BLACK, foreground=PURPLE, padding=(18, 10))
    style.map("TNotebook.Tab", background=[("selected", SELECTED), ("active", SELECTED)], foreground=[("selected", PURPLE), ("disabled", PURPLE)])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=BLACK, troughcolor=BLACK, arrowcolor=PURPLE, bordercolor=BORDER)
        style.map(name, background=[("active", SELECTED), ("pressed", SELECTED)], arrowcolor=[("disabled", PURPLE)])
    for name in ("TButton", "Primary.TButton", "TEntry", "TCombobox", "TNotebook", "TNotebook.Tab", "Treeview.Heading",
                 "Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, lightcolor=BORDER, darkcolor=BLACK)
