"""Deterministic 350px Gunzo-style card and player-name rendering."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin


SIZE = 350
CORNER_RADIUS = 60
NAME_WIDTH = 300
LAYOUT = "gunzo-350-v1"
DEFAULT_FONT_FILENAME = "koverwatch.ttf"


def default_font_path():
    root = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    return root / DEFAULT_FONT_FILENAME


def name_font(path=""):
    candidate = Path(path) if path else default_font_path()
    if not candidate.is_file():
        raise ValueError(f"이름 글꼴 파일이 없습니다: {candidate}. 기본 글꼴 koverwatch.ttf를 프로그램 폴더에 넣거나 ‘폴더 · 연결’에서 폰트를 직접 선택하세요.")
    try:
        ImageFont.truetype(str(candidate), 20)
    except OSError as exc:
        raise ValueError("이름 글꼴을 읽을 수 없습니다. 올바른 TTF/OTF/TTC 파일을 선택하세요.") from exc
    return str(candidate)


def layout_name(name, font_path=""):
    name = " ".join(str(name).split()).upper()
    if not name or len(name) > 200:
        raise ValueError("하단 선수 이름을 1~200자로 입력하세요.")
    path = name_font(font_path)
    # Use the same shaping path here and when drawing the actual caption.
    probe = ImageDraw.Draw(Image.new("RGBA", (SIZE, SIZE)))
    for size in range(23, 8, -1):
        font = ImageFont.truetype(path, size)
        lines = [""]
        for char in name:
            if probe.textlength(lines[-1] + char, font=font) > NAME_WIDTH:
                lines.append("")
            lines[-1] += char
        lines = [line.strip() for line in lines]
        if len(lines) > 2:
            continue
        heights = []
        for line in lines:
            bounds = probe.textbbox((0, 0), line, font=font, stroke_width=1)
            heights.append(bounds[3] - bounds[1])
        if sum(heights) + (len(lines) - 1) * 4 <= 44:
            return name, font, lines, heights
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


def check_options(name, font_path="", template_path=""):
    layout_name(name, font_path)
    check_template(template_path)


def render_gunzo(source, name, font_path="", template_path=""):
    """Return a final PNG; never ask an image model to spell the caption."""
    name, font, lines, heights = layout_name(name, font_path)
    check_template(template_path)
    with Image.open(source) as original:
        original.load()
        card = ImageOps.fit(ImageOps.exif_transpose(original).convert("RGBA"),
                            (SIZE, SIZE), method=Image.Resampling.LANCZOS)
    shade = Image.new("RGBA", (SIZE, SIZE))
    drawing = ImageDraw.Draw(shade)
    for y in range(252, SIZE):
        alpha = round(205 * ((y - 252) / (SIZE - 253)) ** 1.2)
        drawing.line((0, y, SIZE, y), fill=(0, 0, 0, alpha))
    card = Image.alpha_composite(card, shade)
    if template_path:
        with Image.open(template_path) as template:
            card = Image.alpha_composite(card, template.convert("RGBA"))
    drawing = ImageDraw.Draw(card)
    y = 334 - (sum(heights) + 4 * (len(lines) - 1))
    for line, height in zip(lines, heights):
        bounds = drawing.textbbox((0, 0), line, font=font, stroke_width=1)
        x = (SIZE - (bounds[2] - bounds[0])) / 2 - bounds[0]
        drawing.text((x, y - bounds[1]), line, font=font, fill="white",
                     stroke_width=1, stroke_fill=(20, 20, 20, 255))
        y += height + 4
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
    out = BytesIO()
    card.save(out, format="PNG", pnginfo=info)
    return out.getvalue()
