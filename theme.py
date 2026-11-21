"""Muted silver-grey surfaces, neutral text, and plum accents."""
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

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


def button_image(window, radius, color, outline=None, *, background=None, outline_width=2):
    size = 2 * radius + 1
    scale = 3
    image = Image.new("RGBA", (size * scale, size * scale), background)
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1), radius=radius * scale,
        fill=color, outline=outline, width=outline_width * scale)
    return ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS), master=window)


def configure_buttons(window, style):
    images = []
    for name, radius, padding, outline in (
        ("TButton", 18, (13, 9), None),
        ("Compact.TButton", 14, (11, 5), None),
        ("Primary.TButton", 18, (13, 9), PURPLE_HOVER),
    ):
        normal = button_image(window, radius, PURPLE, outline)
        disabled = button_image(window, radius, PURPLE_DISABLED, outline)
        pressed = button_image(window, radius, "#33123F", "#D7A7E4")
        focused = button_image(window, radius, PURPLE, "#E8C5F2")
        hovered = button_image(window, radius, PURPLE_HOVER, outline)
        images.extend((normal, disabled, pressed, focused, hovered))
        element = f"{name}.rounded"
        # The image supplies the shape, not the minimum size. Keep the same
        # 3px inset as the original clam border and focus elements.
        style.element_create(element, "image", normal, ("disabled", disabled),
                             ("pressed", pressed), ("focus", focused), ("active", hovered),
                             border=radius, padding=3, width=0, height=0, sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [
                ("Button.label", {"sticky": "nsew"})]})]})])
        style.configure(name, padding=padding, foreground=BUTTON_TEXT)
        x, y = padding
        style.map(name, foreground=[("disabled", BUTTON_TEXT), ("!disabled", BUTTON_TEXT)],
                  padding=[("pressed", "!disabled", (x, y + 2, x, y - 2))])
    # Tcl's image elements refer to image names, so retain the Python objects.
    window.button_theme_images = images


def match_button_background(event):
    button = event.widget
    style = ttk.Style(button)
    parent = button.master
    if isinstance(parent, ttk.Widget):
        background = style.lookup(parent.cget("style") or parent.winfo_class(), "background")
    else:
        background = parent.cget("background")
    background = background or BACKGROUND
    red, green, blue = button.winfo_rgb(background)
    color = f"#{red // 257:02x}{green // 257:02x}{blue // 257:02x}"
    base = button.cget("style") or "TButton"
    if base.startswith("Surface"):
        base = base.split(".", 1)[1]
    name = f"Surface{color[1:]}.{base}"
    style.configure(name, background=color)
    style.map(name, background=[("disabled", color), ("!disabled", color)])
    button.configure(style=name)


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
    configure_buttons(window, style)
    window.bind_class("TButton", "<Map>", match_button_background, add="+")
    style.configure("Badge.TLabel", background=SELECTED, foreground=PURPLE, padding=(12, 7), font=(family, 10, "bold"))
    style.configure("Title.TLabel", font=(family, 22, "bold"))
    style.configure("Section.TLabel", font=(family, 13, "bold"), foreground=TEXT, background=BACKGROUND)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Card.TFrame", background=SURFACE, borderwidth=0, relief="flat")
    style.configure("Panel.Card.TFrame", background=SURFACE, borderwidth=1, relief="solid", bordercolor=BORDER)
    panel_image = button_image(window, 10, SURFACE, BORDER,
                               background=BACKGROUND, outline_width=1)
    style.element_create("Panel.rounded", "image", panel_image,
                         border=10, padding=1, width=0, height=0, sticky="nsew")
    style.layout("Panel.Card.TFrame", [("Panel.rounded", {"sticky": "nsew"})])
    window.panel_theme_image = panel_image
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
                  indicatorbackground=[("alternate", PURPLE), ("selected", PURPLE), ("active", SELECTED)])
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
