"""Deterministic 350px Gunzo-style card and player-name rendering."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin


SIZE = 350
CORNER_RADIUS = 60
NAME_WIDTH = 300
LAYOUT = "gunzo-350-v2"
SUPPORTED_LAYOUTS = frozenset({LAYOUT, "gunzo-350-v1"})
DEFAULT_NAME_COLOR = "#F2DE9B"
DEFAULT_NAME_FONT_SIZE = 30
DEFAULT_FONT_FILENAME = "koverwatch.ttf"
DEFAULT_FONT_RELATIVE = "fonts/" + DEFAULT_FONT_FILENAME
BUNDLED_FONTS = (DEFAULT_FONT_FILENAME, "BebasNeue.otf", "venus rising rg.ttf")


def bundled_font_path(filename):
    # PyInstaller also resolves __file__ inside its bundled resource directory.
    return Path(__file__).resolve().parent / "fonts" / filename


def default_font_path():
    return bundled_font_path(DEFAULT_FONT_FILENAME)


def name_font(path=""):
    candidate = Path(path) if path else default_font_path()
    if not candidate.is_file():
        raise ValueError(f"이름 글꼴 파일이 없습니다: {candidate}. 프로그램의 fonts 폴더를 복구하거나 ‘폴더 · 연결’에서 폰트를 직접 선택하세요.")
    try:
        ImageFont.truetype(str(candidate), 20)
    except OSError as exc:
        raise ValueError("이름 글꼴을 읽을 수 없습니다. 올바른 TTF/OTF/TTC 파일을 선택하세요.") from exc
    return str(candidate)


def caption_settings(color=DEFAULT_NAME_COLOR, font_size=DEFAULT_NAME_FONT_SIZE):
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color.strip()):
        raise ValueError("이름 색상은 #RRGGBB 형식으로 입력하거나 ‘색상 선택’을 사용하세요.")
    try:
        size = int(font_size)
        if isinstance(font_size, bool) or float(font_size) != size or not 12 <= size <= 48:
            raise ValueError()
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("이름 글자 크기는 12~48px 사이의 정수로 입력하세요.") from exc
    return {"name_color": color.strip().upper(), "name_font_size": size}


def caption_options(config):
    return caption_settings(config.get("name_color", DEFAULT_NAME_COLOR), config.get("name_font_size", DEFAULT_NAME_FONT_SIZE))


def layout_name(name, font_path="", font_size=DEFAULT_NAME_FONT_SIZE):
    name = " ".join(str(name).split()).upper()
    if not name or len(name) > 200:
        raise ValueError("하단 선수 이름을 1~200자로 입력하세요.")
    path = name_font(font_path)
    # Use the same shaping path here and when drawing the actual caption.
    probe = ImageDraw.Draw(Image.new("RGBA", (SIZE, SIZE)))
    # Match the reference's centered single line. Long names shrink without truncation.
    for size in range(font_size, 7, -1):
        font = ImageFont.truetype(path, size)
        bounds = probe.textbbox((0, 0), name, font=font, stroke_width=1)
        if bounds[2] - bounds[0] > NAME_WIDTH:
            continue
        if bounds[3] - bounds[1] <= 48:
            return name, font, [name], [bounds[3] - bounds[1]]
    raise ValueError("이름을 하단에 읽기 좋게 넣을 수 없습니다. 선수별 표시 이름을 짧게 지정하세요.")


def check_template(path):
    if not path:
        return
    with Image.open(path) as template:
        if template.format != "PNG" or template.size != (SIZE, SIZE) or "A" not in template.getbands():
            raise ValueError("건조 폼 템플릿은 투명도를 포함한 350×350 PNG여야 합니다.")
        template.load()
        if template.getchannel("A").getextrema()[0] == 255:
            raise ValueError("템플릿 전체가 불투명하면 선수 얼굴이 가려집니다. 투명한 PNG를 선택하세요.")


def check_options(name, font_path="", template_path="", *, name_color=DEFAULT_NAME_COLOR, name_font_size=DEFAULT_NAME_FONT_SIZE):
    settings = caption_settings(name_color, name_font_size)
    layout_name(name, font_path, settings["name_font_size"])
    check_template(template_path)


def render_gunzo(source, name, font_path="", template_path="", *, name_color=DEFAULT_NAME_COLOR, name_font_size=DEFAULT_NAME_FONT_SIZE):
    """Return a final PNG; never ask an image model to spell the caption."""
    settings = caption_settings(name_color, name_font_size)
    name, font, _, _ = layout_name(name, font_path, settings["name_font_size"])
    check_template(template_path)
    with Image.open(source) as original:
        original.load()
        card = ImageOps.fit(ImageOps.exif_transpose(original).convert("RGBA"),
                            (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    shade = Image.new("RGBA", (SIZE, SIZE))
    drawing = ImageDraw.Draw(shade)
    for y in range(282, SIZE):
        alpha = round(95 * ((y - 282) / (SIZE - 283)) ** 1.2)
        drawing.line((0, y, SIZE, y), fill=(0, 0, 0, alpha))
    card = Image.alpha_composite(card, shade)
    if template_path:
        with Image.open(template_path) as template:
            card = Image.alpha_composite(card, template.convert("RGBA"))
    # Supersample only the local caption: cream fill, dark outline and subtle shadow.
    scale = 4
    lettering = Image.new("RGBA", (SIZE * scale, SIZE * scale))
    drawing = ImageDraw.Draw(lettering)
    display_font = ImageFont.truetype(font.path, font.size * scale)
    bounds = drawing.textbbox((0, 0), name, font=display_font, stroke_width=scale)
    x = (SIZE * scale - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = 334 * scale - bounds[3]
    drawing.text((x + 2 * scale, y + 2 * scale), name, font=display_font, fill=(0, 0, 0, 160), stroke_width=scale, stroke_fill=(0, 0, 0, 160))
    drawing.text((x, y), name, font=display_font, fill=settings["name_color"], stroke_width=scale, stroke_fill=(35, 29, 21, 255))
    card = Image.alpha_composite(card, lettering.resize((SIZE, SIZE), Image.Resampling.LANCZOS))
    # Render the 60px outer radius at 4x for smooth transparent edges.
    scale = 4
    mask = Image.new("L", (SIZE * scale, SIZE * scale))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE * scale - 1, SIZE * scale - 1), radius=CORNER_RADIUS * scale, fill=255)
    mask = mask.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    card.putalpha(Image.composite(card.getchannel("A"), Image.new("L", (SIZE, SIZE)), mask))
    info = PngImagePlugin.PngInfo()
    info.add_itxt("PlayerName", name)
    info.add_text("Layout", LAYOUT)
    info.add_text("CornerRadius", str(CORNER_RADIUS))
    info.add_itxt("NameFont", Path(font.path).name)
    info.add_text("NameColor", settings["name_color"])
    info.add_text("NameFontSize", str(settings["name_font_size"]))
    info.add_text("RenderedNameFontSize", str(font.size))
    info.add_text("NameLayout", "single-line")
    out = BytesIO()
    card.save(out, format="PNG", pnginfo=info)
    return out.getvalue()
