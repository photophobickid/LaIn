"""Генерация icon.ico для приложения: мягкий синий кружок с белой обводкой."""
from PIL import Image, ImageDraw

BLUE = (110, 155, 230, 255)
WHITE = (255, 255, 255, 255)


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    ring = max(1, size // 16)
    d.ellipse([pad, pad, size - pad, size - pad], fill=BLUE, outline=WHITE, width=ring)
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
base = make(256)
base.save("icon.ico", sizes=[(s, s) for s in sizes])
print("icon.ico создан")
