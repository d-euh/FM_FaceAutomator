"""Muted silver-grey surfaces, neutral text, and plum accents."""
from tkinter import ttk

from PIL import Image, ImageColor, ImageDraw, ImageTk

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


def button_image(window, height, center, edge, outline=None):
    radius = 30
    width = 2 * radius + 1
    scale = 3
    size = (width * scale, height * scale)
    bounds = (0, 0, size[0] - 1, size[1] - 1)
    curve = min(radius, height / 2) * scale
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).rounded_rectangle(bounds, radius=curve, fill=255)

    inner, outer = ImageColor.getrgb(center), ImageColor.getrgb(edge)
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(size[1]):
        vertical = abs(2 * y / (size[1] - 1) - 1)
        for x in range(size[0]):
            horizontal = abs(2 * x / (size[0] - 1) - 1)
            strength = max(vertical, horizontal)
            draw.point((x, y), tuple(round(a + (b - a) * strength) for a, b in zip(inner, outer)))
    if outline:
        draw.rounded_rectangle(bounds, radius=curve, outline=outline, width=2 * scale)
    image.putalpha(mask)
    return ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS), master=window)


def configure_buttons(window, style):
    # Stretch the middle of the image while keeping its rounded ends intact.
    images = []
    for name, height, padding, palette in (
        ("TButton", 38, (13, 9), (PURPLE, "#8D589E")),
        ("Compact.TButton", 30, (11, 5), (PURPLE, "#8D589E")),
        ("Primary.TButton", 38, (15, 9), ("#532366", "#805090")),
    ):
        normal = button_image(window, height, *palette)
        disabled = button_image(window, height, "#76647F", PURPLE_DISABLED)
        pressed = button_image(window, height, "#33123F", "#62316F", "#D7A7E4")
        focused = button_image(window, height, *palette, "#E8C5F2")
        hovered = button_image(window, height, PURPLE_HOVER, "#A06CB1")
        images.extend((normal, disabled, pressed, focused, hovered))
        element = f"{name}.gradient"
        style.element_create(element, "image", normal, ("disabled", disabled),
                             ("pressed", pressed), ("focus", focused), ("active", hovered),
                             border=(30, height // 2, 30, height // 2 - 1), sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [
                ("Button.label", {"sticky": "nsew"})]})]})])
        style.configure(name, padding=padding, foreground=BUTTON_TEXT, anchor="center")
        x, y = padding
        style.map(name, foreground=[("disabled", BUTTON_TEXT), ("!disabled", BUTTON_TEXT)],
                  padding=[("pressed", "!disabled", (x, y + 2, x, y - 2))])
    # Tcl's image elements refer to image names, so retain the Python objects.
    window.button_theme_images = images


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
    style.configure("Badge.TLabel", background=SELECTED, foreground=PURPLE, padding=(12, 7), font=(family, 10, "bold"))
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
