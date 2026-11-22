"""Regenerate application icons directly from the supplied full-resolution art."""
from pathlib import Path

from PIL import Image, ImageFilter


SIZES = (16, 20, 24, 28, 32, 40, 48, 64, 96, 128, 192, 256)


def generate_icons():
    directory = Path(__file__).resolve().parents[1] / "icons"
    with Image.open(directory / "ffa-source.png") as source:
        source = source.convert("RGBA")
        frames = []
        for size in SIZES:
            frame = source.resize((size, size), Image.Resampling.LANCZOS)
            if size <= 64:
                frame = frame.filter(ImageFilter.UnsharpMask(radius=0.5, percent=80, threshold=3))
            frames.append(frame)
        frames[-1].save(directory / "ffa.png")
        frames[-1].save(
            directory / "ffa.ico", sizes=[(size, size) for size in SIZES],
            append_images=frames[:-1], bitmap_format="bmp",
        )


if __name__ == "__main__":
    generate_icons()
