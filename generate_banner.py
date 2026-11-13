"""
Generates the official 1600x400 (4:1 aspect ratio) Google Form Header Banner
for Aufbruch – Alumni Conclave 2026 in Deep Navy & Royal Gold.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def create_header_banner(output_path: Path):
    width, height = 1600, 400
    img = Image.new("RGB", (width, height), "#0A1628")
    draw = ImageDraw.Draw(img)

    # Radial/linear gradient effect in Deep Navy -> Royal Blue
    for y in range(height):
        r = int(10 + (18 - 10) * (y / height))
        g = int(22 + (42 - 22) * (y / height))
        b = int(40 + (78 - 40) * (y / height))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Subtle decorative gold framing lines
    gold_bright = (212, 175, 55)
    gold_soft = (165, 134, 42)
    gold_pale = (243, 223, 145)

    # Outer double border
    draw.rectangle([24, 24, width - 25, height - 25], outline=gold_soft, width=2)
    draw.rectangle([34, 34, width - 35, height - 35], outline=gold_bright, width=3)

    # Corner accents
    corner_len = 48
    for cx, cy, dx, dy in [
        (34, 34, 1, 1),
        (width - 35, 34, -1, 1),
        (34, height - 35, 1, -1),
        (width - 35, height - 35, -1, -1),
    ]:
        draw.line([(cx, cy), (cx + dx * corner_len, cy)], fill=gold_pale, width=5)
        draw.line([(cx, cy), (cx, cy + dy * corner_len)], fill=gold_pale, width=5)

    # Load uploaded Sora font files from ./public/fonts/ or ./fonts/
    fonts_dir = output_path.parent / "public" / "fonts"
    if not fonts_dir.exists():
        fonts_dir = output_path.parent / "fonts"
    def load_font(names, size):
        for name in names:
            try:
                p = fonts_dir / name
                if p.exists():
                    return ImageFont.truetype(str(p), size)
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    font_badge = load_font(["Sora-Bold.ttf", "segoeuib.ttf", "arialbd.ttf"], 20)
    font_title = load_font(["Sora-ExtraBold.ttf", "Sora-Bold.ttf", "arialbd.ttf"], 58)
    font_sub = load_font(["Sora-SemiBold.ttf", "Sora-Bold.ttf", "arialbd.ttf"], 28)
    font_meta = load_font(["Sora-Medium.ttf", "Sora-Regular.ttf", "arial.ttf"], 24)

    def draw_centered_text(y, text, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) // 2, y), text, font=font, fill=fill)

    draw_centered_text(62, "MAJMAU ACADEMY ALUMNI ASSOCIATION PRESENTS", font_badge, gold_pale)
    draw_centered_text(110, "AUFBRUCH – ALUMNI CONCLAVE 2026", font_title, (255, 255, 255))

    # Divider line with diamond
    mid_x = width // 2
    draw.line([(mid_x - 320, 206), (mid_x - 20, 206)], fill=gold_bright, width=2)
    draw.polygon([(mid_x, 198), (mid_x + 10, 206), (mid_x, 214), (mid_x - 10, 206)], fill=gold_bright)
    draw.line([(mid_x + 20, 206), (mid_x + 320, 206)], fill=gold_bright, width=2)

    draw_centered_text(232, "Thursday, December 10, 2026   |   3:30 PM to 9:30 PM", font_sub, gold_bright)
    draw_centered_text(286, "Venue: Majmau Academy, Nilambur", font_meta, (226, 232, 240))

    img.save(output_path, "PNG", optimize=True)
    print(f"Saved banner image to {output_path}")


if __name__ == "__main__":
    create_header_banner(Path(__file__).resolve().parent / "aufbruch_2026_form_header.png")
