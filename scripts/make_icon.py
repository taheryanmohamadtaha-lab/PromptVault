"""ساخت آیکون برنامه (app/assets/icon.png و icon.ico) با Pillow. اجرا: python scripts/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "app" / "assets"
S = 1024  # رسم در اندازه‌ی بزرگ و کوچک‌کردن برای لبه‌های نرم


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # پس‌زمینه‌ی گرادیانی (نیلی → صورتی)
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    c1, c2 = (79, 107, 237), (255, 79, 163)
    for y in range(S):
        for x in range(S):
            px[x, y] = (*lerp(c1, c2, (x + y) / (2 * S)), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx, top, mid, bot = S // 2, 250, 420, 790
    left, right = 250, S - 250
    # نگین (گنجینه): بالا، کمربند، نوک
    d.polygon([(left + 90, top), (right - 90, top), (right, mid), (cx, bot), (left, mid)], fill=(255, 255, 255, 255))
    facet = (220, 228, 255, 255)
    d.polygon([(left, mid), (left + 90, top), (cx - 70, mid)], fill=facet)
    d.polygon([(right, mid), (right - 90, top), (cx + 70, mid)], fill=facet)
    d.polygon([(left, mid), (cx - 70, mid), (cx, bot)], fill=(200, 210, 250, 255))
    d.polygon([(right, mid), (cx + 70, mid), (cx, bot)], fill=(200, 210, 250, 255))
    d.polygon([(cx - 70, mid), (cx + 70, mid), (cx, bot)], fill=(240, 244, 255, 255))
    d.polygon([(left + 90, top), (right - 90, top), (cx + 70, mid), (cx - 70, mid)], fill=(255, 255, 255, 255))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    big = build()
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    big.save(OUT / "icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("آیکون ساخته شد:", OUT)
