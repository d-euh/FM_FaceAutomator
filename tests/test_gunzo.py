from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops, PngImagePlugin

from engine import validate_png
from gunzo import bundled_font_path, layout_name, render_gunzo


class GunzoCaptionTests(unittest.TestCase):
    def setUp(self):
        self.font = str(bundled_font_path("koverwatch.ttf"))

    def card(self, **options):
        source = BytesIO()
        Image.new("RGB", (350, 350), (70, 90, 120)).save(source, format="PNG")
        source.seek(0)
        result = Image.open(BytesIO(render_gunzo(source, "Bruno Fernandes", self.font, **options)))
        result.load()
        return result

    def test_size_changes_letter_pixels_and_leaves_face_region_unchanged(self):
        with self.card(name_font_size=18, name_color="#FFFFFF") as small, self.card(name_font_size=40, name_color="#FFFFFF") as large:
            def white_bounds(card):
                points = [(x, y) for y in range(280, 340) for x in range(25, 325) if min(card.getpixel((x, y))[:3]) >= 248]
                return min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)
            a, b = white_bounds(small), white_bounds(large)
            self.assertGreater(b[2] - b[0], a[2] - a[0] + 50)
            self.assertGreater(b[3] - b[1], a[3] - a[1] + 10)
            self.assertIsNone(ImageChops.difference(small.crop((0, 0, 350, 280)), large.crop((0, 0, 350, 280))).getbbox())
            self.assertEqual(large.size, (350, 350))
            self.assertEqual(large.info["CornerRadius"], "60")

    def test_long_names_stay_complete_on_one_line_and_fit_the_card(self):
        name = "Ludwig Augustinsson Alexander Sorloth"
        text, font, lines, heights = layout_name(name, self.font, 48)
        self.assertEqual(lines, [name.upper()])
        self.assertEqual(text, name.upper())
        self.assertLess(font.size, 48)
        bounds = font.getbbox(text, stroke_width=1)
        self.assertLessEqual(bounds[2] - bounds[0], 300)
        self.assertEqual(len(heights), 1)

    def test_bold_thickens_the_colored_glyph_and_keeps_face_and_corners_unchanged(self):
        with self.card(name_bold=False, name_color="#FFFFFF") as regular, self.card(name_bold=True, name_color="#FFFFFF") as bold:
            def filled_pixels(card):
                return sum(min(card.getpixel((x, y))[:3]) >= 248 for y in range(280, 340) for x in range(25, 325))
            self.assertGreater(filled_pixels(bold), filled_pixels(regular) * 1.15)
            self.assertEqual(regular.info["NameBold"], "false")
            self.assertEqual(bold.info["NameBold"], "true")
            self.assertIsNone(ImageChops.difference(regular.crop((0, 0, 350, 280)), bold.crop((0, 0, 350, 280))).getbbox())
            self.assertIsNone(ImageChops.difference(regular.getchannel("A"), bold.getchannel("A")).getbbox())
            self.assertEqual(bold.size, (350, 350))

    def test_old_completed_layout_remains_applicable_without_another_ai_call(self):
        with tempfile.TemporaryDirectory() as folder, self.card() as image:
            path = Path(folder) / "legacy.png"
            info = PngImagePlugin.PngInfo()
            info.add_text("Layout", "gunzo-350-v1")
            info.add_text("PlayerName", "BRUNO FERNANDES")
            image.save(path, pnginfo=info)
            validate_png(path)
