"""Генерация icon.ico: Aurora Glass — indigo ядро со светящимся кольцом."""
from PIL import Image, ImageDraw

CORE = (79, 70, 229, 255)    # #4F46E5
GLOW = (129, 140, 248, 255)  # #818CF8


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=GLOW)
    inset = max(2, size // 5)
    d.ellipse([inset, inset, size - 1 - inset, size - 1 - inset], fill=CORE)
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
base = make(256)
base.save("icon.ico", sizes=[(s, s) for s in sizes])
print("icon.ico создан")
