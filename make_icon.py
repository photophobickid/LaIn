"""Генерация icon.ico: мягкая indigo-точка."""
from PIL import Image, ImageDraw

DOT = (110, 127, 204, 255)  # #6E7FCC


def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=DOT)
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
base = make(256)
base.save("icon.ico", sizes=[(s, s) for s in sizes])
print("icon.ico ok")
